"""Cria o primeiro administrador do escritório.

Uso: uv run python scripts/bootstrap_admin.py --email adm@fiber.com.br --nome "Admin" --senha '...'
Só funciona enquanto não existir nenhum administrador (evita uso indevido depois do setup).
"""
import argparse
import sys

from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import Usuario
from app.schemas.auth import UsuarioCreate
from app.services import auth


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", required=True)
    ap.add_argument("--nome", required=True)
    ap.add_argument("--senha", required=True)
    a = ap.parse_args()
    with SessionLocal() as db:
        if db.scalar(select(Usuario.id).where(Usuario.admin_escritorio.is_(True)).limit(1)):
            print("já existe administrador; use a API /usuarios", file=sys.stderr)
            return 1
        u = auth.criar_usuario(
            db, UsuarioCreate(email=a.email, nome=a.nome, senha=a.senha, admin_escritorio=True),
            criado_por=None, ip="bootstrap",
        )
        db.commit()
        print(f"administrador criado: {u.id} {u.email}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
