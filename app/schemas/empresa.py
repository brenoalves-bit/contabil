from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.models.enums import PapelEmpresa, RegimeTributario


def _validar_cnpj(cnpj: str) -> str:
    digits = "".join(ch for ch in cnpj if ch.isdigit())
    if len(digits) != 14 or digits == digits[0] * 14:
        raise ValueError("CNPJ inválido")

    def dv(base: str, pesos: list[int]) -> int:
        s = sum(int(d) * p for d, p in zip(base, pesos, strict=True))
        r = s % 11
        return 0 if r < 2 else 11 - r

    p1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    p2 = [6, *p1]
    if dv(digits[:12], p1) != int(digits[12]) or dv(digits[:13], p2) != int(digits[13]):
        raise ValueError("CNPJ inválido")
    return digits


class EmpresaCreate(BaseModel):
    razao_social: str = Field(min_length=2, max_length=300)
    nome_fantasia: str | None = Field(default=None, max_length=300)
    cnpj: str
    regime_tributario: RegimeTributario
    inicio_exercicio_mes: int = Field(default=1, ge=1, le=12)
    criar_plano_padrao: bool = True

    @field_validator("cnpj")
    @classmethod
    def _cnpj(cls, v: str) -> str:
        return _validar_cnpj(v)


class EmpresaUpdate(BaseModel):
    razao_social: str | None = Field(default=None, min_length=2, max_length=300)
    nome_fantasia: str | None = Field(default=None, max_length=300)
    regime_tributario: RegimeTributario | None = None
    ativa: bool | None = None


class EmpresaOut(BaseModel):
    id: UUID
    razao_social: str
    nome_fantasia: str | None
    cnpj: str
    regime_tributario: RegimeTributario
    inicio_exercicio_mes: int
    ativa: bool

    model_config = {"from_attributes": True}


class VinculoUsuarioIn(BaseModel):
    usuario_id: UUID
    papel: PapelEmpresa


class VinculoUsuarioOut(BaseModel):
    usuario_id: UUID
    empresa_id: UUID
    papel: PapelEmpresa
    email: str | None = None
    nome: str | None = None
