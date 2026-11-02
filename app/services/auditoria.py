import json
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import Auditoria


def _jsonable(v: Any) -> Any:
    return json.loads(json.dumps(v, default=str))


def registrar(
    db: Session,
    *,
    acao: str,
    entidade: str,
    entidade_id: str | UUID | None = None,
    empresa_id: UUID | None = None,
    usuario_id: UUID | None = None,
    dados: dict | None = None,
    ip: str | None = None,
) -> None:
    db.add(
        Auditoria(
            empresa_id=empresa_id,
            usuario_id=usuario_id,
            acao=acao,
            entidade=entidade,
            entidade_id=str(entidade_id) if entidade_id is not None else None,
            dados=_jsonable(dados) if dados is not None else None,
            ip=ip,
        )
    )
