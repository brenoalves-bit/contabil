from datetime import date
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import GrupoConta, NaturezaConta, TipoConta
from app.schemas.tipos import Dinheiro


class LinhaRazao(BaseModel):
    data: date
    lancamento_id: UUID
    numero: int | None
    historico: str
    historico_complementar: str | None
    debito: Dinheiro
    credito: Dinheiro
    saldo: Dinheiro
    saldo_natureza: NaturezaConta


class RazaoOut(BaseModel):
    conta_codigo: str
    conta_nome: str
    natureza: NaturezaConta
    inicio: date
    fim: date
    saldo_anterior: Dinheiro
    saldo_anterior_natureza: NaturezaConta
    linhas: list[LinhaRazao]
    saldo_final: Dinheiro
    saldo_final_natureza: NaturezaConta


class LinhaBalancete(BaseModel):
    conta_id: UUID
    codigo: str
    nome: str
    grupo: GrupoConta
    natureza: NaturezaConta
    tipo: TipoConta
    nivel: int
    saldo_anterior: Dinheiro
    saldo_anterior_natureza: NaturezaConta
    debitos: Dinheiro
    creditos: Dinheiro
    saldo_atual: Dinheiro
    saldo_atual_natureza: NaturezaConta


class BalanceteOut(BaseModel):
    inicio: date
    fim: date
    linhas: list[LinhaBalancete]
    total_debitos: Dinheiro
    total_creditos: Dinheiro
    total_saldo_devedor: Dinheiro
    total_saldo_credor: Dinheiro
    fechado: bool


class LinhaDemonstrativo(BaseModel):
    codigo: str
    nome: str
    nivel: int
    tipo: TipoConta
    valor: Dinheiro


class DREOut(BaseModel):
    inicio: date
    fim: date
    receitas: list[LinhaDemonstrativo]
    despesas: list[LinhaDemonstrativo]
    total_receitas: Dinheiro
    total_despesas: Dinheiro
    resultado: Dinheiro


class BalancoOut(BaseModel):
    data: date
    ativo: list[LinhaDemonstrativo]
    passivo: list[LinhaDemonstrativo]
    patrimonio_liquido: list[LinhaDemonstrativo]
    resultado_periodo: Dinheiro
    total_ativo: Dinheiro
    total_passivo: Dinheiro
    total_patrimonio_liquido: Dinheiro
    total_passivo_e_pl: Dinheiro
    fechado: bool
