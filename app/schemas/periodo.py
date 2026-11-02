from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import StatusPeriodo


class PeriodoOut(BaseModel):
    id: UUID
    ano: int
    mes: int
    status: StatusPeriodo
    fechado_em: datetime | None
    fechado_por: UUID | None

    model_config = {"from_attributes": True}


class ApuracaoIn(BaseModel):
    ano: int = Field(ge=1990, le=2100)
    conta_resultado_codigo: str = Field(description="Conta de PL que recebe o resultado (ex.: Lucros ou Prejuízos Acumulados)")
    historico: str | None = Field(default=None, max_length=2000)
