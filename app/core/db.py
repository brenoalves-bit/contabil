"""Conexão com o banco e contexto de tenant.

Toda query de tabela multiempresa passa por Row Level Security no Postgres.
A política lê `current_setting('app.empresa_id')`; `set_tenant` grava esse valor
com SET LOCAL, válido só na transação corrente. Sem ele, as tabelas de tenant
retornam zero linhas — isolamento por padrão, não por disciplina do programador.
"""
from collections.abc import Generator
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


engine = create_engine(get_settings().database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def set_tenant(db: Session, empresa_id: UUID | None, usuario_id: UUID | None) -> None:
    db.execute(
        text("SELECT set_config('app.empresa_id', :e, true), set_config('app.usuario_id', :u, true)"),
        {"e": str(empresa_id) if empresa_id else "", "u": str(usuario_id) if usuario_id else ""},
    )


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
