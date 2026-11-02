from uuid import UUID

from fastapi import APIRouter, status

from app.api.deps import DB, AdminEmpresa, Contador, Leitura
from app.models import GrupoConta, TipoConta
from app.schemas.conta import (
    CentroCustoCreate,
    CentroCustoOut,
    CentroCustoUpdate,
    ContaCreate,
    ContaOut,
    ContaUpdate,
)
from app.services import contas as svc

router = APIRouter(prefix="/empresas/{empresa_id}", tags=["plano de contas"])


@router.get("/contas", response_model=list[ContaOut])
def listar(empresa_id: UUID, db: DB, ctx: Leitura, grupo: GrupoConta | None = None,
           tipo: TipoConta | None = None, ativa: bool | None = None):
    return svc.listar(db, ctx.empresa_id, grupo=grupo, tipo=tipo, ativa=ativa)


@router.post("/contas", response_model=ContaOut, status_code=status.HTTP_201_CREATED)
def criar(empresa_id: UUID, dados: ContaCreate, db: DB, ctx: AdminEmpresa):
    return svc.criar(db, ctx, dados)


@router.post("/contas/plano-padrao", status_code=status.HTTP_201_CREATED)
def plano_padrao(empresa_id: UUID, db: DB, ctx: AdminEmpresa):
    return {"contas_criadas": svc.criar_plano_padrao(db, ctx.empresa_id)}


@router.get("/contas/{codigo}", response_model=ContaOut)
def obter(empresa_id: UUID, codigo: str, db: DB, ctx: Leitura):
    return svc.por_codigo(db, ctx.empresa_id, codigo)


@router.patch("/contas/{codigo}", response_model=ContaOut)
def atualizar(empresa_id: UUID, codigo: str, dados: ContaUpdate, db: DB, ctx: AdminEmpresa):
    return svc.atualizar(db, ctx, codigo, dados)


@router.get("/centros-custo", response_model=list[CentroCustoOut])
def listar_centros(empresa_id: UUID, db: DB, ctx: Leitura):
    return svc.listar_centros(db, ctx.empresa_id)


@router.post("/centros-custo", response_model=CentroCustoOut, status_code=status.HTTP_201_CREATED)
def criar_centro(empresa_id: UUID, dados: CentroCustoCreate, db: DB, ctx: Contador):
    return svc.criar_centro(db, ctx, dados)


@router.patch("/centros-custo/{codigo}", response_model=CentroCustoOut)
def atualizar_centro(empresa_id: UUID, codigo: str, dados: CentroCustoUpdate, db: DB, ctx: Contador):
    return svc.atualizar_centro(db, ctx, codigo, dados)
