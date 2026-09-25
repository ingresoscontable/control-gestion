"""Modelos de datos: usuarios, metas y registros diarios."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base

ROL_JEFE = "jefe"
ROL_EMPLEADO = "empleado"

ESTADOS_REGISTRO = [
    ("en_progreso", "En progreso"),
    ("completado", "Completado"),
    ("bloqueado", "Bloqueado"),
]

ESTADOS_META = ["activa", "cerrada"]


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

    registros: Mapped[list["Registro"]] = relationship(
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

    asignado: Mapped[Usuario | None] = relationship(foreign_keys=[asignado_a])
    registros: Mapped[list["Registro"]] = relationship(back_populates="meta")


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

    usuario: Mapped[Usuario] = relationship(
        back_populates="registros", foreign_keys=[usuario_id]
    )
    meta: Mapped[Meta | None] = relationship(back_populates="registros")
