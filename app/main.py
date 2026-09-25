"""Aplicación FastAPI de Control de Gestión (uso interno, red LAN)."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path
from urllib.parse import quote

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from openpyxl import Workbook
from openpyxl.styles import Font
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from . import backup, config, reportes
from .database import Base, engine, get_db
from .metricas import horas_por_semana, resumen_semanal
from .migraciones import aplicar_migraciones
from .progreso import metas_vencidas, progreso_metas, progreso_por_id
from .models import (
    ESTADOS_META,
    ESTADOS_REGISTRO,
    ROL_EMPLEADO,
    ROL_JEFE,
    Meta,
    Registro,
    Usuario,
)
from .security import hash_pin, ips_locales, valida_pin, verificar_pin
from .seed import crear_datos_iniciales

APP_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    aplicar_migraciones()
    crear_datos_iniciales()
    tarea_respaldo = asyncio.create_task(backup.respaldo_periodico())
    try:
        yield
    finally:
        tarea_respaldo.cancel()
        with suppress(asyncio.CancelledError):
            await tarea_respaldo


app = FastAPI(title=config.APP_NAME, lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=config.SECRET_KEY)
app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")


# --------------------------------------------------------------------------
# Autenticación
# --------------------------------------------------------------------------
def usuario_actual(request: Request, db: Session = Depends(get_db)) -> Usuario | None:
    uid = request.session.get("usuario_id")
    if not uid:
        return None
    usuario = db.get(Usuario, uid)
    if usuario is None or not usuario.activo:
        request.session.clear()
        return None
    return usuario


def requiere_login(usuario: Usuario | None = Depends(usuario_actual)) -> Usuario:
    if usuario is None:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return usuario


def requiere_jefe(usuario: Usuario = Depends(requiere_login)) -> Usuario:
    if not usuario.es_jefe:
        raise HTTPException(
            status_code=303, headers={"Location": "/?msg=No+tienes+permiso+para+eso"}
        )
    return usuario


def ir_a(destino: str, msg: str = "") -> RedirectResponse:
    if msg:
        sep = "&" if "?" in destino else "?"
        destino = f"{destino}{sep}msg={quote(msg)}"
    return RedirectResponse(destino, status_code=303)


PAGINAS_VALIDAS = ("/", "/registros")


def volver_a(valor: str, por_defecto: str = "/") -> str:
    """Evita redirecciones abiertas: solo se vuelve a paginas conocidas."""
    return valor if valor in PAGINAS_VALIDAS else por_defecto


# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------
def contexto(request: Request, usuario: Usuario | None, **extra) -> dict:
    datos = {
        "request": request,
        "usuario": usuario,
        "msg": request.query_params.get("msg", ""),
        "hoy": date.today(),
        "APP_NAME": config.APP_NAME,
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
            .order_by(Meta.fecha_limite.is_(None), Meta.fecha_limite)
        )
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


def filtrar_registros(usuario_id: str, desde: str, hasta: str):
    """Arma la consulta de registros y los filtros aplicados.

    Se usa tanto en la página de registros como en la exportación a Excel
    para que ambos muestren exactamente lo mismo.
    """
    consulta = select(Registro).order_by(Registro.fecha.desc(), Registro.id.desc())
    filtros: dict = {}

    if (usuario_id or "").isdigit():
        consulta = consulta.where(Registro.usuario_id == int(usuario_id))
        filtros["usuario_id"] = int(usuario_id)

    f_desde = parse_fecha(desde)
    f_hasta = parse_fecha(hasta)
    if f_desde:
        consulta = consulta.where(Registro.fecha >= f_desde)
        filtros["desde"] = f_desde
    if f_hasta:
        consulta = consulta.where(Registro.fecha <= f_hasta)
        filtros["hasta"] = f_hasta

    return consulta, filtros


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
    user = db.scalar(select(Usuario).where(Usuario.usuario == usuario_input.strip()))
    if user is None or not user.activo or not verificar_pin(pin, user.pin_hash):
        return templates.TemplateResponse(
            request,
            "login.html",
            contexto(request, None, error="Usuario o PIN incorrecto.", usuario_input=usuario_input),
            status_code=401,
        )
    request.session["usuario_id"] = user.id
    return ir_a("/", f"Hola {user.nombre}")


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
):
    hoy = date.today()
    equipo = list(
        db.scalars(select(Usuario).where(Usuario.activo.is_(True)).order_by(Usuario.nombre))
    )

    registros_hoy = list(
        db.scalars(
            select(Registro)
            .where(Registro.fecha == hoy)
            .order_by(Registro.creado_en.desc())
        )
    )
    ids_registraron = {r.usuario_id for r in registros_hoy}

    metas = list(
        db.scalars(
            select(Meta).order_by(Meta.estado, Meta.fecha_limite.is_(None), Meta.fecha_limite)
        )
    )
    mis_registros = list(
        db.scalars(
            select(Registro)
            .where(Registro.usuario_id == usuario.id)
            .order_by(Registro.fecha.desc(), Registro.id.desc())
            .limit(10)
        )
    )

    resumen, semana_inicio = resumen_semanal(db, equipo, hoy)

    visibles = metas_visibles(db, usuario)
    ids_visibles = {meta.id for meta in visibles}
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
            registrar_hoy=[u for u in equipo if u.id not in ids_registraron and u.rol != ROL_JEFE],
            resumen_semana=resumen,
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

    db.add(
        Registro(
            usuario_id=usuario.id,
            meta_id=id_meta,
            fecha=parse_fecha(fecha) or date.today(),
            descripcion=descripcion,
            horas=parse_horas(horas),
            estado=estado,
        )
    )
    db.commit()
    return ir_a("/", "Registro guardado")


@app.get("/registros")
def listar_registros(
    request: Request,
    usuario: Usuario = Depends(requiere_jefe),
    db: Session = Depends(get_db),
    usuario_id: str = "",
    desde: str = "",
    hasta: str = "",
):
    consulta, filtros = filtrar_registros(usuario_id, desde, hasta)
    registros = list(db.scalars(consulta.limit(500)))
    return templates.TemplateResponse(
        request,
        "registros.html",
        contexto(
            request,
            usuario,
            registros=registros,
            equipo=list(db.scalars(select(Usuario).order_by(Usuario.nombre))),
            filtros=filtros,
            total_horas=sum(r.horas for r in registros),
            meses=reportes.MESES,
        ),
    )


@app.get("/registros/exportar.xlsx")
def exportar_registros(
    usuario: Usuario = Depends(requiere_jefe),
    db: Session = Depends(get_db),
    usuario_id: str = "",
    desde: str = "",
    hasta: str = "",
):
    """Descarga en Excel los registros que cumplen los filtros elegidos."""
    consulta, _filtros = filtrar_registros(usuario_id, desde, hasta)
    registros = list(db.scalars(consulta.limit(5000)))

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
            "Estado",
            "Cargado el",
            "Comentario del jefe",
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
                r.estado.replace("_", " "),
                r.creado_en.strftime("%d/%m/%Y %H:%M") if r.creado_en else "",
                r.comentario or "",
            ]
        )

    hoja.append([])
    hoja.append(
        ["", "", "", "", "TOTAL HORAS", round(sum(r.horas for r in registros), 2)]
    )

    for columna, ancho in zip("ABCDEFGHI", [12, 24, 20, 34, 58, 9, 14, 18, 42]):
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
    db.commit()
    return ir_a(destino, mensaje)


# --------------------------------------------------------------------------
# Metas (solo jefe)
# --------------------------------------------------------------------------
@app.get("/metas")
def metas(
    request: Request,
    usuario: Usuario = Depends(requiere_jefe),
    db: Session = Depends(get_db),
):
    todas = list(
        db.scalars(
            select(Meta).order_by(Meta.estado, Meta.fecha_limite.is_(None), Meta.fecha_limite)
        )
    )
    return templates.TemplateResponse(
        request,
        "metas.html",
        contexto(
            request,
            usuario,
            metas=todas,
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
    todas = list(
        db.scalars(
            select(Meta).order_by(
                Meta.estado, Meta.fecha_limite.is_(None), Meta.fecha_limite
            )
        )
    )
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
):
    titulo = titulo.strip()
    if not titulo:
        return ir_a("/metas", "La meta necesita un título")

    id_asignado = int(asignado_a) if asignado_a.isdigit() else None
    if id_asignado is not None and db.get(Usuario, id_asignado) is None:
        id_asignado = None

    db.add(
        Meta(
            titulo=titulo,
            descripcion=descripcion.strip(),
            asignado_a=id_asignado,
            fecha_inicio=parse_fecha(fecha_inicio),
            fecha_limite=parse_fecha(fecha_limite),
            horas_estimadas=parse_numero(horas_estimadas),
        )
    )
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
    for registro in list(db.scalars(select(Registro).where(Registro.meta_id == meta_id))):
        registro.meta_id = None
    db.delete(meta)
    db.commit()
    return ir_a("/metas", "Meta eliminada (los registros se conservan)")


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
    if estado in ESTADOS_META:
        meta.estado = estado
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

    db.add(
        Usuario(
            nombre=nombre,
            usuario=login_nombre,
            cargo=cargo.strip(),
            pin_hash=hash_pin(pin),
            rol=rol,
        )
    )
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
    registros = list(db.scalars(consulta.limit(300)))

    metas = list(
        db.scalars(
            select(Meta)
            .where(or_(Meta.asignado_a == usuario_id, Meta.asignado_a.is_(None)))
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
            metas=progreso_metas(db, metas),
            total_horas=sum(r.horas for r in registros),
            dias=len({r.fecha for r in registros}),
            total_comentarios=sum(1 for r in registros if r.comentario),
        ),
    )


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
        ),
    )


@app.post("/respaldos/ahora")
def respaldo_ahora(usuario: Usuario = Depends(requiere_jefe)):
    try:
        ruta = backup.crear_respaldo(etiqueta="manual")
        backup.limpiar_respaldos_antiguos()
    except Exception as error:  # noqa: BLE001 - se informa al usuario, no se cae
        return ir_a("/respaldos", f"No se pudo crear el respaldo: {error}")
    return ir_a("/respaldos", f"Respaldo creado: {ruta.name}")


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
