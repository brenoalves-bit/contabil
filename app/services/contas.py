from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import Conflict, NotFound, RegraContabil
from app.models import CentroCusto, Conta, TipoConta
from app.schemas.conta import CentroCustoCreate, CentroCustoUpdate, ContaCreate, ContaUpdate
from app.services import auditoria
from app.services.contexto import Contexto
from app.services.plano_padrao import NATUREZA_PADRAO, PLANO


def _erro_integridade(exc: IntegrityError) -> Exception:
    msg = str(exc.orig).splitlines()[0] if exc.orig else str(exc)
    if "unique" in msg.lower() or "duplicate" in msg.lower():
        return Conflict("código já existe nesta empresa")
    return RegraContabil(msg)


def por_codigo(db: Session, empresa_id: UUID, codigo: str) -> Conta:
    c = db.scalar(select(Conta).where(Conta.empresa_id == empresa_id, Conta.codigo == codigo))
    if c is None:
        raise NotFound(f"conta {codigo} não encontrada")
    return c


def listar(db: Session, empresa_id: UUID, *, grupo=None, tipo=None, ativa: bool | None = None) -> list[Conta]:
    q = select(Conta).where(Conta.empresa_id == empresa_id)
    if grupo is not None:
        q = q.where(Conta.grupo == grupo)
    if tipo is not None:
        q = q.where(Conta.tipo == tipo)
    if ativa is not None:
        q = q.where(Conta.ativa == ativa)
    contas = list(db.scalars(q))
    return sorted(contas, key=lambda c: _chave_codigo(c.codigo))


def _chave_codigo(codigo: str) -> tuple[int, ...]:
    return tuple(int(p) for p in codigo.split("."))


def criar(db: Session, ctx: Contexto, dados: ContaCreate) -> Conta:
    pai_id = None
    if dados.conta_pai_codigo:
        pai_id = por_codigo(db, ctx.empresa_id, dados.conta_pai_codigo).id
    c = Conta(
        empresa_id=ctx.empresa_id,
        codigo=dados.codigo,
        nome=dados.nome,
        grupo=dados.grupo,
        natureza=dados.natureza,
        tipo=dados.tipo,
        conta_pai_id=pai_id,
        codigo_referencial=dados.codigo_referencial,
    )
    db.add(c)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise _erro_integridade(exc) from exc
    db.refresh(c)  # nivel é calculado pelo trigger
    auditoria.registrar(
        db, acao="criar", entidade="conta", entidade_id=c.id, empresa_id=ctx.empresa_id,
        usuario_id=ctx.usuario.id, dados=dados.model_dump(mode="json"), ip=ctx.ip,
    )
    return c


def atualizar(db: Session, ctx: Contexto, codigo: str, dados: ContaUpdate) -> Conta:
    c = por_codigo(db, ctx.empresa_id, codigo)
    mudancas = dados.model_dump(exclude_unset=True)
    for k, v in mudancas.items():
        setattr(c, k, v)
    db.flush()
    auditoria.registrar(
        db, acao="atualizar", entidade="conta", entidade_id=c.id, empresa_id=ctx.empresa_id,
        usuario_id=ctx.usuario.id, dados=mudancas, ip=ctx.ip,
    )
    return c


def criar_plano_padrao(db: Session, empresa_id: UUID, *, completar: bool = False) -> int:
    """Carrega o plano padrão. Em empresa que já tem contas, só com `completar=True`:
    insere apenas os códigos ausentes e não altera nada do que existe."""
    existentes: dict[str, Conta] = {c.codigo: c for c in db.scalars(select(Conta).where(Conta.empresa_id == empresa_id))}
    if existentes and not completar:
        raise Conflict("empresa já possui plano de contas; use completar=true para inserir só as contas faltantes")
    codigos_com_filhas = set()
    todos = [p[0] for p in PLANO]
    for cod in todos:
        for outro in todos:
            if outro != cod and outro.startswith(cod + "."):
                codigos_com_filhas.add(cod)
                break
    criadas: dict[str, Conta] = dict(existentes)
    novas = 0
    for codigo, nome, grupo, natureza in PLANO:
        if codigo in existentes:
            continue
        pai = None
        partes = codigo.split(".")
        for n in range(len(partes) - 1, 0, -1):
            cand = ".".join(partes[:n])
            if cand in criadas:
                pai = criadas[cand]
                break
        c = Conta(
            empresa_id=empresa_id,
            codigo=codigo,
            nome=nome,
            grupo=grupo,
            natureza=natureza or NATUREZA_PADRAO[grupo],
            tipo=TipoConta.SINTETICA if codigo in codigos_com_filhas else TipoConta.ANALITICA,
            conta_pai_id=pai.id if pai else None,
        )
        db.add(c)
        db.flush()
        criadas[codigo] = c
        novas += 1
    return novas


# ---------------------------------------------------------------- centros de custo
def centro_por_codigo(db: Session, empresa_id: UUID, codigo: str) -> CentroCusto:
    cc = db.scalar(
        select(CentroCusto).where(CentroCusto.empresa_id == empresa_id, CentroCusto.codigo == codigo)
    )
    if cc is None:
        raise NotFound(f"centro de custo {codigo} não encontrado")
    return cc


def listar_centros(db: Session, empresa_id: UUID) -> list[CentroCusto]:
    return list(
        db.scalars(select(CentroCusto).where(CentroCusto.empresa_id == empresa_id).order_by(CentroCusto.codigo))
    )


def criar_centro(db: Session, ctx: Contexto, dados: CentroCustoCreate) -> CentroCusto:
    cc = CentroCusto(empresa_id=ctx.empresa_id, codigo=dados.codigo, nome=dados.nome)
    db.add(cc)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise _erro_integridade(exc) from exc
    auditoria.registrar(
        db, acao="criar", entidade="centro_custo", entidade_id=cc.id, empresa_id=ctx.empresa_id,
        usuario_id=ctx.usuario.id, dados=dados.model_dump(), ip=ctx.ip,
    )
    return cc


def atualizar_centro(db: Session, ctx: Contexto, codigo: str, dados: CentroCustoUpdate) -> CentroCusto:
    cc = centro_por_codigo(db, ctx.empresa_id, codigo)
    mudancas = dados.model_dump(exclude_unset=True)
    for k, v in mudancas.items():
        setattr(cc, k, v)
    db.flush()
    auditoria.registrar(
        db, acao="atualizar", entidade="centro_custo", entidade_id=cc.id, empresa_id=ctx.empresa_id,
        usuario_id=ctx.usuario.id, dados=mudancas, ip=ctx.ip,
    )
    return cc
