"""Conexión a SQLite con SQLAlchemy."""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from . import config

config.DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = config.DATA_DIR / "control.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    # SQLite + varios hilos de uvicorn: hace falta desactivar este chequeo.
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _configurar_sqlite(conexion_dbapi, _registro) -> None:
    """Pone la conexion en modo WAL y con espera ante bloqueos.

    En el modo por defecto (rollback journal) quien escribe bloquea a todos los
    que estan leyendo, y con varias personas cargando a la vez en la red local
    eso termina en "database is locked". WAL separa lectores de escritores.
    """
    cursor = conexion_dbapi.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
    finally:
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    """Dependencia de FastAPI: abre y cierra una sesión por request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
