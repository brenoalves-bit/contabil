import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.api.v1 import router as v1
from app.core.config import get_settings
from app.core.errors import DomainError

log = logging.getLogger("fiber")
settings = get_settings()

app = FastAPI(
    title="Fiber Finance — Contabilidade",
    version="0.1.0",
    description="Núcleo contábil multiempresa: plano de contas, lançamentos de partidas dobradas, "
                "períodos, razão, balancete, DRE e balanço patrimonial.",
    docs_url="/docs" if settings.env != "prod" else None,
    redoc_url=None,
)

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
        allow_methods=["*"], allow_headers=["Authorization", "Content-Type"],
    )


@app.middleware("http")
async def cabecalhos_seguranca(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Cache-Control"] = "no-store"
    if settings.env == "prod":
        resp.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return resp


@app.exception_handler(DomainError)
async def erro_dominio(_: Request, exc: DomainError):
    return JSONResponse(status_code=exc.status_code, content={"code": exc.code, "detail": exc.message})


@app.exception_handler(IntegrityError)
async def erro_integridade(_: Request, exc: IntegrityError):
    msg = str(exc.orig).splitlines()[0] if exc.orig else "violação de integridade"
    log.warning("integridade: %s", msg)
    return JSONResponse(status_code=422, content={"code": "regra_contabil", "detail": msg})


@app.get("/health", tags=["infra"])
def health():
    return {"status": "ok"}


app.include_router(v1)
