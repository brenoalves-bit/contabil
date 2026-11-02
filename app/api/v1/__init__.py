from fastapi import APIRouter

from app.api.v1 import (
    auditoria,
    auth,
    contas,
    empresas,
    lancamentos,
    periodos,
    relatorios,
    usuarios,
)

router = APIRouter(prefix="/api/v1")
for r in (auth, usuarios, empresas, contas, lancamentos, periodos, relatorios, auditoria):
    router.include_router(r.router)
