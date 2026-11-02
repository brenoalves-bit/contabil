from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, Path, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.db import get_db, set_tenant
from app.core.errors import Forbidden, NotFound, Unauthorized
from app.core.security import decode_access_token
from app.models import PapelEmpresa, Usuario
from app.services import empresas as svc_empresas
from app.services.contexto import Contexto

_bearer = HTTPBearer(auto_error=False)

DB = Annotated[Session, Depends(get_db)]


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def usuario_atual(
    db: DB,
    cred: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Usuario:
    if cred is None or cred.scheme.lower() != "bearer":
        raise Unauthorized("token ausente")
    try:
        payload = decode_access_token(cred.credentials)
    except jwt.PyJWTError as exc:
        raise Unauthorized("token inválido ou expirado") from exc
    u = db.get(Usuario, UUID(payload["sub"]))
    if u is None or not u.ativo:
        raise Unauthorized("usuário inativo")
    return u


UsuarioAtual = Annotated[Usuario, Depends(usuario_atual)]


def admin_escritorio(u: UsuarioAtual) -> Usuario:
    if not u.admin_escritorio:
        raise Forbidden("requer administrador do escritório")
    return u


AdminEscritorio = Annotated[Usuario, Depends(admin_escritorio)]


def _tenant(minimo: PapelEmpresa):
    def dep(
        request: Request,
        db: DB,
        u: UsuarioAtual,
        empresa_id: Annotated[UUID, Path()],
    ) -> Contexto:
        papel = svc_empresas.papel_de(db, u, empresa_id)
        if papel is None:
            # 404, não 403: não revelar a existência de empresas alheias.
            raise NotFound("empresa não encontrada")
        if svc_empresas.obter(db, empresa_id) is None:
            raise NotFound("empresa não encontrada")
        ctx = Contexto(usuario=u, empresa_id=empresa_id, papel=papel, ip=_ip(request))
        if not ctx.pode(minimo):
            raise Forbidden(f"requer papel {minimo.value} nesta empresa")
        set_tenant(db, empresa_id, u.id)
        return ctx

    return dep


Leitura = Annotated[Contexto, Depends(_tenant(PapelEmpresa.LEITURA))]
Contador = Annotated[Contexto, Depends(_tenant(PapelEmpresa.CONTADOR))]
AdminEmpresa = Annotated[Contexto, Depends(_tenant(PapelEmpresa.ADMIN))]
