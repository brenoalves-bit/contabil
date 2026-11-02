from datetime import date
from uuid import UUID

from fastapi import APIRouter, Query

from app.api.deps import DB, Leitura
from app.core.errors import DomainError
from app.schemas.relatorio import BalanceteOut, BalancoOut, DREOut, RazaoOut
from app.services import relatorios as svc

router = APIRouter(prefix="/empresas/{empresa_id}/relatorios", tags=["relatórios"])


def _valida(inicio: date, fim: date) -> None:
    if fim < inicio:
        raise DomainError("fim deve ser maior ou igual a início", "intervalo_invalido")


@router.get("/razao", response_model=RazaoOut)
def razao(empresa_id: UUID, db: DB, ctx: Leitura, conta_codigo: str = Query(...), inicio: date = Query(...), fim: date = Query(...)):
    _valida(inicio, fim)
    return svc.razao(db, ctx.empresa_id, conta_codigo, inicio, fim)


@router.get("/balancete", response_model=BalanceteOut)
def balancete(empresa_id: UUID, db: DB, ctx: Leitura, inicio: date = Query(...), fim: date = Query(...),
              somente_com_movimento: bool = False):
    _valida(inicio, fim)
    return svc.balancete(db, ctx.empresa_id, inicio, fim, somente_com_movimento=somente_com_movimento)


@router.get("/dre", response_model=DREOut)
def dre(empresa_id: UUID, db: DB, ctx: Leitura, inicio: date = Query(...), fim: date = Query(...)):
    _valida(inicio, fim)
    return svc.dre(db, ctx.empresa_id, inicio, fim)


@router.get("/balanco", response_model=BalancoOut)
def balanco(empresa_id: UUID, db: DB, ctx: Leitura, data: date = Query(...)):
    return svc.balanco(db, ctx.empresa_id, data)
