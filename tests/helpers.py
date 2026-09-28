"""Ayudantes compartidos por los modulos de prueba."""

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import Meta, Registro, Usuario


def login(client: TestClient, usuario: str, pin: str):
    return client.post(
        "/login", data={"usuario": usuario, "pin": pin}, follow_redirects=False
    )


def _id_usuario(login_usuario: str) -> int:
    db = SessionLocal()
    try:
        return db.query(Usuario).filter_by(usuario=login_usuario).one().id
    finally:
        db.close()


def _usuario_id(usuario: str) -> int:
    db = SessionLocal()
    try:
        return db.query(Usuario).filter_by(usuario=usuario).one().id
    finally:
        db.close()


def _id_meta(titulo: str) -> int:
    db = SessionLocal()
    try:
        return db.query(Meta).filter_by(titulo=titulo).one().id
    finally:
        db.close()


def _id_registro_de(login_usuario: str) -> int:
    db = SessionLocal()
    try:
        persona = db.query(Usuario).filter_by(usuario=login_usuario).one()
        registro = (
            db.query(Registro)
            .filter(Registro.usuario_id == persona.id)
            .order_by(Registro.id)
            .first()
        )
        return registro.id
    finally:
        db.close()


def _ultimo_registro_de(login_usuario: str) -> int:
    db = SessionLocal()
    try:
        persona = db.query(Usuario).filter_by(usuario=login_usuario).one()
        registro = (
            db.query(Registro)
            .filter(Registro.usuario_id == persona.id)
            .order_by(Registro.id.desc())
            .first()
        )
        return registro.id
    finally:
        db.close()
