"""Participantes (clientes/fornecedores), produtos e de-para de códigos."""
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import Conflict, NotFound
from app.models import Participante, Produto, ProdutoReferencia, TipoItem, TipoPessoa
from app.schemas.fiscal import (
    ParticipanteCreate,
    ParticipanteUpdate,
    ProdutoCreate,
    ProdutoReferenciaIn,
    ProdutoUpdate,
)
from app.services import auditoria
from app.services.contexto import Contexto


def _conflito(exc: IntegrityError, msg: str) -> Exception:
    db_msg = str(exc.orig).lower() if exc.orig else ""
    return Conflict(msg) if "unique" in db_msg or "duplicate" in db_msg else exc


# ---------------------------------------------------------------- participantes
def obter_participante(db: Session, empresa_id: UUID, pid: UUID) -> Participante:
    p = db.scalar(select(Participante).where(Participante.id == pid, Participante.empresa_id == empresa_id))
    if p is None:
        raise NotFound("participante não encontrado")
    return p


def participante_por_documento(db: Session, empresa_id: UUID, cnpj_cpf: str) -> Participante | None:
    return db.scalar(
        select(Participante).where(Participante.empresa_id == empresa_id, Participante.cnpj_cpf == cnpj_cpf)
    )


def listar_participantes(db: Session, empresa_id: UUID, *, q: str | None, ativo: bool | None, limit: int, offset: int):
    stmt = select(Participante).where(Participante.empresa_id == empresa_id)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Participante.razao_social.ilike(like), Participante.nome_fantasia.ilike(like),
                              Participante.cnpj_cpf.like(f"{''.join(ch for ch in q if ch.isdigit()) or '§'}%")))
    if ativo is not None:
        stmt = stmt.where(Participante.ativo == ativo)
    return list(db.scalars(stmt.order_by(Participante.razao_social).limit(limit).offset(offset)))


def criar_participante(db: Session, ctx: Contexto, dados: ParticipanteCreate) -> Participante:
    p = Participante(empresa_id=ctx.empresa_id, **dados.model_dump())
    db.add(p)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise _conflito(exc, "CNPJ/CPF já cadastrado nesta empresa") from exc
    auditoria.registrar(db, acao="criar", entidade="participante", entidade_id=p.id, empresa_id=ctx.empresa_id,
                        usuario_id=ctx.usuario.id, dados={"cnpj_cpf": p.cnpj_cpf, "razao_social": p.razao_social}, ip=ctx.ip)
    return p


def atualizar_participante(db: Session, ctx: Contexto, pid: UUID, dados: ParticipanteUpdate) -> Participante:
    p = obter_participante(db, ctx.empresa_id, pid)
    mudancas = dados.model_dump(exclude_unset=True)
    for k, v in mudancas.items():
        setattr(p, k, v)
    db.flush()
    auditoria.registrar(db, acao="atualizar", entidade="participante", entidade_id=p.id, empresa_id=ctx.empresa_id,
                        usuario_id=ctx.usuario.id, dados=mudancas, ip=ctx.ip)
    return p


def upsert_participante_xml(db: Session, empresa_id: UUID, dados: dict) -> Participante:
    """Cria o participante a partir dos dados do XML; se já existe, só completa campos vazios."""
    p = participante_por_documento(db, empresa_id, dados["cnpj_cpf"])
    if p is None:
        p = Participante(empresa_id=empresa_id, **dados)
        db.add(p)
        db.flush()
        return p
    for k, v in dados.items():
        if v and getattr(p, k, None) in (None, ""):
            setattr(p, k, v)
    return p


# ---------------------------------------------------------------- produtos
def obter_produto(db: Session, empresa_id: UUID, pid: UUID) -> Produto:
    p = db.scalar(select(Produto).where(Produto.id == pid, Produto.empresa_id == empresa_id))
    if p is None:
        raise NotFound("produto não encontrado")
    return p


def produto_por_codigo(db: Session, empresa_id: UUID, codigo: str) -> Produto | None:
    return db.scalar(select(Produto).where(Produto.empresa_id == empresa_id, Produto.codigo == codigo))


def listar_produtos(db: Session, empresa_id: UUID, *, q: str | None, tipo_item: TipoItem | None, ativo: bool | None,
                    limit: int, offset: int):
    stmt = select(Produto).where(Produto.empresa_id == empresa_id)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Produto.descricao.ilike(like), Produto.codigo.ilike(like), Produto.ean == q))
    if tipo_item is not None:
        stmt = stmt.where(Produto.tipo_item == tipo_item)
    if ativo is not None:
        stmt = stmt.where(Produto.ativo == ativo)
    return list(db.scalars(stmt.order_by(Produto.codigo).limit(limit).offset(offset)))


def criar_produto(db: Session, ctx: Contexto, dados: ProdutoCreate) -> Produto:
    p = Produto(empresa_id=ctx.empresa_id, **dados.model_dump())
    db.add(p)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise _conflito(exc, "código de produto já existe nesta empresa") from exc
    auditoria.registrar(db, acao="criar", entidade="produto", entidade_id=p.id, empresa_id=ctx.empresa_id,
                        usuario_id=ctx.usuario.id, dados={"codigo": p.codigo, "descricao": p.descricao}, ip=ctx.ip)
    return p


def atualizar_produto(db: Session, ctx: Contexto, pid: UUID, dados: ProdutoUpdate) -> Produto:
    p = obter_produto(db, ctx.empresa_id, pid)
    mudancas = dados.model_dump(exclude_unset=True)
    for k, v in mudancas.items():
        setattr(p, k, v)
    db.flush()
    auditoria.registrar(db, acao="atualizar", entidade="produto", entidade_id=p.id, empresa_id=ctx.empresa_id,
                        usuario_id=ctx.usuario.id, dados=mudancas, ip=ctx.ip)
    return p


def referencia(db: Session, empresa_id: UUID, participante_id: UUID, codigo_externo: str) -> ProdutoReferencia | None:
    return db.scalar(select(ProdutoReferencia).where(
        ProdutoReferencia.empresa_id == empresa_id,
        ProdutoReferencia.participante_id == participante_id,
        ProdutoReferencia.codigo_externo == codigo_externo,
    ))


def listar_referencias(db: Session, empresa_id: UUID, produto_id: UUID) -> list[ProdutoReferencia]:
    return list(db.scalars(select(ProdutoReferencia).where(
        ProdutoReferencia.empresa_id == empresa_id, ProdutoReferencia.produto_id == produto_id)))


def criar_referencia(db: Session, ctx: Contexto, produto_id: UUID, dados: ProdutoReferenciaIn) -> ProdutoReferencia:
    obter_produto(db, ctx.empresa_id, produto_id)
    obter_participante(db, ctx.empresa_id, dados.participante_id)
    ref = referencia(db, ctx.empresa_id, dados.participante_id, dados.codigo_externo)
    if ref is None:
        ref = ProdutoReferencia(empresa_id=ctx.empresa_id, participante_id=dados.participante_id,
                                codigo_externo=dados.codigo_externo, produto_id=produto_id)
        db.add(ref)
    else:
        ref.produto_id = produto_id
    db.flush()
    auditoria.registrar(db, acao="de_para", entidade="produto", entidade_id=produto_id, empresa_id=ctx.empresa_id,
                        usuario_id=ctx.usuario.id, dados=dados.model_dump(mode="json"), ip=ctx.ip)
    return ref


def tipo_pessoa_por_documento(doc: str | None, estrangeiro: bool = False) -> TipoPessoa:
    if estrangeiro or doc is None:
        return TipoPessoa.EXTERIOR
    return TipoPessoa.PJ if len(doc) == 14 else TipoPessoa.PF
