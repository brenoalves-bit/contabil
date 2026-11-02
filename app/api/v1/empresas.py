from uuid import UUID

from fastapi import APIRouter, Request, status

from app.api.deps import DB, AdminEmpresa, AdminEscritorio, Leitura, UsuarioAtual
from app.schemas.empresa import (
    EmpresaCreate,
    EmpresaOut,
    EmpresaUpdate,
    VinculoUsuarioIn,
    VinculoUsuarioOut,
)
from app.services import empresas as svc

router = APIRouter(prefix="/empresas", tags=["empresas"])


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.post("", response_model=EmpresaOut, status_code=status.HTTP_201_CREATED)
def criar(dados: EmpresaCreate, db: DB, adm: AdminEscritorio, request: Request):
    return svc.criar(db, dados, usuario=adm, ip=_ip(request))


@router.get("", response_model=list[EmpresaOut])
def listar(db: DB, u: UsuarioAtual):
    return svc.listar_para_usuario(db, u)


@router.get("/{empresa_id}", response_model=EmpresaOut)
def obter(empresa_id: UUID, db: DB, ctx: Leitura):
    return svc.obter(db, ctx.empresa_id)


@router.patch("/{empresa_id}", response_model=EmpresaOut)
def atualizar(empresa_id: UUID, dados: EmpresaUpdate, db: DB, ctx: AdminEmpresa):
    return svc.atualizar(db, svc.obter(db, ctx.empresa_id), dados, usuario=ctx.usuario, ip=ctx.ip)


@router.get("/{empresa_id}/usuarios", response_model=list[VinculoUsuarioOut])
def listar_usuarios(empresa_id: UUID, db: DB, ctx: AdminEmpresa):
    return [
        VinculoUsuarioOut(usuario_id=v.usuario_id, empresa_id=v.empresa_id, papel=v.papel, email=u.email, nome=u.nome)
        for v, u in svc.listar_vinculos(db, ctx.empresa_id)
    ]


@router.put("/{empresa_id}/usuarios", response_model=VinculoUsuarioOut)
def vincular(empresa_id: UUID, dados: VinculoUsuarioIn, db: DB, ctx: AdminEmpresa):
    v = svc.vincular_usuario(db, ctx.empresa_id, dados.usuario_id, dados.papel, por=ctx.usuario, ip=ctx.ip)
    return VinculoUsuarioOut(usuario_id=v.usuario_id, empresa_id=v.empresa_id, papel=v.papel)


@router.delete("/{empresa_id}/usuarios/{usuario_id}", status_code=status.HTTP_204_NO_CONTENT)
def desvincular(empresa_id: UUID, usuario_id: UUID, db: DB, ctx: AdminEmpresa):
    svc.desvincular_usuario(db, ctx.empresa_id, usuario_id, por=ctx.usuario, ip=ctx.ip)
