from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import Conflict, Forbidden, NotFound, Unauthorized
from app.core.security import (
    create_access_token,
    hash_password,
    hash_refresh_token,
    new_refresh_token,
    verify_password,
)
from app.models import RefreshToken, Usuario
from app.schemas.auth import TokenOut, UsuarioCreate
from app.services import auditoria

MSG_CREDENCIAIS = "credenciais inválidas"


def _emitir_tokens(db: Session, u: Usuario) -> TokenOut:
    s = get_settings()
    raw, h = new_refresh_token()
    db.add(
        RefreshToken(
            usuario_id=u.id,
            token_hash=h,
            expira_em=datetime.now(UTC) + timedelta(days=s.refresh_token_days),
        )
    )
    return TokenOut(
        access_token=create_access_token(u.id, u.admin_escritorio),
        refresh_token=raw,
        expires_in=s.access_token_minutes * 60,
    )


def login(db: Session, email: str, senha: str, ip: str | None) -> TokenOut:
    s = get_settings()
    u = db.scalar(select(Usuario).where(func.lower(Usuario.email) == email.lower()))
    agora = datetime.now(UTC)
    if u is None:
        # Executa o hash mesmo assim para não vazar existência do usuário por tempo de resposta.
        verify_password(senha, hash_password("x" * 16))
        raise Unauthorized(MSG_CREDENCIAIS)
    if not u.ativo:
        raise Unauthorized(MSG_CREDENCIAIS)
    if u.bloqueado_ate and u.bloqueado_ate > agora:
        raise Unauthorized("usuário temporariamente bloqueado por excesso de tentativas", "bloqueado")
    if not verify_password(senha, u.senha_hash):
        u.falhas_login += 1
        if u.falhas_login >= s.max_login_failures:
            u.bloqueado_ate = agora + timedelta(minutes=s.lockout_minutes)
            u.falhas_login = 0
            auditoria.registrar(db, acao="login_bloqueado", entidade="usuario", entidade_id=u.id, ip=ip)
        else:
            auditoria.registrar(db, acao="login_falhou", entidade="usuario", entidade_id=u.id, ip=ip)
        db.commit()
        raise Unauthorized(MSG_CREDENCIAIS)
    u.falhas_login = 0
    u.bloqueado_ate = None
    auditoria.registrar(db, acao="login", entidade="usuario", entidade_id=u.id, usuario_id=u.id, ip=ip)
    return _emitir_tokens(db, u)


def refresh(db: Session, raw_token: str, ip: str | None) -> TokenOut:
    h = hash_refresh_token(raw_token)
    rt = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == h))
    agora = datetime.now(UTC)
    if rt is None or rt.expira_em < agora:
        raise Unauthorized("refresh token inválido")
    if rt.revogado_em is not None:
        # Reuso de token já rotacionado: possível roubo. Revoga tudo do usuário.
        db.query(RefreshToken).filter(
            RefreshToken.usuario_id == rt.usuario_id, RefreshToken.revogado_em.is_(None)
        ).update({"revogado_em": agora})
        auditoria.registrar(
            db, acao="refresh_reuso_detectado", entidade="usuario", entidade_id=rt.usuario_id, ip=ip
        )
        db.commit()
        raise Unauthorized("refresh token inválido")
    u = db.get(Usuario, rt.usuario_id)
    if u is None or not u.ativo:
        raise Unauthorized("refresh token inválido")
    rt.revogado_em = agora
    return _emitir_tokens(db, u)


def logout(db: Session, raw_token: str) -> None:
    h = hash_refresh_token(raw_token)
    rt = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == h))
    if rt and rt.revogado_em is None:
        rt.revogado_em = datetime.now(UTC)


def criar_usuario(db: Session, dados: UsuarioCreate, *, criado_por: UUID | None, ip: str | None) -> Usuario:
    existe = db.scalar(select(Usuario.id).where(func.lower(Usuario.email) == dados.email.lower()))
    if existe:
        raise Conflict("e-mail já cadastrado")
    u = Usuario(
        email=dados.email,
        nome=dados.nome,
        senha_hash=hash_password(dados.senha),
        admin_escritorio=dados.admin_escritorio,
    )
    db.add(u)
    db.flush()
    auditoria.registrar(
        db, acao="criar", entidade="usuario", entidade_id=u.id, usuario_id=criado_por,
        dados={"email": u.email, "admin_escritorio": u.admin_escritorio}, ip=ip,
    )
    return u


def trocar_senha(db: Session, u: Usuario, senha_atual: str, senha_nova: str, ip: str | None) -> None:
    if not verify_password(senha_atual, u.senha_hash):
        raise Forbidden("senha atual incorreta")
    u.senha_hash = hash_password(senha_nova)
    db.query(RefreshToken).filter(
        RefreshToken.usuario_id == u.id, RefreshToken.revogado_em.is_(None)
    ).update({"revogado_em": datetime.now(UTC)})
    auditoria.registrar(db, acao="trocar_senha", entidade="usuario", entidade_id=u.id, usuario_id=u.id, ip=ip)


def obter_usuario(db: Session, usuario_id: UUID) -> Usuario:
    u = db.get(Usuario, usuario_id)
    if u is None:
        raise NotFound("usuário não encontrado")
    return u
