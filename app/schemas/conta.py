from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import GrupoConta, NaturezaConta, TipoConta


class ContaCreate(BaseModel):
    codigo: str = Field(pattern=r"^[0-9]+(\.[0-9]+)*$", max_length=40)
    nome: str = Field(min_length=1, max_length=200)
    grupo: GrupoConta
    natureza: NaturezaConta
    tipo: TipoConta
    conta_pai_codigo: str | None = None
    codigo_referencial: str | None = Field(default=None, max_length=40)


class ContaUpdate(BaseModel):
    nome: str | None = Field(default=None, min_length=1, max_length=200)
    ativa: bool | None = None
    codigo_referencial: str | None = Field(default=None, max_length=40)


class ContaOut(BaseModel):
    id: UUID
    codigo: str
    nome: str
    grupo: GrupoConta
    natureza: NaturezaConta
    tipo: TipoConta
    conta_pai_id: UUID | None
    nivel: int
    codigo_referencial: str | None
    ativa: bool

    model_config = {"from_attributes": True}


class CentroCustoCreate(BaseModel):
    codigo: str = Field(min_length=1, max_length=40)
    nome: str = Field(min_length=1, max_length=200)


class CentroCustoUpdate(BaseModel):
    nome: str | None = Field(default=None, min_length=1, max_length=200)
    ativo: bool | None = None


class CentroCustoOut(BaseModel):
    id: UUID
    codigo: str
    nome: str
    ativo: bool

    model_config = {"from_attributes": True}
