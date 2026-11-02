from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.models.enums import OrigemLancamento, StatusLancamento
from app.schemas.tipos import Dinheiro


class PartidaIn(BaseModel):
    conta_codigo: str
    debito: Decimal = Field(default=Decimal(0), ge=0, max_digits=18, decimal_places=2)
    credito: Decimal = Field(default=Decimal(0), ge=0, max_digits=18, decimal_places=2)
    centro_custo_codigo: str | None = None
    historico_complementar: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _um_lado(self):
        if (self.debito > 0) == (self.credito > 0):
            raise ValueError("partida deve ter débito OU crédito, maior que zero")
        return self


class LancamentoCreate(BaseModel):
    data: date
    historico: str = Field(min_length=1, max_length=2000)
    partidas: list[PartidaIn] = Field(min_length=2, max_length=500)
    origem: OrigemLancamento = OrigemLancamento.MANUAL
    chave_externa: str | None = Field(default=None, max_length=200)
    efetivar: bool = True

    @model_validator(mode="after")
    def _balanceado(self):
        if self.efetivar:
            d = sum(p.debito for p in self.partidas)
            c = sum(p.credito for p in self.partidas)
            if d != c:
                raise ValueError(f"lançamento desbalanceado: débitos {d} ≠ créditos {c}")
        if self.origem in (OrigemLancamento.APURACAO, OrigemLancamento.ESTORNO):
            raise ValueError("origem APURACAO/ESTORNO é gerada pelo sistema")
        return self


class LancamentoUpdate(BaseModel):
    """Somente rascunhos aceitam edição."""
    data: date | None = None
    historico: str | None = Field(default=None, min_length=1, max_length=2000)
    partidas: list[PartidaIn] | None = Field(default=None, min_length=2, max_length=500)


class EstornoIn(BaseModel):
    data: date
    historico: str | None = Field(default=None, max_length=2000)


class PartidaOut(BaseModel):
    id: UUID
    conta_id: UUID
    conta_codigo: str
    conta_nome: str
    centro_custo_id: UUID | None
    ordem: int
    debito: Dinheiro
    credito: Dinheiro
    historico_complementar: str | None


class LancamentoOut(BaseModel):
    id: UUID
    numero: int | None
    data: date
    historico: str
    status: StatusLancamento
    origem: OrigemLancamento
    chave_externa: str | None
    estorno_de_id: UUID | None
    estornado_por_id: UUID | None
    criado_por: UUID
    efetivado_em: datetime | None
    criado_em: datetime
    total_debito: Dinheiro
    total_credito: Dinheiro
    partidas: list[PartidaOut]


class LancamentoPage(BaseModel):
    items: list[LancamentoOut]
    total: int
    limit: int
    offset: int
