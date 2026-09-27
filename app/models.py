"""Modelos de datos: usuarios, metas y registros diarios."""

from __future__ import annotations

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

ESTADOS_META = ["activa", "cerrada", "eliminada"]

# Estado de archivo: la meta desaparece de las pantallas pero conserva sus
# reportes y se puede restaurar.
ESTADO_ELIMINADA = "eliminada"


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(80))
    usuario: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    pin_hash: Mapped[str] = mapped_column(String(255))
    rol: Mapped[str] = mapped_column(String(20), default=ROL_EMPLEADO)
    cargo: Mapped[str] = mapped_column(String(80), default="")
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
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
    estado: Mapped[str] = mapped_column(String(20), default="en_progreso")
    # Comentario del jefe sobre el reporte del dia.
    comentario: Mapped[str] = mapped_column(Text, default="")
    comentado_en: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    __table_args__ = (
        # El calendario, el resumen semanal y los reportes filtran por fecha;
        # el historial de cada persona filtra por usuario y despues por fecha.
        Index("ix_registros_fecha", "fecha"),
        Index("ix_registros_usuario_fecha", "usuario_id", "fecha"),
        # Un reporte por persona, dia y meta: corta los dobles clic y los
        # "Repetir" seguidos. (SQLite trata los NULL como distintos, asi que
        # los reportes "sin meta" los cubre la comprobacion de la aplicacion.)
        Index("ix_registros_unico", "usuario_id", "fecha", "meta_id", unique=True),
    )

    usuario: Mapped[Usuario] = relationship(
        back_populates="registros", foreign_keys=[usuario_id]
    )
    meta: Mapped[Meta | None] = relationship(back_populates="registros")


# Sin esto cada fila de un listado dispara su propia consulta para leer el
# usuario o el responsable (1 consulta por fila al renderizar).
OPCIONES_REGISTRO = (selectinload(Registro.usuario), selectinload(Registro.meta))
OPCIONES_META = (selectinload(Meta.asignado),)
