"""Contexto da requisição dentro de uma empresa (tenant)."""
from dataclasses import dataclass
from uuid import UUID

from app.models import PapelEmpresa, Usuario

_ORDEM = {PapelEmpresa.LEITURA: 0, PapelEmpresa.CONTADOR: 1, PapelEmpresa.ADMIN: 2}


@dataclass(frozen=True)
class Contexto:
    usuario: Usuario
    empresa_id: UUID
    papel: PapelEmpresa
    ip: str | None = None

    def pode(self, minimo: PapelEmpresa) -> bool:
        return _ORDEM[self.papel] >= _ORDEM[minimo]
