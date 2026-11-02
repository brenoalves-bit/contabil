from fastapi import APIRouter, Request, status

from app.api.deps import DB, UsuarioAtual
from app.schemas.auth import LoginIn, RefreshIn, TokenOut, TrocarSenhaIn, UsuarioOut
from app.services import auth as svc

router = APIRouter(prefix="/auth", tags=["auth"])


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.post("/login", response_model=TokenOut)
def login(dados: LoginIn, db: DB, request: Request):
    return svc.login(db, dados.email, dados.senha, _ip(request))


@router.post("/refresh", response_model=TokenOut)
def refresh(dados: RefreshIn, db: DB, request: Request):
    return svc.refresh(db, dados.refresh_token, _ip(request))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(dados: RefreshIn, db: DB, _: UsuarioAtual):
    svc.logout(db, dados.refresh_token)


@router.get("/me", response_model=UsuarioOut)
def me(u: UsuarioAtual):
    return u


@router.post("/trocar-senha", status_code=status.HTTP_204_NO_CONTENT)
def trocar_senha(dados: TrocarSenhaIn, db: DB, u: UsuarioAtual, request: Request):
    svc.trocar_senha(db, u, dados.senha_atual, dados.senha_nova, _ip(request))
