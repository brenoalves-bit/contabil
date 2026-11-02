from uuid import UUID

from fastapi import APIRouter, Request, status
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import DB, AdminEscritorio
from app.models import Usuario
from app.schemas.auth import UsuarioCreate, UsuarioOut
from app.services import auditoria
from app.services import auth as svc

router = APIRouter(prefix="/usuarios", tags=["usuarios"])


class UsuarioPatch(BaseModel):
    ativo: bool | None = None
    admin_escritorio: bool | None = None
    nome: str | None = None


@router.post("", response_model=UsuarioOut, status_code=status.HTTP_201_CREATED)
def criar(dados: UsuarioCreate, db: DB, adm: AdminEscritorio, request: Request):
    return svc.criar_usuario(db, dados, criado_por=adm.id, ip=request.client.host if request.client else None)


@router.get("", response_model=list[UsuarioOut])
def listar(db: DB, _: AdminEscritorio):
    return list(db.scalars(select(Usuario).order_by(Usuario.nome)))


@router.patch("/{usuario_id}", response_model=UsuarioOut)
def atualizar(usuario_id: UUID, dados: UsuarioPatch, db: DB, adm: AdminEscritorio, request: Request):
    u = svc.obter_usuario(db, usuario_id)
    mudancas = dados.model_dump(exclude_unset=True)
    for k, v in mudancas.items():
        setattr(u, k, v)
    auditoria.registrar(
        db, acao="atualizar", entidade="usuario", entidade_id=u.id, usuario_id=adm.id,
        dados=mudancas, ip=request.client.host if request.client else None,
    )
    return u
