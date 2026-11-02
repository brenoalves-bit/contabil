from decimal import ROUND_HALF_EVEN, Decimal
from typing import Annotated

from pydantic import PlainSerializer

_CENT = Decimal("0.01")


def _duas_casas(v: Decimal) -> str:
    return format(Decimal(v).quantize(_CENT, rounding=ROUND_HALF_EVEN), "f")


# Valor monetário de saída: sempre string com duas casas ("1234.50"), nunca float.
Dinheiro = Annotated[Decimal, PlainSerializer(_duas_casas, return_type=str, when_used="json")]
