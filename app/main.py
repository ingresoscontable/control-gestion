"""Aplicación FastAPI de Control de Gestión (uso interno, red LAN)."""

from __future__ import annotations

import asyncio
import calendar
import logging
from contextlib import asynccontextmanager, suppress
from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path
from urllib.parse import quote, urlencode

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from openpyxl import Workbook
from openpyxl.styles import Font
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from . import auditoria, backup, config, reportes
from . import novedades as novedades_db
from .database import Base, SessionLocal, engine, get_db
from .jornada import describir_dias, es_laborable
from .metricas import (
    calendario_mes,
    expresion_en_fecha,
    horas_por_semana,
    puntualidad,
    resumen_semanal,
)
from .migraciones import aplicar_migraciones
from .models import (
    ACCIONES_AUDITORIA,
    ESTADO_ELIMINADA,
    ESTADOS_META,
    ESTADOS_REGISTRO,
    ESTADOS_REVISION,
    OPCIONES_AUDITORIA,
    OPCIONES_META,
    OPCIONES_NOVEDAD,
    OPCIONES_REGISTRO,
    REVISION_DEVUELTA,
    ROL_EMPLEADO,
    ROL_JEFE,
    TIPOS_NOVEDAD,
    Auditoria,
    Meta,
    Novedad,
    Registro,
    Usuario,
    nuevo_token_de_sesion,
)
from .progreso import metas_vencidas, progreso_metas, progreso_por_id
from .security import (
    es_pin_de_fabrica,
    hash_pin,
    intentos_login,
    ips_locales,
    olvidar_pin_de_fabrica,
    valida_pin,
    verificar_pin,
)
from .seed import borrar_primer_ingreso, crear_datos_iniciales

APP_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))

logger = logging.getLogger(__name__)

# Textos legales del sistema. Son paginas publicas (se leen sin iniciar
# sesion) para que cualquiera pueda conocerlas antes de usar la herramienta.
VERSION_LEGAL = "1.0"
ACTUALIZADO_LEGAL = "27/09/2026"
DOCUMENTOS_LEGALES = [
    ("privacidad", "Política de Privacidad"),
    ("cookies", "Cookies"),
    ("terminos", "Términos y condiciones"),
    ("licencia", "Licencia"),
]


def _auditar_respaldo_automatico(nombre: str) -> None:
    """Firma en la auditoria los respaldos que el sistema hace solo."""
    db = SessionLocal()
    try:
        auditoria.registrar(db, None, "crear_respaldo", "respaldo", resumen=nombre)
        db.commit()
    except Exception:  # noqa: BLE001 - no tumbar el respaldo por un fallo de escritura
        logger.exception("No se pudo registrar en la auditoria el respaldo %s", nombre)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    aplicar_migraciones()
    crear_datos_iniciales()
    tarea_respaldo = asyncio.create_task(
        backup.respaldo_periodico(_auditar_respaldo_automatico)
    )
    try:
        yield
    finally:
        tarea_respaldo.cancel()
        with suppress(asyncio.CancelledError):
            await tarea_respaldo


app = FastAPI(title=config.APP_NAME, lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=config.SECRET_KEY)
app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")


@app.middleware("http")
async def headers_de_seguridad(request: Request, call_next) -> Response:
    """Headers de seguridad basicos en todas las respuestas.

    No se bloquea F12 ni el click derecho (se saltean y rompen el copiado de
    datos): son headers que el navegador respeta de verdad.
    """
    respuesta = await call_next(request)
    respuesta.headers.setdefault("X-Content-Type-Options", "nosniff")
    respuesta.headers.setdefault("X-Frame-Options", "DENY")
    respuesta.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    respuesta.headers.setdefault(
        "X-Robots-Tag", "noindex, nofollow, nosnippet, noarchive"
    )
    return respuesta


# --------------------------------------------------------------------------
# Autenticación
# --------------------------------------------------------------------------
class Redireccionar(Exception):
    """Corta la peticion y responde con una redireccion 303.

    Se lanza desde las dependencias, que no pueden devolver una respuesta.
    (Un HTTPException(303) dejaria un JSON en el cuerpo de la respuesta.)
    """

    def __init__(self, destino: str) -> None:
        super().__init__(destino)
        self.destino = destino


@app.exception_handler(Redireccionar)
async def manejar_redireccion(request: Request, excepcion: Redireccionar) -> Response:
    return RedirectResponse(excepcion.destino, status_code=303)


@app.exception_handler(Exception)
async def error_interno(request: Request, excepcion: Exception) -> Response:
    """Pagina amigable en vez del error crudo del servidor.

    El detalle queda en data/sistema.log; al usuario solo se le dice que algo
    salio mal, sin filtrar el traceback.
    """
    logger.error("Error no controlado en %s", request.url.path, exc_info=excepcion)
    return templates.TemplateResponse(
        request, "error.html", contexto(request, None), status_code=500
    )


def usuario_actual(request: Request, db: Session = Depends(get_db)) -> Usuario | None:
    uid = request.session.get("usuario_id")
    if not uid:
        return None
    usuario = db.get(Usuario, uid)
    if usuario is None or not usuario.activo:
        request.session.clear()
        return None
    # Si le resetearon el PIN, la cookie vieja deja de valer en el acto.
    if usuario.sesion_token and request.session.get("sesion_token") != usuario.sesion_token:
        request.session.clear()
        return None
    return usuario


# Rutas que siguen disponibles con el PIN de fabrica: sin ellas no habria
# forma de cambiarlo sin quedar afuera del sistema.
RUTAS_LIBRES_PIN = ("/ayuda", "/mi-pin")


def requiere_login(
    request: Request,
    usuario: Usuario | None = Depends(usuario_actual),
) -> Usuario:
    if usuario is None:
        raise Redireccionar("/login")
    en_ruta_libre = request.url.path.startswith(RUTAS_LIBRES_PIN)
    if es_pin_de_fabrica(usuario.id, usuario.pin_hash) and not en_ruta_libre:
        raise Redireccionar(
            "/ayuda?msg=" + quote("Tu PIN es el de fábrica: cambialo antes de seguir")
        )
    return usuario


def requiere_jefe(usuario: Usuario = Depends(requiere_login)) -> Usuario:
    if not usuario.es_jefe:
        raise Redireccionar("/?msg=No+tienes+permiso+para+eso")
    return usuario


def ir_a(destino: str, msg: str = "") -> RedirectResponse:
    if msg:
        sep = "&" if "?" in destino else "?"
        destino = f"{destino}{sep}msg={quote(msg)}"
    return RedirectResponse(destino, status_code=303)


PAGINAS_VALIDAS = ("/", "/registros")

# Cuantos registros entra en una pantalla. Antes se tiraban los primeros 500 de
# una; ahora se pagina de 50 en 50 y los totales siguen siendo de TODOS los
# registros que cumplen el filtro (totales_registros).
POR_PAGINA = 50
LIMITE_HISTORIAL = 300
LIMITE_EXPORTACION = 5000


def volver_a(valor: str, por_defecto: str = "/") -> str:
    """Evita redirecciones abiertas: solo se vuelve a paginas conocidas.

    Acepta querystring (por ejemplo ``/registros?page=3``) porque las paginas
    de listado pasan la direccion entera para volver al mismo lugar.
    """
    base = (valor or "").split("?", 1)[0]
    if base in PAGINAS_VALIDAS or base.startswith("/personas/"):
        return valor
    return por_defecto


def pagina_de(valor: str) -> int:
    """Numero de pagina pedido en la URL (1 si viene vacio o mal escrito)."""
    return int(valor) if (valor or "").isdigit() and int(valor) > 0 else 1


def qs_filtros(filtros: dict) -> str:
    """Querystring de los filtros activos, para no perderlos al paginar."""
    datos = {}
    for clave, valor in filtros.items():
        if isinstance(valor, date):
            datos[clave] = valor.isoformat()
        elif valor not in ("", None):
            datos[clave] = valor
    return urlencode(datos)


# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------
def contexto(request: Request, usuario: Usuario | None, **extra) -> dict:
    datos = {
        "request": request,
        "usuario": usuario,
        "msg": request.query_params.get("msg", ""),
        "hoy": date.today(),
        "limite_carga": date.today() - timedelta(days=config.DIAS_ATRASO),
        "APP_NAME": config.APP_NAME,
        "estados_revision": ESTADOS_REVISION,
        "revision_etiquetas": dict(ESTADOS_REVISION),
        "dias_laborables_txt": describir_dias(config.DIAS_LABORABLES),
        "documentos": DOCUMENTOS_LEGALES,
    }
    datos.update(extra)
    return datos


def metas_visibles(db: Session, usuario: Usuario) -> list[Meta]:
    """Metas activas asignadas al usuario o a todo el equipo."""
    return list(
        db.scalars(
            select(Meta)
            .where(
                Meta.estado == "activa",
                or_(Meta.asignado_a.is_(None), Meta.asignado_a == usuario.id),
            )
            .options(*OPCIONES_META)
            .order_by(Meta.fecha_limite.is_(None), Meta.fecha_limite)
        )
    )


def metas_ordenadas(db: Session, incluir_eliminadas: bool = False) -> list[Meta]:
    """Metas en el orden en que se muestran, con el responsable ya cargado.

    Las archivadas (estado "eliminada") quedan fuera de todas las listas
    salvo que se las pida a proposito, en /metas.
    """
    consulta = select(Meta).options(*OPCIONES_META)
    if not incluir_eliminadas:
        consulta = consulta.where(Meta.estado != ESTADO_ELIMINADA)
    return list(
        db.scalars(
            consulta.order_by(Meta.estado, Meta.fecha_limite.is_(None), Meta.fecha_limite)
        )
    )


def meta_usable(db: Session, usuario: Usuario, meta_id: int) -> bool:
    """El usuario puede reportar sobre esa meta.

    Solo se pueden usar metas propias o del equipo (o cualquier meta si sos
    jefe). El estado no cuenta, porque "Repetir" trae la meta del dia
    anterior aunque ya este cerrada.
    """
    meta = db.get(Meta, meta_id)
    if meta is None:
        return False
    if usuario.es_jefe:
        return True
    return meta.asignado_a is None or meta.asignado_a == usuario.id


def puede_corregir(usuario: Usuario, registro: Registro) -> bool:
    """Puede editar un reporte: su dueño o el jefe."""
    return usuario.es_jefe or registro.usuario_id == usuario.id


def registro_duplicado(db: Session, usuario_id: int, dia: date, meta_id: int | None) -> bool:
    """Si esa persona ya cargo ese dia para esa meta (o para "sin meta")."""
    condicion_meta = Registro.meta_id.is_(None) if meta_id is None else Registro.meta_id == meta_id
    return (
        db.scalar(
            select(Registro.id).where(
                Registro.usuario_id == usuario_id,
                Registro.fecha == dia,
                condicion_meta,
            )
        )
        is not None
    )


def parse_fecha(valor: str) -> date | None:
    valor = (valor or "").strip()
    if not valor:
        return None
    try:
        return datetime.strptime(valor, "%Y-%m-%d").date()
    except ValueError:
        return None


def parse_horas(valor: str) -> float:
    try:
        horas = float((valor or "0").replace(",", "."))
    except ValueError:
        return 0.0
    return max(0.0, min(horas, 24.0))


def parse_numero(valor: str) -> float:
    """Numero positivo sin tope (para estimaciones de horas de una meta)."""
    try:
        numero = float((valor or "0").replace(",", "."))
    except ValueError:
        return 0.0
    return max(0.0, numero)


def empleados_activos(db: Session) -> list[Usuario]:
    """Empleados activos, sin el jefe (para asignar metas)."""
    return list(
        db.scalars(
            select(Usuario)
            .where(Usuario.activo.is_(True), Usuario.rol != ROL_JEFE)
            .order_by(Usuario.nombre)
        )
    )


def filtrar_registros(
    usuario_id: str,
    desde: str,
    hasta: str,
    meta_id: str = "",
    texto: str = "",
    estado: str = "",
    revision: str = "",
):
    """Arma la consulta de registros y los filtros aplicados.

    Se usa tanto en la pagina de registros como en la exportacion a Excel
    para que ambos muestren exactamente lo mismo.
    """
    consulta = select(Registro).order_by(Registro.fecha.desc(), Registro.id.desc())
    filtros: dict = {}

    if (usuario_id or "").isdigit():
        consulta = consulta.where(Registro.usuario_id == int(usuario_id))
        filtros["usuario_id"] = int(usuario_id)

    if (meta_id or "").isdigit():
        consulta = consulta.where(Registro.meta_id == int(meta_id))
        filtros["meta_id"] = int(meta_id)

    f_desde = parse_fecha(desde)
    f_hasta = parse_fecha(hasta)
    if f_desde:
        consulta = consulta.where(Registro.fecha >= f_desde)
        filtros["desde"] = f_desde
    if f_hasta:
        consulta = consulta.where(Registro.fecha <= f_hasta)
        filtros["hasta"] = f_hasta

    busca = (texto or "").strip()
    if busca:
        consulta = consulta.where(Registro.descripcion.ilike(f"%{busca}%"))
        filtros["texto"] = busca

    estado = (estado or "").strip()
    if estado in {clave for clave, _ in ESTADOS_REGISTRO}:
        consulta = consulta.where(Registro.estado == estado)
        filtros["estado"] = estado

    revision = (revision or "").strip()
    if revision in {clave for clave, _ in ESTADOS_REVISION}:
        consulta = consulta.where(Registro.estado_revision == revision)
        filtros["revision"] = revision

    return consulta, filtros


def totales_registros(db: Session, consulta) -> dict:
    """Totales de TODOS los registros que cumplen el filtro.

    Se calculan en una consulta aparte porque la lista que se muestra viene
    limitada: si no, el total de horas que aparece en pantalla dejaria de
    coincidir con lo que realmente hay en la base.
    """
    cantidad, horas, dias, comentarios, en_fecha = db.execute(
        consulta.with_only_columns(
            func.count(Registro.id),
            func.coalesce(func.sum(Registro.horas), 0.0),
            func.count(func.distinct(Registro.fecha)),
            func.coalesce(func.sum(case((Registro.comentario != "", 1), else_=0)), 0),
            func.coalesce(func.sum(case((expresion_en_fecha(), 1), else_=0)), 0),
        ).order_by(None)
    ).one()
    return {
        "cantidad": int(cantidad or 0),
        "horas": float(horas or 0.0),
        "dias": int(dias or 0),
        "comentarios": int(comentarios or 0),
        "en_fecha": int(en_fecha or 0),
    }


def horas_entre(db: Session, usuario_id: int, desde: date, hasta: date) -> float:
    """Horas cargadas por una persona en un rango de fechas (inclusive)."""
    return float(
        db.scalar(
            select(func.coalesce(func.sum(Registro.horas), 0.0)).where(
                Registro.usuario_id == usuario_id,
                Registro.fecha >= desde,
                Registro.fecha <= hasta,
            )
        )
        or 0.0
    )


def aviso_de_carga(db: Session, usuario_id: int, dia: date) -> str:
    """Avisa si la carga recien hecha se paso del dia o de la semana.

    No frenan el guardado: es un cartel en la pantalla, no una validacion.
    """
    inicio_semana = dia - timedelta(days=dia.weekday())
    avisos = []

    horas_dia = horas_entre(db, usuario_id, dia, dia)
    if horas_dia > config.HORAS_DIA:
        avisos.append(
            f"{horas_dia:.1f} h el {dia.strftime('%d/%m/%Y')} "
            f"(aviso por superar {config.HORAS_DIA:g} h en un dia)"
        )

    horas_semana = horas_entre(db, usuario_id, inicio_semana, inicio_semana + timedelta(days=6))
    if horas_semana > config.HORAS_SEMANA:
        avisos.append(
            f"{horas_semana:.1f} h en la semana "
            f"(aviso por superar {config.HORAS_SEMANA:g} h)"
        )

    if not avisos:
        return ""
    return "Cargaste " + "; ".join(avisos) + ". Revisalo si no es un error de tipeo."


# --------------------------------------------------------------------------
# Login / logout
# --------------------------------------------------------------------------
@app.get("/login")
def login_form(request: Request, usuario: Usuario | None = Depends(usuario_actual)):
    if usuario:
        return ir_a("/")
    return templates.TemplateResponse(request, "login.html", contexto(request, None))


@app.post("/login")
def login(
    request: Request,
    usuario_input: str = Form(..., alias="usuario"),
    pin: str = Form(...),
    db: Session = Depends(get_db),
):
    ip = request.client.host if request.client else "?"
    clave = f"{ip}|{usuario_input.strip().lower()}"

    espera = intentos_login.restante(clave)
    if espera > 0:
        return _login_bloqueado(request, usuario_input, espera)

    user = db.scalar(select(Usuario).where(Usuario.usuario == usuario_input.strip()))
    if user is None or not user.activo or not verificar_pin(pin, user.pin_hash):
        bloqueo = intentos_login.registrar_fallo(clave)
        if bloqueo:
            return _login_bloqueado(request, usuario_input, bloqueo)
        return templates.TemplateResponse(
            request,
            "login.html",
            contexto(request, None, error="Usuario o PIN incorrecto.", usuario_input=usuario_input),
            status_code=401,
        )
    intentos_login.limpiar(clave)
    request.session["usuario_id"] = user.id
    request.session["sesion_token"] = user.sesion_token
    return ir_a("/", f"Hola {user.nombre}")


def _login_bloqueado(request: Request, usuario_input: str, espera: float) -> Response:
    minutos = max(1, round(espera / 60))
    return templates.TemplateResponse(
        request,
        "login.html",
        contexto(
            request,
            None,
            error=f"Demasiados intentos fallidos. Volvé a intentar en {minutos} minuto(s).",
            usuario_input=usuario_input,
        ),
        status_code=429,
    )


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return ir_a("/login")


# --------------------------------------------------------------------------
# Panel
# --------------------------------------------------------------------------
@app.get("/")
def panel(
    request: Request,
    usuario: Usuario = Depends(requiere_login),
    db: Session = Depends(get_db),
    repetir: str = "",
):
    hoy = date.today()
    equipo = list(
        db.scalars(select(Usuario).where(Usuario.activo.is_(True)).order_by(Usuario.nombre))
    )

    registros_hoy = list(
        db.scalars(
            select(Registro)
            .where(Registro.fecha == hoy)
            .options(*OPCIONES_REGISTRO)
            .order_by(Registro.creado_en.desc())
        )
    )
    ids_registraron = {r.usuario_id for r in registros_hoy}

    metas = metas_ordenadas(db)
    mis_registros = list(
        db.scalars(
            select(Registro)
            .where(Registro.usuario_id == usuario.id)
            .options(*OPCIONES_REGISTRO)
            .order_by(Registro.fecha.desc(), Registro.id.desc())
            .limit(10)
        )
    )

    resumen, semana_inicio = resumen_semanal(db, equipo, hoy)

    # Revision: lo que el jefe tiene por revisar y lo que le devolvieron a
    # esta persona (para que se entere sin tener que buscarlo).
    por_revisar = int(
        db.scalar(
            select(func.count(Registro.id)).where(Registro.estado_revision == "pendiente")
        )
        or 0
    )
    devueltos = list(
        db.scalars(
            select(Registro)
            .where(
                Registro.usuario_id == usuario.id,
                Registro.estado_revision == REVISION_DEVUELTA,
            )
            .options(*OPCIONES_REGISTRO)
            .order_by(Registro.fecha.desc())
        )
    )

    # Solo se les reclama el reporte a quienes hoy trabajan: si no es dia
    # laborable, o estan de licencia, no corresponde.
    hoy_laborable = es_laborable(hoy)
    registrar_hoy = []
    if hoy_laborable:
        registrar_hoy = [
            persona
            for persona in equipo
            if persona.id not in ids_registraron
            and persona.rol != ROL_JEFE
            and not novedades_db.hay_novedad(db, persona.id, hoy)
        ]

    # ?repetir=<id> precarga el formulario con un registro propio: sirve para
    # repetir la carga del dia anterior sin volver a escribir todo.
    a_repetir = None
    if repetir.isdigit():
        candidato = db.get(Registro, int(repetir))
        if candidato is not None and candidato.usuario_id == usuario.id:
            a_repetir = candidato

    visibles = metas_visibles(db, usuario)
    ids_visibles = {meta.id for meta in visibles}
    # La meta del registro repetido tiene que estar en el combo aunque
    # este cerrada, sino el formulario la perderia sin avisar.
    if (
        a_repetir is not None
        and a_repetir.meta is not None
        and a_repetir.meta_id not in ids_visibles
    ):
        visibles = [a_repetir.meta] + visibles
    progreso = progreso_por_id(db, metas)

    return templates.TemplateResponse(
        request,
        "panel.html",
        contexto(
            request,
            usuario,
            equipo=equipo,
            registros_hoy=registros_hoy,
            metas_activas=[m for m in metas if m.estado == "activa"],
            progreso=progreso,
            progreso_usuario=[
                fila for fila in progreso.values() if fila["meta"].id in ids_visibles
            ],
            vencidas=metas_vencidas(
                metas if usuario.es_jefe else visibles, hoy
            ),
            mis_metas=visibles,
            mis_registros=mis_registros,
            a_repetir=a_repetir,
            hoy_laborable=es_laborable(hoy),
            registrar_hoy=registrar_hoy,
            resumen_semana=resumen,
            por_revisar=por_revisar,
            devueltos=devueltos,
            semana_inicio=semana_inicio,
            semana_fin=semana_inicio + timedelta(days=6),
            grafico=horas_por_semana(db, equipo, hoy) if usuario.es_jefe else None,
            estados_registro=ESTADOS_REGISTRO,
        ),
    )


# --------------------------------------------------------------------------
# Registros diarios
# --------------------------------------------------------------------------
@app.post("/registros")
def crear_registro(
    usuario: Usuario = Depends(requiere_login),
    db: Session = Depends(get_db),
    meta_id: str = Form(""),
    fecha: str = Form(""),
    descripcion: str = Form(...),
    horas: str = Form("0"),
    cantidad: str = Form("0"),
    estado: str = Form("en_progreso"),
):
    descripcion = descripcion.strip()
    if not descripcion:
        return ir_a("/", "La descripción no puede estar vacía")

    estados_validos = {clave for clave, _ in ESTADOS_REGISTRO}
    if estado not in estados_validos:
        estado = "en_progreso"

    id_meta = int(meta_id) if meta_id.isdigit() else None
    if id_meta is not None and db.get(Meta, id_meta) is None:
        id_meta = None

    dia = parse_fecha(fecha) or date.today()
    hoy = date.today()
    if dia > hoy:
        return ir_a("/", "No se puede registrar trabajo en una fecha futura")
    if dia < hoy - timedelta(days=config.DIAS_ATRASO):
        limite = (hoy - timedelta(days=config.DIAS_ATRASO)).strftime("%d/%m/%Y")
        return ir_a("/", f"Fuera de rango: solo se carga desde el {limite}")

    if id_meta is not None and not meta_usable(db, usuario, id_meta):
        return ir_a("/", "Esa meta no te corresponde")

    if registro_duplicado(db, usuario.id, dia, id_meta):
        return ir_a(
            "/",
            "Ya hay un registro de ese día para esa meta; eliminá el anterior o cambiá la fecha",
        )

    db.add(
        Registro(
            usuario_id=usuario.id,
            meta_id=id_meta,
            fecha=dia,
            descripcion=descripcion,
            horas=parse_horas(horas),
            cantidad=parse_numero(cantidad),
            estado=estado,
        )
    )
    db.commit()

    # Aviso de carga excesiva: se calcula despues de guardar, asi que el
    # registro ya quedo; solo se le muestra el cartel a la persona.
    aviso = aviso_de_carga(db, usuario.id, dia)
    if aviso:
        return ir_a("/", f"Registro guardado. {aviso}")
    return ir_a("/", "Registro guardado")


@app.get("/registros")
def listar_registros(
    request: Request,
    usuario: Usuario = Depends(requiere_jefe),
    db: Session = Depends(get_db),
    usuario_id: str = "",
    meta_id: str = "",
    desde: str = "",
    hasta: str = "",
    texto: str = "",
    estado: str = "",
    revision: str = "",
    page: str = "",
):
    consulta, filtros = filtrar_registros(
        usuario_id, desde, hasta, meta_id, texto, estado, revision
    )
    totales = totales_registros(db, consulta)
    paginas = max(1, -(-totales["cantidad"] // POR_PAGINA))
    pagina = min(pagina_de(page), paginas)
    registros = list(
        db.scalars(
            consulta.options(*OPCIONES_REGISTRO)
            .offset((pagina - 1) * POR_PAGINA)
            .limit(POR_PAGINA)
        )
    )
    return templates.TemplateResponse(
        request,
        "registros.html",
        contexto(
            request,
            usuario,
            registros=registros,
            equipo=list(db.scalars(select(Usuario).order_by(Usuario.nombre))),
            metas=metas_ordenadas(db),
            filtros=filtros,
            qs=qs_filtros(filtros),
            estados=ESTADOS_REGISTRO,
            pagina=pagina,
            paginas=paginas,
            por_pagina=POR_PAGINA,
            total=totales["cantidad"],
            total_horas=totales["horas"],
            total_dias=totales["dias"],
            total_comentarios=totales["comentarios"],
            total_en_fecha=totales["en_fecha"],
            mostrados=len(registros),
            meses=reportes.MESES,
        ),
    )


@app.get("/registros/exportar.xlsx")
def exportar_registros(
    usuario: Usuario = Depends(requiere_jefe),
    db: Session = Depends(get_db),
    usuario_id: str = "",
    meta_id: str = "",
    desde: str = "",
    hasta: str = "",
    texto: str = "",
    estado: str = "",
    revision: str = "",
):
    """Descarga en Excel los registros que cumplen los filtros elegidos."""
    consulta, _filtros = filtrar_registros(
        usuario_id, desde, hasta, meta_id, texto, estado, revision
    )
    totales = totales_registros(db, consulta)
    registros = list(
        db.scalars(consulta.options(*OPCIONES_REGISTRO).limit(LIMITE_EXPORTACION))
    )

    libro = Workbook()
    hoja = libro.active
    hoja.title = "Registros"
    hoja.append(
        [
            "Fecha",
            "Persona",
            "Cargo",
            "Meta",
            "Que hizo",
            "Horas",
            "Cantidad",
            "Estado",
            "Cargado el",
            "Comentario del jefe",
            "Revisión",
        ]
    )
    for celda in hoja[1]:
        celda.font = Font(bold=True)

    for r in registros:
        hoja.append(
            [
                r.fecha.strftime("%d/%m/%Y"),
                r.usuario.nombre,
                r.usuario.cargo or "",
                r.meta.titulo if r.meta else "",
                r.descripcion,
                r.horas,
                r.cantidad,
                r.estado.replace("_", " "),
                r.creado_en.strftime("%d/%m/%Y %H:%M") if r.creado_en else "",
                r.comentario or "",
                dict(ESTADOS_REVISION).get(r.estado_revision, r.estado_revision),
            ]
        )

    hoja.append([])
    hoja.append(
        ["", "", "", "", "TOTAL HORAS", round(totales["horas"], 2)]
    )
    if len(registros) < totales["cantidad"]:
        hoja.append(
            [
                "",
                "",
                "",
                "",
                "AVISO",
                f"El detalle trae los primeros {len(registros)} de "
                f"{totales['cantidad']} registros; el total de arriba si cuenta todos.",
            ]
        )

    for columna, ancho in zip(
        "ABCDEFGHIJK",
        [12, 24, 20, 34, 58, 9, 11, 14, 18, 42, 20],
        strict=True,
    ):
        hoja.column_dimensions[columna].width = ancho
    hoja.freeze_panes = "A2"

    buffer = BytesIO()
    libro.save(buffer)

    nombre = f"registros_{date.today().isoformat()}.xlsx"
    return Response(
        content=buffer.getvalue(),
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


@app.get("/calendario")
def calendario(
    request: Request,
    usuario: Usuario = Depends(requiere_jefe),
    db: Session = Depends(get_db),
    anio: str = "",
    mes: str = "",
):
    """Calendario de carga: quien reporto y cuantas horas, dia por dia."""
    hoy = date.today()

    try:
        anio_num = int(anio) if anio else hoy.year
        mes_num = int(mes) if mes else hoy.month
    except ValueError:
        anio_num, mes_num = hoy.year, hoy.month

    if not 2000 <= anio_num <= 2100 or not 1 <= mes_num <= 12:
        return ir_a("/calendario", "Periodo no valido")

    equipo = list(
        db.scalars(
            select(Usuario).where(Usuario.activo.is_(True)).order_by(Usuario.nombre)
        )
    )
    cal = calendario_mes(db, equipo, anio_num, mes_num)

    primero = date(anio_num, mes_num, 1)
    ultimo = date(anio_num, mes_num, calendar.monthrange(anio_num, mes_num)[1])
    anterior = primero - timedelta(days=1)
    siguiente = ultimo + timedelta(days=1)

    return templates.TemplateResponse(
        request,
        "calendario.html",
        contexto(
            request,
            usuario,
            cal=cal,
            meses=reportes.MESES,
            anio=anio_num,
            mes=mes_num,
            anio_anterior=anterior.year,
            mes_anterior=anterior.month,
            anio_siguiente=siguiente.year,
            mes_siguiente=siguiente.month,
        ),
    )


@app.post("/registros/{registro_id}/eliminar")
def eliminar_registro(
    registro_id: int,
    usuario: Usuario = Depends(requiere_login),
    db: Session = Depends(get_db),
    volver: str = Form("/"),
):
    destino = volver_a(volver)
    registro = db.get(Registro, registro_id)
    if registro is None:
        return ir_a(destino, "Ese registro ya no existe")
    if not usuario.es_jefe and registro.usuario_id != usuario.id:
        return ir_a(destino, "No puedes eliminar registros de otra persona")
    db.delete(registro)
    auditoria.registrar(
        db,
        usuario,
        "eliminar_registro",
        "registro",
        registro.id,
        f"{registro.fecha.isoformat()}: {registro.descripcion}"[:255],
    )
    db.commit()
    return ir_a(destino, "Registro eliminado")


@app.post("/registros/{registro_id}/comentario")
def comentar_registro(
    registro_id: int,
    usuario: Usuario = Depends(requiere_jefe),
    db: Session = Depends(get_db),
    comentario: str = Form(""),
    volver: str = Form("/"),
):
    """El jefe deja una observacion sobre el reporte de una persona."""
    destino = volver_a(volver, "/registros")
    registro = db.get(Registro, registro_id)
    if registro is None:
        return ir_a(destino, "Ese registro ya no existe")

    texto = comentario.strip()[:500]
    if texto:
        registro.comentario = texto
        registro.comentado_en = datetime.now()
        mensaje = "Comentario guardado"
    else:
        registro.comentario = ""
        registro.comentado_en = None
        mensaje = "Comentario borrado"
    auditoria.registrar(
        db,
        usuario,
        "comentar_registro",
        "registro",
        registro.id,
        (texto or "borro el comentario")[:255],
    )
    db.commit()
    return ir_a(destino, mensaje)


# --------------------------------------------------------------------------
# Revision del trabajo: el jefe aprueba o devuelve, la persona corrige
# --------------------------------------------------------------------------
@app.post("/registros/{registro_id}/revisar")
def revisar_registro(
    registro_id: int,
    usuario: Usuario = Depends(requiere_jefe),
    db: Session = Depends(get_db),
    estado_revision: str = Form(...),
    observacion: str = Form(""),
    volver: str = Form("/registros"),
):
    """El jefe aprueba el reporte o lo devuelve para que lo corrijan.

    Devolverlo (``correccion_pendiente``) es la reversion del progreso: el
    reporte deja de sumar para el avance de la meta hasta que se corrija.
    """
    destino = volver_a(volver, "/registros")
    registro = db.get(Registro, registro_id)
    if registro is None:
        return ir_a(destino, "Ese registro ya no existe")

    if estado_revision not in {"aprobado", REVISION_DEVUELTA}:
        return ir_a(destino, "Estado de revisión inválido")

    observacion = observacion.strip()[:500]
    if estado_revision == REVISION_DEVUELTA and not observacion:
        return ir_a(destino, "Escribí qué hay que corregir antes de devolverlo")

    registro.estado_revision = estado_revision
    registro.revisado_por = usuario.id
    registro.revisado_en = datetime.now()
    registro.observacion_revision = observacion
    auditoria.registrar(
        db,
        usuario,
        "revisar_registro",
        "registro",
        registro.id,
        (f"{registro.fecha.isoformat()}: {estado_revision} {observacion}")[:255],
    )
    db.commit()
    return ir_a(
        destino,
        "Reporte aprobado"
        if estado_revision == "aprobado"
        else "Reporte devuelto para corrección",
    )


@app.get("/registros/{registro_id}/corregir")
def corregir_registro_form(
    registro_id: int,
    request: Request,
    usuario: Usuario = Depends(requiere_login),
    db: Session = Depends(get_db),
):
    """Formulario para que la persona arregle un reporte devuelto."""
    registro = db.get(Registro, registro_id)
    if registro is None:
        return ir_a("/", "Ese registro ya no existe")
    if not puede_corregir(usuario, registro):
        return ir_a("/", "No puedes corregir registros de otra persona")
    return templates.TemplateResponse(
        request,
        "corregir.html",
        contexto(
            request,
            usuario,
            registro=registro,
            estados_registro=ESTADOS_REGISTRO,
        ),
    )


@app.post("/registros/{registro_id}/corregir")
def corregir_registro(
    registro_id: int,
    usuario: Usuario = Depends(requiere_login),
    db: Session = Depends(get_db),
    descripcion: str = Form(...),
    horas: str = Form("0"),
    cantidad: str = Form("0"),
    estado: str = Form("en_progreso"),
):
    """Guarda la corrección y vuelve a mandar el reporte a revisión."""
    registro = db.get(Registro, registro_id)
    if registro is None:
        return ir_a("/", "Ese registro ya no existe")
    if not puede_corregir(usuario, registro):
        return ir_a("/", "No puedes corregir registros de otra persona")

    descripcion = descripcion.strip()
    if not descripcion:
        return ir_a(f"/registros/{registro.id}/corregir", "La descripción no puede estar vacía")
    if estado not in {clave for clave, _ in ESTADOS_REGISTRO}:
        return ir_a(f"/registros/{registro.id}/corregir", "Estado inválido")

    registro.descripcion = descripcion
    registro.horas = parse_horas(horas)
    registro.cantidad = parse_numero(cantidad)
    registro.estado = estado
    # Vuelve a la bandeja del jefe. La observación queda como historial de lo
    # que se pidió, así el jefe ve qué se contestó.
    registro.estado_revision = "pendiente"
    registro.revisado_por = None
    registro.revisado_en = None
    auditoria.registrar(
        db,
        usuario,
        "corregir_registro",
        "registro",
        registro.id,
        f"{registro.fecha.isoformat()}: {descripcion}"[:255],
    )
    db.commit()
    return ir_a("/", "Corrección enviada: queda pendiente de revisión")


# --------------------------------------------------------------------------
# Metas (solo jefe)
# --------------------------------------------------------------------------
@app.get("/metas")
def metas(
    request: Request,
    usuario: Usuario = Depends(requiere_jefe),
    db: Session = Depends(get_db),
):
    todas = metas_ordenadas(db, incluir_eliminadas=True)
    return templates.TemplateResponse(
        request,
        "metas.html",
        contexto(
            request,
            usuario,
            metas=todas,
            archivadas=sum(1 for meta in todas if meta.estado == ESTADO_ELIMINADA),
            progreso=progreso_por_id(db, todas),
            equipo=empleados_activos(db),
        ),
    )


@app.get("/metas/progreso")
def progreso(
    request: Request,
    usuario: Usuario = Depends(requiere_jefe),
    db: Session = Depends(get_db),
    ver: str = "activas",
):
    todas = metas_ordenadas(db)
    if ver == "activas":
        todas = [meta for meta in todas if meta.estado == "activa"]

    filas = progreso_metas(db, todas)
    promedio = round(sum(fila["avance"] for fila in filas) / len(filas)) if filas else 0

    return templates.TemplateResponse(
        request,
        "progreso.html",
        contexto(
            request,
            usuario,
            filas=filas,
            ver=ver,
            total=len(filas),
            promedio=promedio,
            horas_acumuladas=sum(fila["horas"] for fila in filas),
            horas_estimadas=sum((fila["meta"].horas_estimadas or 0) for fila in filas),
            total_reportes=sum(fila["reportes"] for fila in filas),
        ),
    )


@app.post("/metas")
def crear_meta(
    usuario: Usuario = Depends(requiere_jefe),
    db: Session = Depends(get_db),
    titulo: str = Form(...),
    descripcion: str = Form(""),
    asignado_a: str = Form(""),
    fecha_inicio: str = Form(""),
    fecha_limite: str = Form(""),
    horas_estimadas: str = Form(""),
    objetivo: str = Form(""),
    unidad: str = Form(""),
):
    titulo = titulo.strip()
    if not titulo:
        return ir_a("/metas", "La meta necesita un título")

    id_asignado = int(asignado_a) if asignado_a.isdigit() else None
    if id_asignado is not None and db.get(Usuario, id_asignado) is None:
        id_asignado = None

    meta = Meta(
        titulo=titulo,
        descripcion=descripcion.strip(),
        asignado_a=id_asignado,
        fecha_inicio=parse_fecha(fecha_inicio),
        fecha_limite=parse_fecha(fecha_limite),
        horas_estimadas=parse_numero(horas_estimadas),
        objetivo=parse_numero(objetivo),
        unidad=unidad.strip()[:30],
    )
    db.add(meta)
    auditoria.registrar(db, usuario, "crear_meta", "meta", resumen=titulo)
    db.commit()
    return ir_a("/metas", "Meta creada")


@app.post("/metas/{meta_id}/estado")
def cambiar_estado_meta(
    meta_id: int,
    usuario: Usuario = Depends(requiere_jefe),
    db: Session = Depends(get_db),
    estado: str = Form(...),
):
    meta = db.get(Meta, meta_id)
    if meta is None:
        return ir_a("/metas", "Esa meta ya no existe")
    if estado not in ESTADOS_META:
        return ir_a("/metas", "Estado inválido")
    meta.estado = estado
    auditoria.registrar(
        db, usuario, "editar_meta", "meta", meta.id, f"{meta.titulo} -> {estado}"
    )
    db.commit()
    return ir_a("/metas", f"Meta marcada como {estado}")


@app.post("/metas/{meta_id}/eliminar")
def eliminar_meta(
    meta_id: int,
    usuario: Usuario = Depends(requiere_jefe),
    db: Session = Depends(get_db),
):
    meta = db.get(Meta, meta_id)
    if meta is None:
        return ir_a("/metas", "Esa meta ya no existe")
    # Borrado logico: se archiva en vez de borrar, para no perder los reportes
    # ni el vinculo con la meta. Se revierte con "Restaurar" o en Editar.
    meta.estado = ESTADO_ELIMINADA
    auditoria.registrar(db, usuario, "archivar_meta", "meta", meta.id, meta.titulo)
    db.commit()
    return ir_a("/metas", "Meta archivada (sus reportes se conservan y se puede restaurar)")


@app.post("/metas/{meta_id}/duplicar")
def duplicar_meta(
    meta_id: int,
    usuario: Usuario = Depends(requiere_jefe),
    db: Session = Depends(get_db),
):
    """Copia una meta para no volver a cargarla a mano.

    Las metas cambian de numero de corte, de mes y de anio, asi que la copia
    se abre directo en el formulario de edicion para ajustar titulo y fechas.
    """
    original = db.get(Meta, meta_id)
    if original is None:
        return ir_a("/metas", "Esa meta ya no existe")

    copia = Meta(
        titulo=f"{original.titulo} (copia)"[:140],
        descripcion=original.descripcion,
        asignado_a=original.asignado_a,
        fecha_inicio=original.fecha_inicio,
        fecha_limite=original.fecha_limite,
        horas_estimadas=original.horas_estimadas or 0.0,
        objetivo=original.objetivo or 0.0,
        unidad=original.unidad,
        # La copia arranca siempre activa, aunque el original este cerrado.
        estado="activa",
    )
    db.add(copia)
    auditoria.registrar(
        db,
        usuario,
        "duplicar_meta",
        "meta",
        resumen=f"Copia de: {original.titulo}",
    )
    db.commit()
    return ir_a(f"/metas/{copia.id}/editar", "Meta duplicada, ajuste titulo y fechas")


@app.get("/metas/{meta_id}/editar")
def meta_editar_form(
    meta_id: int,
    request: Request,
    usuario: Usuario = Depends(requiere_jefe),
    db: Session = Depends(get_db),
):
    meta = db.get(Meta, meta_id)
    if meta is None:
        return ir_a("/metas", "Esa meta ya no existe")
    return templates.TemplateResponse(
        request,
        "meta_editar.html",
        contexto(
            request,
            usuario,
            meta=meta,
            equipo=empleados_activos(db),
            progreso=progreso_por_id(db, [meta]).get(meta.id),
            registros=list(
                db.scalars(
                    select(Registro)
                    .where(Registro.meta_id == meta.id)
                    .options(*OPCIONES_REGISTRO)
                    .order_by(Registro.fecha.desc(), Registro.id.desc())
                    .limit(50)
                )
            ),
        ),
    )


@app.post("/metas/{meta_id}")
def meta_editar(
    meta_id: int,
    usuario: Usuario = Depends(requiere_jefe),
    db: Session = Depends(get_db),
    titulo: str = Form(...),
    descripcion: str = Form(""),
    asignado_a: str = Form(""),
    fecha_inicio: str = Form(""),
    fecha_limite: str = Form(""),
    horas_estimadas: str = Form(""),
    objetivo: str = Form(""),
    unidad: str = Form(""),
    estado: str = Form("activa"),
):
    meta = db.get(Meta, meta_id)
    if meta is None:
        return ir_a("/metas", "Esa meta ya no existe")

    titulo = titulo.strip()
    if not titulo:
        return ir_a(f"/metas/{meta_id}/editar", "La meta necesita un título")

    id_asignado = int(asignado_a) if asignado_a.isdigit() else None
    if id_asignado is not None and db.get(Usuario, id_asignado) is None:
        id_asignado = None

    meta.titulo = titulo
    meta.descripcion = descripcion.strip()
    meta.asignado_a = id_asignado
    meta.fecha_inicio = parse_fecha(fecha_inicio)
    meta.fecha_limite = parse_fecha(fecha_limite)
    meta.horas_estimadas = parse_numero(horas_estimadas)
    meta.objetivo = parse_numero(objetivo)
    meta.unidad = unidad.strip()[:30]
    if estado in ESTADOS_META:
        meta.estado = estado
    auditoria.registrar(db, usuario, "editar_meta", "meta", meta.id, meta.titulo)
    db.commit()
    return ir_a("/metas", "Meta actualizada")


# --------------------------------------------------------------------------
# Equipo y perfil
# --------------------------------------------------------------------------
@app.get("/equipo")
def equipo(
    request: Request,
    usuario: Usuario = Depends(requiere_jefe),
    db: Session = Depends(get_db),
):
    return templates.TemplateResponse(
        request,
        "equipo.html",
        contexto(
            request,
            usuario,
            equipo=list(
                db.scalars(select(Usuario).order_by(Usuario.rol, Usuario.nombre))
            ),
        ),
    )


@app.post("/equipo")
def crear_usuario(
    usuario: Usuario = Depends(requiere_jefe),
    db: Session = Depends(get_db),
    nombre: str = Form(...),
    usuario_input: str = Form(..., alias="usuario"),
    cargo: str = Form(""),
    pin: str = Form(...),
    rol: str = Form(ROL_EMPLEADO),
):
    nombre = nombre.strip()
    login_nombre = usuario_input.strip().lower().replace(" ", "")
    if not nombre or not login_nombre:
        return ir_a("/equipo", "Nombre y usuario son obligatorios")
    if db.scalar(select(Usuario).where(Usuario.usuario == login_nombre)):
        return ir_a("/equipo", "Ese usuario ya existe")
    error_pin = valida_pin(pin)
    if error_pin:
        return ir_a("/equipo", error_pin)
    if rol not in {ROL_JEFE, ROL_EMPLEADO}:
        rol = ROL_EMPLEADO

    nuevo = Usuario(
        nombre=nombre,
        usuario=login_nombre,
        cargo=cargo.strip(),
        pin_hash=hash_pin(pin),
        rol=rol,
    )
    db.add(nuevo)
    auditoria.registrar(db, usuario, "crear_usuario", "usuario", resumen=login_nombre)
    db.commit()
    return ir_a("/equipo", f"Usuario {nombre} creado")


@app.post("/equipo/{usuario_id}/pin")
def resetear_pin(
    usuario_id: int,
    usuario: Usuario = Depends(requiere_jefe),
    db: Session = Depends(get_db),
    pin: str = Form(...),
):
    destino = db.get(Usuario, usuario_id)
    if destino is None:
        return ir_a("/equipo", "Ese usuario no existe")
    error_pin = valida_pin(pin)
    if error_pin:
        return ir_a("/equipo", error_pin)
    destino.pin_hash = hash_pin(pin)
    # Corta la sesion que esa persona tuviera abierta con el PIN viejo.
    destino.sesion_token = nuevo_token_de_sesion()
    olvidar_pin_de_fabrica(destino.id)
    if destino.usuario == config.ADMIN_USUARIO:
        borrar_primer_ingreso()
    auditoria.registrar(db, usuario, "cambiar_pin", "usuario", destino.id, destino.nombre)
    db.commit()
    return ir_a("/equipo", f"PIN de {destino.nombre} actualizado")


@app.post("/equipo/{usuario_id}/activo")
def alternar_activo(
    usuario_id: int,
    usuario: Usuario = Depends(requiere_jefe),
    db: Session = Depends(get_db),
):
    destino = db.get(Usuario, usuario_id)
    if destino is None:
        return ir_a("/equipo", "Ese usuario no existe")
    if destino.id == usuario.id:
        return ir_a("/equipo", "No puedes desactivar tu propio usuario")
    destino.activo = not destino.activo
    auditoria.registrar(
        db,
        usuario,
        "cambiar_estado_usuario",
        "usuario",
        destino.id,
        f"{destino.nombre}: {'activo' if destino.activo else 'inactivo'}",
    )
    db.commit()
    return ir_a("/equipo", f"{destino.nombre} {'activado' if destino.activo else 'desactivado'}")


@app.get("/personas/{usuario_id}")
def persona_detalle(
    request: Request,
    usuario_id: int,
    usuario: Usuario = Depends(requiere_jefe),
    db: Session = Depends(get_db),
    desde: str = "",
    hasta: str = "",
):
    """Historial completo de una persona: sus reportes, comentarios y metas."""
    persona = db.get(Usuario, usuario_id)
    if persona is None:
        return ir_a("/equipo", "Ese usuario no existe")

    consulta, filtros = filtrar_registros(str(usuario_id), desde, hasta)
    totales = totales_registros(db, consulta)
    registros = list(
        db.scalars(consulta.options(*OPCIONES_REGISTRO).limit(LIMITE_HISTORIAL))
    )

    metas = list(
        db.scalars(
            select(Meta)
            .where(
                or_(Meta.asignado_a == usuario_id, Meta.asignado_a.is_(None)),
                Meta.estado != ESTADO_ELIMINADA,
            )
            .options(*OPCIONES_META)
            .order_by(Meta.estado, Meta.fecha_limite.is_(None), Meta.fecha_limite)
        )
    )

    return templates.TemplateResponse(
        request,
        "persona.html",
        contexto(
            request,
            usuario,
            persona=persona,
            registros=registros,
            filtros=filtros,
            # Solo fechas: usuario_id ya viene puesto en la direccion de la
            # ficha y no hace falta repetirlo en los enlaces.
            qs=qs_filtros({k: v for k, v in filtros.items() if k != "usuario_id"}),
            metas=progreso_metas(db, metas),
            total=totales["cantidad"],
            total_horas=totales["horas"],
            dias=totales["dias"],
            total_comentarios=totales["comentarios"],
            puntualidad=puntualidad(
                db,
                usuario_id,
                parse_fecha(desde) or date(2000, 1, 1),
                parse_fecha(hasta) or date.today(),
            ),
            mostrados=len(registros),
            limite=LIMITE_HISTORIAL,
            meses=reportes.MESES,
        ),
    )


@app.get("/personas/{usuario_id}/reporte.pdf")
def reporte_persona_pdf(
    usuario_id: int,
    usuario: Usuario = Depends(requiere_jefe),
    db: Session = Depends(get_db),
    anio: str = "",
    mes: str = "",
):
    """PDF mensual de una persona, para enviarselo desde su ficha."""
    persona = db.get(Usuario, usuario_id)
    if persona is None:
        return ir_a("/equipo", "Ese usuario no existe")

    hoy = date.today()
    try:
        anio_num = int(anio) if anio else hoy.year
        mes_num = int(mes) if mes else hoy.month
    except ValueError:
        anio_num, mes_num = hoy.year, hoy.month
    if not 2000 <= anio_num <= 2100 or not 1 <= mes_num <= 12:
        return ir_a(f"/personas/{persona.id}", "Periodo invalido")

    pdf = reportes.generar_pdf_persona(db, persona, anio_num, mes_num)
    nombre = f"reporte_{persona.usuario}_{anio_num}-{mes_num:02d}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


@app.get("/auditoria")
def auditoria_pagina(
    request: Request,
    usuario: Usuario = Depends(requiere_jefe),
    db: Session = Depends(get_db),
    usuario_id: str = "",
    desde: str = "",
    hasta: str = "",
    accion: str = "",
    page: str = "",
):
    """Quien hizo que: la trazabilidad de las acciones que cambian datos."""
    consulta = select(Auditoria).order_by(Auditoria.fecha.desc(), Auditoria.id.desc())
    filtros: dict = {}

    if (usuario_id or "").isdigit():
        consulta = consulta.where(Auditoria.usuario_id == int(usuario_id))
        filtros["usuario_id"] = int(usuario_id)

    f_desde = parse_fecha(desde)
    if f_desde:
        consulta = consulta.where(
            Auditoria.fecha >= datetime(f_desde.year, f_desde.month, f_desde.day)
        )
        filtros["desde"] = f_desde

    f_hasta = parse_fecha(hasta)
    if f_hasta:
        consulta = consulta.where(
            Auditoria.fecha
            < datetime(f_hasta.year, f_hasta.month, f_hasta.day) + timedelta(days=1)
        )
        filtros["hasta"] = f_hasta

    accion = (accion or "").strip()
    if accion in {clave for clave, _ in ACCIONES_AUDITORIA}:
        consulta = consulta.where(Auditoria.accion == accion)
        filtros["accion"] = accion

    cantidad = int(
        db.scalar(consulta.with_only_columns(func.count(Auditoria.id)).order_by(None))
        or 0
    )
    paginas = max(1, -(-cantidad // POR_PAGINA))
    pagina = min(pagina_de(page), paginas)
    filas = list(
        db.scalars(
            consulta.options(*OPCIONES_AUDITORIA)
            .offset((pagina - 1) * POR_PAGINA)
            .limit(POR_PAGINA)
        )
    )

    return templates.TemplateResponse(
        request,
        "auditoria.html",
        contexto(
            request,
            usuario,
            filas=filas,
            equipo=list(db.scalars(select(Usuario).order_by(Usuario.nombre))),
            acciones=ACCIONES_AUDITORIA,
            etiquetas=dict(ACCIONES_AUDITORIA),
            filtros=filtros,
            qs=qs_filtros(filtros),
            pagina=pagina,
            paginas=paginas,
            total=cantidad,
            mostrados=len(filas),
        ),
    )


# --------------------------------------------------------------------------
# Novedades del equipo (vacaciones, licencias, feriados) - solo jefe
# --------------------------------------------------------------------------
@app.get("/novedades")
def novedades_pagina(
    request: Request,
    usuario: Usuario = Depends(requiere_jefe),
    db: Session = Depends(get_db),
):
    """Dias en que no se le exige reportar a alguien.

    Sin esto, quien esta de licencia o una semana con feriado aparece como
    incumplidor en el panel.
    """
    return templates.TemplateResponse(
        request,
        "novedades.html",
        contexto(
            request,
            usuario,
            novedades=list(
                db.scalars(
                    select(Novedad)
                    .options(*OPCIONES_NOVEDAD)
                    .order_by(Novedad.desde.desc(), Novedad.id.desc())
                )
            ),
            equipo=list(db.scalars(select(Usuario).order_by(Usuario.nombre))),
            tipos=TIPOS_NOVEDAD,
            etiquetas=dict(TIPOS_NOVEDAD),
            hoy=date.today(),
        ),
    )


@app.post("/novedades")
def crear_novedad(
    usuario: Usuario = Depends(requiere_jefe),
    db: Session = Depends(get_db),
    usuario_id: str = Form(""),
    tipo: str = Form("otro"),
    desde: str = Form(""),
    hasta: str = Form(""),
    detalle: str = Form(""),
):
    id_persona = int(usuario_id) if usuario_id.isdigit() else None
    if id_persona is not None and db.get(Usuario, id_persona) is None:
        id_persona = None
    if tipo not in {clave for clave, _ in TIPOS_NOVEDAD}:
        return ir_a("/novedades", "Tipo de novedad inválido")

    f_desde = parse_fecha(desde)
    f_hasta = parse_fecha(hasta) or f_desde
    if f_desde is None:
        return ir_a("/novedades", "Poné desde cuándo es la novedad")
    if f_hasta < f_desde:
        return ir_a("/novedades", "La fecha de fin es anterior a la de inicio")

    db.add(
        Novedad(
            usuario_id=id_persona,
            tipo=tipo,
            desde=f_desde,
            hasta=f_hasta,
            detalle=detalle.strip()[:140],
        )
    )
    auditoria.registrar(
        db,
        usuario,
        "crear_novedad",
        "novedad",
        resumen=f"{tipo}: {f_desde.isoformat()} a {f_hasta.isoformat()}",
    )
    db.commit()
    return ir_a("/novedades", "Novedad cargada")


@app.post("/novedades/{novedad_id}/eliminar")
def eliminar_novedad(
    novedad_id: int,
    usuario: Usuario = Depends(requiere_jefe),
    db: Session = Depends(get_db),
):
    novedad = db.get(Novedad, novedad_id)
    if novedad is None:
        return ir_a("/novedades", "Esa novedad ya no existe")
    resumen = f"{novedad.tipo}: {novedad.desde.isoformat()} a {novedad.hasta.isoformat()}"
    db.delete(novedad)
    auditoria.registrar(db, usuario, "eliminar_novedad", "novedad", novedad.id, resumen)
    db.commit()
    return ir_a("/novedades", "Novedad borrada")


@app.get("/guia")
def guia(request: Request, usuario: Usuario = Depends(requiere_login)):
    """Instructivo corto, pensado para que lo lea el equipo."""
    return templates.TemplateResponse(
        request,
        "guia.html",
        contexto(
            request,
            usuario,
            direcciones=[
                f"http://{ip}:{config.PORT}" for ip in ips_locales()
            ],
        ),
    )


@app.post("/mi-pin")
def cambiar_mi_pin(
    request: Request,
    usuario: Usuario = Depends(requiere_login),
    db: Session = Depends(get_db),
    pin_actual: str = Form(...),
    pin_nuevo: str = Form(...),
):
    if not verificar_pin(pin_actual, usuario.pin_hash):
        return ir_a("/ayuda", "Tu PIN actual no coincide")
    error_pin = valida_pin(pin_nuevo)
    if error_pin:
        return ir_a("/ayuda", error_pin)
    usuario.pin_hash = hash_pin(pin_nuevo)
    # Se renueva el token para cortar otras sesiones, pero esta sigue viva: el
    # que acaba de cambiar su propio PIN no tiene por que volver a entrar.
    usuario.sesion_token = nuevo_token_de_sesion()
    request.session["sesion_token"] = usuario.sesion_token
    olvidar_pin_de_fabrica(usuario.id)
    if usuario.usuario == config.ADMIN_USUARIO:
        borrar_primer_ingreso()
    auditoria.registrar(db, usuario, "cambiar_pin", "usuario", usuario.id, usuario.nombre)
    db.commit()
    return ir_a("/ayuda", "PIN actualizado")


# --------------------------------------------------------------------------
# Respaldos de la base de datos
# --------------------------------------------------------------------------
@app.get("/respaldos")
def respaldos(
    request: Request,
    usuario: Usuario = Depends(requiere_jefe),
):
    return templates.TemplateResponse(
        request,
        "respaldos.html",
        contexto(
            request,
            usuario,
            respaldos=backup.listar_respaldos(),
            carpeta=str(config.BACKUP_DIR),
            archivo_base=str(config.DATA_DIR / "control.db"),
            horas=config.BACKUP_HORAS,
            conservar=config.BACKUP_CONSERVAR,
            mismo_disco=backup.respaldos_en_mismo_disco(),
        ),
    )


@app.post("/respaldos/ahora")
def respaldo_ahora(
    usuario: Usuario = Depends(requiere_jefe),
    db: Session = Depends(get_db),
):
    try:
        ruta = backup.crear_respaldo(etiqueta="manual")
        backup.limpiar_respaldos_antiguos()
    except Exception as error:  # noqa: BLE001 - se informa al usuario, no se cae
        return ir_a("/respaldos", f"No se pudo crear el respaldo: {error}")
    auditoria.registrar(db, usuario, "crear_respaldo", "respaldo", resumen=ruta.name)
    db.commit()
    return ir_a("/respaldos", f"Respaldo creado: {ruta.name}")


@app.post("/respaldos/restaurar")
def restaurar_respaldo(
    usuario: Usuario = Depends(requiere_jefe),
    db: Session = Depends(get_db),
    nombre: str = Form(...),
):
    """Vuelve la base al estado de un respaldo guardado."""
    # La conexion de este pedido queda abierta arriba (la pidio requiere_jefe).
    # En Windows no se puede reemplazar el archivo de la base mientras este
    # abierto, asi que se devuelve al pool antes de restaurar.
    db.close()
    try:
        seguridad = backup.restaurar_respaldo(nombre)
        backup.limpiar_respaldos_antiguos()
    except Exception as error:  # noqa: BLE001 - se informa al usuario, no se cae
        return ir_a("/respaldos", f"No se pudo restaurar: {error}")
    # La base que habia quedo reemplazada, asi que la fila va en una sesion
    # nueva y despues del restaurar: si fuera antes, se perderia.
    db_nuevo = SessionLocal()
    try:
        auditoria.registrar(
            db_nuevo, usuario, "restaurar_respaldo", "respaldo", resumen=nombre
        )
        db_nuevo.commit()
    finally:
        db_nuevo.close()
    return ir_a(
        "/respaldos",
        f"Base restaurada desde {nombre}. Deje una copia previa: {seguridad.name}",
    )


# --------------------------------------------------------------------------
# Informes por rango de fechas
# --------------------------------------------------------------------------
# Un informe de gestion no necesita mas que eso: pedir tres anos de registros
# de una vez solo llenaria la memoria sin decir nada util.
MAX_DIAS_INFORME = 1095


def rango_informe(desde: str, hasta: str) -> tuple[date, date] | None:
    """Fechas del informe a partir de lo que vino en la direccion.

    Sin fechas se usa el mes en curso. Si vienen al reves se dan vuelta (es un
    error de tipeo, no hace falta rechazarlo) y si el rango es enorme devuelve
    None para que la ruta avise.
    """
    hoy = date.today()
    inicio = parse_fecha(desde)
    fin = parse_fecha(hasta)
    if inicio is None and fin is None:
        return hoy.replace(day=1), hoy
    if inicio is None:
        inicio = fin.replace(day=1)
    if fin is None:
        fin = max(hoy, inicio)
    if fin < inicio:
        inicio, fin = fin, inicio
    if (fin - inicio).days + 1 > MAX_DIAS_INFORME:
        return None
    return inicio, fin


@app.get("/reportes")
def informes(
    request: Request,
    usuario: Usuario = Depends(requiere_jefe),
    db: Session = Depends(get_db),
    desde: str = "",
    hasta: str = "",
    comparar: str = "",
):
    """Informe de un rango de fechas libre, con comparacion opcional."""
    rango = rango_informe(desde, hasta)
    if rango is None:
        return ir_a("/reportes", "Rango de fechas demasiado largo")
    inicio, fin = rango

    quiere_comparar = comparar not in ("", "0")
    parametros = f"desde={inicio.isoformat()}&hasta={fin.isoformat()}"
    if quiere_comparar:
        parametros += "&comparar=1"

    return templates.TemplateResponse(
        request,
        "reportes.html",
        contexto(
            request,
            usuario,
            desde=inicio,
            hasta=fin,
            comparar=quiere_comparar,
            resumen=reportes.resumen_periodo(db, inicio, fin),
            comparacion=reportes.comparativa(db, inicio, fin) if quiere_comparar else None,
            qs_pdf=parametros,
            max_dias=MAX_DIAS_INFORME,
        ),
    )


@app.get("/reportes/rango.pdf")
def reporte_rango_pdf(
    usuario: Usuario = Depends(requiere_jefe),
    db: Session = Depends(get_db),
    desde: str = "",
    hasta: str = "",
    comparar: str = "",
):
    """PDF del mismo informe de rango que se ve en pantalla."""
    rango = rango_informe(desde, hasta)
    if rango is None:
        return ir_a("/reportes", "Rango de fechas demasiado largo")
    inicio, fin = rango

    pdf = reportes.generar_pdf_rango(
        db, inicio, fin, comparar=comparar not in ("", "0")
    )
    nombre = f"informe_{inicio.isoformat()}_{fin.isoformat()}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


# --------------------------------------------------------------------------
# Reporte mensual en PDF
# --------------------------------------------------------------------------
@app.get("/reportes/mensual.pdf")
def reporte_mensual_pdf(
    usuario: Usuario = Depends(requiere_jefe),
    db: Session = Depends(get_db),
    anio: str = "",
    mes: str = "",
):
    hoy = date.today()
    try:
        anio_num = int(anio) if anio else hoy.year
        mes_num = int(mes) if mes else hoy.month
    except ValueError:
        anio_num, mes_num = hoy.year, hoy.month
    if not 2000 <= anio_num <= 2100 or not 1 <= mes_num <= 12:
        return ir_a("/registros", "Periodo invalido")

    pdf = reportes.generar_pdf_mensual(db, anio_num, mes_num)
    nombre = f"reporte_{anio_num}-{mes_num:02d}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


# --------------------------------------------------------------------------
# Textos legales (públicos: se leen sin iniciar sesión)
# --------------------------------------------------------------------------
@app.get("/legal/{documento}")
def legal(request: Request, documento: str):
    """Política de privacidad, cookies, términos y licencia.

    No depende del login a propósito: son las condiciones que hay que poder
    leer antes de usar el sistema, y el pie de la pantalla de entrada apunta
    acá.
    """
    titulos = dict(DOCUMENTOS_LEGALES)
    if documento not in titulos:
        raise HTTPException(status_code=404, detail="Ese documento no existe")
    return templates.TemplateResponse(
        request,
        f"legal/{documento}.html",
        contexto(
            request,
            None,
            titulo=titulos[documento],
            documento=documento,
            version_legal=VERSION_LEGAL,
            actualizado_legal=ACTUALIZADO_LEGAL,
        ),
    )


# --------------------------------------------------------------------------
# Ayuda: cómo conectarse desde otra PC
# --------------------------------------------------------------------------
@app.get("/ayuda")
def ayuda(request: Request, usuario: Usuario = Depends(requiere_login)):
    return templates.TemplateResponse(
        request,
        "ayuda.html",
        contexto(
            request,
            usuario,
            ips=ips_locales(),
            puerto=config.PORT,
        ),
    )
