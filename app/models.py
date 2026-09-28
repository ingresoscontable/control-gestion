"""Modelos de datos: usuarios, metas y registros diarios."""

from __future__ import annotations

import secrets
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship, selectinload

from .database import Base

ROL_JEFE = "jefe"
ROL_EMPLEADO = "empleado"

ESTADOS_REGISTRO = [
    ("en_progreso", "En progreso"),
    ("completado", "Completado"),
    ("bloqueado", "Bloqueado"),
]

# Revision del jefe sobre cada reporte: se carga "pendiente", el jefe lo
# aprueba o lo devuelve para corregir, y al corregirlo vuelve a "pendiente".
ESTADOS_REVISION = [
    ("pendiente", "Pendiente de revisión"),
    ("aprobado", "Aprobado"),
    ("correccion_pendiente", "Corrección pendiente"),
]

# Un reporte devuelto por el jefe no cuenta para el avance de la meta hasta
# que se corrija: eso es la "reversion del progreso".
REVISION_DEVUELTA = "correccion_pendiente"

# Novedades: dias en que una persona (o todo el equipo) no cuenta para el
# cumplimiento semanal.
TIPOS_NOVEDAD = [
    ("vacaciones", "Vacaciones"),
    ("licencia", "Licencia"),
    ("feriado", "Feriado"),
    ("otro", "Otro"),
]

ESTADOS_META = ["activa", "cerrada", "eliminada"]

# Estado de archivo: la meta desaparece de las pantallas pero conserva sus
# reportes y se puede restaurar.
ESTADO_ELIMINADA = "eliminada"


def nuevo_token_de_sesion() -> str:
    """Token que viaja en la cookie de sesion de cada usuario.

    Al cambiar (o resetear) el PIN se genera uno nuevo: las sesiones que ya
    estaban abiertas dejan de valer, que es lo que corresponde cuando alguien
    sospecha que le vieron el PIN.
    """
    return secrets.token_urlsafe(16)


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(80))
    usuario: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    pin_hash: Mapped[str] = mapped_column(String(255))
    rol: Mapped[str] = mapped_column(String(20), default=ROL_EMPLEADO)
    cargo: Mapped[str] = mapped_column(String(80), default="")
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    # Se renueva al cambiar el PIN para cortar las sesiones viejas.
    sesion_token: Mapped[str] = mapped_column(String(64), default=nuevo_token_de_sesion)
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    registros: Mapped[list[Registro]] = relationship(
        back_populates="usuario", foreign_keys="Registro.usuario_id"
    )

    @property
    def es_jefe(self) -> bool:
        return self.rol == ROL_JEFE


class Meta(Base):
    __tablename__ = "metas"

    id: Mapped[int] = mapped_column(primary_key=True)
    titulo: Mapped[str] = mapped_column(String(140))
    descripcion: Mapped[str] = mapped_column(Text, default="")
    # NULL => meta para todo el equipo.
    asignado_a: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id"), nullable=True
    )
    fecha_inicio: Mapped[date | None] = mapped_column(Date, nullable=True)
    fecha_limite: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Horas de trabajo previstas para cumplir la meta (0 = sin estimacion).
    horas_estimadas: Mapped[float] = mapped_column(Float, default=0.0)
    # Objetivo medido en cantidad (0 = la meta no se mide por cantidad) y como
    # se llama esa unidad: "tramites", "registros", "liquidaciones"... El jefe
    # la escribe libre, no viene fija en el sistema.
    objetivo: Mapped[float] = mapped_column(Float, default=0.0)
    unidad: Mapped[str] = mapped_column(String(30), default="")
    estado: Mapped[str] = mapped_column(String(20), default="activa")
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    __table_args__ = (Index("ix_metas_estado_fecha_limite", "estado", "fecha_limite"),)

    asignado: Mapped[Usuario | None] = relationship(foreign_keys=[asignado_a])
    registros: Mapped[list[Registro]] = relationship(back_populates="meta")


class Registro(Base):
    __tablename__ = "registros"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    meta_id: Mapped[int | None] = mapped_column(ForeignKey("metas.id"), nullable=True)
    fecha: Mapped[date] = mapped_column(Date, default=date.today)
    descripcion: Mapped[str] = mapped_column(Text)
    horas: Mapped[float] = mapped_column(Float, default=0.0)
    # Cuanto produjo, en la unidad que defina la meta (0 = no se informo).
    cantidad: Mapped[float] = mapped_column(Float, default=0.0)
    estado: Mapped[str] = mapped_column(String(20), default="en_progreso")
    # Comentario del jefe sobre el reporte del dia.
    comentario: Mapped[str] = mapped_column(Text, default="")
    comentado_en: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Revision del jefe: pendiente / aprobado / correccion_pendiente.
    estado_revision: Mapped[str] = mapped_column(String(20), default="pendiente")
    revisado_por: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id"), nullable=True
    )
    revisado_en: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    observacion_revision: Mapped[str] = mapped_column(Text, default="")
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    __table_args__ = (
        # El calendario, el resumen semanal y los reportes filtran por fecha;
        # el historial de cada persona filtra por usuario y despues por fecha.
        Index("ix_registros_fecha", "fecha"),
        Index("ix_registros_usuario_fecha", "usuario_id", "fecha"),
        Index("ix_registros_revision", "estado_revision"),
        # Un reporte por persona, dia y meta: corta los dobles clic y los
        # "Repetir" seguidos. (SQLite trata los NULL como distintos, asi que
        # los reportes "sin meta" los cubre la comprobacion de la aplicacion.)
        Index("ix_registros_unico", "usuario_id", "fecha", "meta_id", unique=True),
    )

    usuario: Mapped[Usuario] = relationship(
        back_populates="registros", foreign_keys=[usuario_id]
    )
    meta: Mapped[Meta | None] = relationship(back_populates="registros")
    revisor: Mapped[Usuario | None] = relationship(foreign_keys=[revisado_por])


class Novedad(Base):
    """Un rango de dias que no se le exige reportar a alguien.

    ``usuario_id`` en NULL es una novedad de todo el equipo (un feriado).
    """

    __tablename__ = "novedades"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id"), nullable=True
    )
    tipo: Mapped[str] = mapped_column(String(20), default="otro")
    desde: Mapped[date] = mapped_column(Date)
    hasta: Mapped[date] = mapped_column(Date)
    detalle: Mapped[str] = mapped_column(String(140), default="")
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    __table_args__ = (Index("ix_novedades_rango", "desde", "hasta"),)

    usuario: Mapped[Usuario | None] = relationship(foreign_keys=[usuario_id])


class Auditoria(Base):
    """Quien hizo que y cuando: deja rastro de toda accion destructiva."""

    __tablename__ = "auditoria"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id"), nullable=True
    )
    accion: Mapped[str] = mapped_column(String(40))
    objeto_tipo: Mapped[str] = mapped_column(String(30), default="")
    objeto_id: Mapped[int | None] = mapped_column(nullable=True)
    resumen: Mapped[str] = mapped_column(String(255), default="")
    fecha: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    __table_args__ = (Index("ix_auditoria_fecha", "fecha"),)

    usuario: Mapped[Usuario | None] = relationship(foreign_keys=[usuario_id])


# Sin esto cada fila de un listado dispara su propia consulta para leer el
# usuario o el responsable (1 consulta por fila al renderizar).
OPCIONES_REGISTRO = (
    selectinload(Registro.usuario),
    selectinload(Registro.meta),
    selectinload(Registro.revisor),
)
OPCIONES_META = (selectinload(Meta.asignado),)
OPCIONES_AUDITORIA = (selectinload(Auditoria.usuario),)
OPCIONES_NOVEDAD = (selectinload(Novedad.usuario),)

# Acciones que quedan firmadas en la auditoria, con la etiqueta que se muestra
# en la pagina /auditoria. Se guarda la clave corta en la base.
ACCIONES_AUDITORIA = [
    ("crear_meta", "Creó una meta"),
    ("editar_meta", "Editó una meta"),
    ("duplicar_meta", "Duplicó una meta"),
    ("archivar_meta", "Archivó una meta"),
    ("comentar_registro", "Comentó un reporte"),
    ("crear_novedad", "Cargó una novedad"),
    ("eliminar_novedad", "Borró una novedad"),
    ("revisar_registro", "Revisó un reporte"),
    ("corregir_registro", "Corrigió un reporte"),
    ("eliminar_registro", "Eliminó un reporte"),
    ("crear_usuario", "Creó un usuario"),
    ("cambiar_estado_usuario", "Activó/desactivó un usuario"),
    ("cambiar_pin", "Cambió un PIN"),
    ("crear_respaldo", "Creó un respaldo"),
    ("restaurar_respaldo", "Restauró un respaldo"),
]
