from uuid import UUID

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from app.api.deps import DB, AdminEmpresa, Leitura
from app.schemas.lancamento import LancamentoOut
from app.schemas.periodo import ApuracaoIn, PeriodoOut
from app.services import empresas as svc_empresas
from app.services import lancamentos as svc_lanc
from app.services import periodos as svc

router = APIRouter(prefix="/empresas/{empresa_id}/periodos", tags=["períodos"])


class ReabrirIn(BaseModel):
    motivo: str = Field(min_length=10, max_length=1000)


@router.get("", response_model=list[PeriodoOut])
def listar(empresa_id: UUID, db: DB, ctx: Leitura):
    return svc.listar(db, ctx.empresa_id)


@router.post("/{ano}/{mes}/fechar", response_model=PeriodoOut)
def fechar(empresa_id: UUID, ano: int, mes: int, db: DB, ctx: AdminEmpresa):
    return svc.fechar(db, ctx, ano, mes)


@router.post("/{ano}/{mes}/reabrir", response_model=PeriodoOut)
def reabrir(empresa_id: UUID, ano: int, mes: int, dados: ReabrirIn, db: DB, ctx: AdminEmpresa):
    return svc.reabrir(db, ctx, ano, mes, dados.motivo)


@router.post("/apuracao", response_model=LancamentoOut, status_code=status.HTTP_201_CREATED)
def apurar(empresa_id: UUID, dados: ApuracaoIn, db: DB, ctx: AdminEmpresa):
    e = svc_empresas.obter(db, ctx.empresa_id)
    lanc = svc.apurar_resultado(db, ctx, dados, e.inicio_exercicio_mes)
    return svc_lanc.para_saida(db, [lanc])[0]
