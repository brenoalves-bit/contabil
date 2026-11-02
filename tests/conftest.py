import os
import subprocess
from collections.abc import Iterator

import pytest

# A engine é criada na importação de app.core.db: precisa apontar para o banco de teste ANTES.
_TEST_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://fiber:fiber_dev_pw@localhost:5432/fiber_contabil_test"
)
os.environ["DATABASE_URL"] = _TEST_URL
os.environ.setdefault("JWT_SECRET", "segredo-de-teste-com-mais-de-32-caracteres-ok")
os.environ["ACCESS_TOKEN_MINUTES"] = "15"

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.db import SessionLocal, engine
from app.main import app
from app.schemas.auth import UsuarioCreate
from app.services import auth as svc_auth

TABELAS = [
    "auditoria", "partida", "lancamento", "periodo", "centro_custo", "conta",
    "usuario_empresa", "empresa", "refresh_token", "usuario",
]


@pytest.fixture(scope="session", autouse=True)
def migrar() -> None:
    env = {**os.environ, "ALEMBIC_DATABASE_URL": _TEST_URL}
    subprocess.run(["alembic", "downgrade", "base"], check=True, env=env, capture_output=True)
    subprocess.run(["alembic", "upgrade", "head"], check=True, env=env, capture_output=True)


@pytest.fixture(autouse=True)
def limpar() -> Iterator[None]:
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE " + ", ".join(TABELAS) + " RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


SENHA = "SenhaForte!2026xyz"


def criar_usuario(email: str, admin: bool = False) -> str:
    with SessionLocal() as db:
        u = svc_auth.criar_usuario(
            db, UsuarioCreate(email=email, nome=email.split("@")[0], senha=SENHA, admin_escritorio=admin),
            criado_por=None, ip=None,
        )
        db.commit()
        return str(u.id)


def login(client: TestClient, email: str) -> dict:
    r = client.post("/api/v1/auth/login", json={"email": email, "senha": SENHA})
    assert r.status_code == 200, r.text
    tok = r.json()
    return {"Authorization": f"Bearer {tok['access_token']}", "_refresh": tok["refresh_token"]}


@pytest.fixture
def admin(client: TestClient) -> dict:
    criar_usuario("admin@fiber-finance.com.br", admin=True)
    h = login(client, "admin@fiber-finance.com.br")
    return {"Authorization": h["Authorization"]}


CNPJ_A = "11222333000181"
CNPJ_B = "34028316000103"


def criar_empresa(client: TestClient, headers: dict, cnpj: str = CNPJ_A, nome: str = "Empresa A") -> str:
    r = client.post("/api/v1/empresas", headers=headers, json={
        "razao_social": nome, "cnpj": cnpj, "regime_tributario": "SIMPLES", "criar_plano_padrao": True,
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.fixture
def empresa(client: TestClient, admin: dict) -> str:
    return criar_empresa(client, admin)


def lancar(client, headers, empresa_id, data, historico, partidas, efetivar=True, **extra):
    body = {"data": data, "historico": historico, "partidas": partidas, "efetivar": efetivar, **extra}
    return client.post(f"/api/v1/empresas/{empresa_id}/lancamentos", headers=headers, json=body)


def p(conta, debito=None, credito=None):
    d = {"conta_codigo": conta}
    if debito is not None:
        d["debito"] = str(debito)
    if credito is not None:
        d["credito"] = str(credito)
    return d
