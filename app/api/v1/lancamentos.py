from datetime import date
from uuid import UUID

from fastapi import APIRouter, Query, status

from app.api.deps import DB, Contador, Leitura
from app.models import StatusLancamento
from app.schemas.lancamento import (
    EstornoIn,
    LancamentoCreate,
    LancamentoOut,
    LancamentoPage,
    LancamentoUpdate,
)
from app.services import lancamentos as svc

router = APIRouter(prefix="/empresas/{empresa_id}/lancamentos", tags=["lançamentos"])


@router.get("", response_model=LancamentoPage)
def listar(
    empresa_id: UUID, db: DB, ctx: Leitura,
    data_inicio: date | None = None, data_fim: date | None = None,
    status_: StatusLancamento | None = Query(default=None, alias="status"),
    conta_codigo: str | None = None, q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=500), offset: int = Query(default=0, ge=0),
):
    items, total = svc.listar(
        db, ctx.empresa_id, data_inicio=data_inicio, data_fim=data_fim, status=status_,
        conta_codigo=conta_codigo, texto=q, limit=limit, offset=offset,
    )
    return LancamentoPage(items=svc.para_saida(db, items), total=total, limit=limit, offset=offset)


@router.post("", response_model=LancamentoOut, status_code=status.HTTP_201_CREATED)
def criar(empresa_id: UUID, dados: LancamentoCreate, db: DB, ctx: Contador):
    return svc.para_saida(db, [svc.criar(db, ctx, dados)])[0]


@router.get("/{lancamento_id}", response_model=LancamentoOut)
def obter(empresa_id: UUID, lancamento_id: UUID, db: DB, ctx: Leitura):
    return svc.para_saida(db, [svc.obter(db, ctx.empresa_id, lancamento_id)])[0]


@router.put("/{lancamento_id}", response_model=LancamentoOut)
def atualizar_rascunho(empresa_id: UUID, lancamento_id: UUID, dados: LancamentoUpdate, db: DB, ctx: Contador):
    return svc.para_saida(db, [svc.atualizar_rascunho(db, ctx, lancamento_id, dados)])[0]


@router.delete("/{lancamento_id}", status_code=status.HTTP_204_NO_CONTENT)
def excluir_rascunho(empresa_id: UUID, lancamento_id: UUID, db: DB, ctx: Contador):
    svc.excluir_rascunho(db, ctx, lancamento_id)


@router.post("/{lancamento_id}/efetivar", response_model=LancamentoOut)
def efetivar(empresa_id: UUID, lancamento_id: UUID, db: DB, ctx: Contador):
    return svc.para_saida(db, [svc.efetivar(db, ctx, lancamento_id)])[0]


@router.post("/{lancamento_id}/estornar", response_model=LancamentoOut, status_code=status.HTTP_201_CREATED)
def estornar(empresa_id: UUID, lancamento_id: UUID, dados: EstornoIn, db: DB, ctx: Contador):
    return svc.para_saida(db, [svc.estornar(db, ctx, lancamento_id, dados)])[0]
