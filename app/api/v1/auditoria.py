from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import DB, AdminEmpresa
from app.models import Auditoria

router = APIRouter(prefix="/empresas/{empresa_id}/auditoria", tags=["auditoria"])


class AuditoriaOut(BaseModel):
    id: int
    usuario_id: UUID | None
    acao: str
    entidade: str
    entidade_id: str | None
    dados: dict | None
    ip: str | None
    criado_em: datetime

    model_config = {"from_attributes": True}


@router.get("", response_model=list[AuditoriaOut])
def listar(empresa_id: UUID, db: DB, ctx: AdminEmpresa, entidade: str | None = None,
           limit: int = Query(default=100, ge=1, le=1000), offset: int = Query(default=0, ge=0)):
    q = select(Auditoria).where(Auditoria.empresa_id == ctx.empresa_id)
    if entidade:
        q = q.where(Auditoria.entidade == entidade)
    return list(db.scalars(q.order_by(Auditoria.id.desc()).limit(limit).offset(offset)))
