from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import Conflict, NotFound, RegraContabil
from app.models import Conta, Lancamento, OrigemLancamento, Partida, StatusLancamento
from app.schemas.lancamento import (
    EstornoIn,
    LancamentoCreate,
    LancamentoOut,
    LancamentoUpdate,
    PartidaIn,
    PartidaOut,
)
from app.services import auditoria, contas, periodos
from app.services.contexto import Contexto


def _erro_integridade(exc: IntegrityError) -> Exception:
    msg = str(exc.orig).splitlines()[0] if exc.orig else str(exc)
    low = msg.lower()
    if "chave_externa" in low:
        return Conflict("chave_externa já utilizada nesta empresa")
    return RegraContabil(msg)


def obter(db: Session, empresa_id: UUID, lancamento_id: UUID) -> Lancamento:
    lanc = db.scalar(
        select(Lancamento).where(Lancamento.id == lancamento_id, Lancamento.empresa_id == empresa_id)
    )
    if lanc is None:
        raise NotFound("lançamento não encontrado")
    return lanc


def _montar_partidas(db: Session, ctx: Contexto, partidas: list[PartidaIn]) -> list[Partida]:
    out = []
    for i, p in enumerate(partidas):
        conta = contas.por_codigo(db, ctx.empresa_id, p.conta_codigo)
        cc_id = None
        if p.centro_custo_codigo:
            cc_id = contas.centro_por_codigo(db, ctx.empresa_id, p.centro_custo_codigo).id
        out.append(
            Partida(
                empresa_id=ctx.empresa_id,
                conta_id=conta.id,
                centro_custo_id=cc_id,
                ordem=i,
                debito=p.debito,
                credito=p.credito,
                historico_complementar=p.historico_complementar,
            )
        )
    return out


def _proximo_numero(db: Session, empresa_id: UUID) -> int:
    # UPDATE com RETURNING trava a linha da empresa: numeração sequencial sem corrida.
    return db.execute(
        text(
            "UPDATE empresa SET proximo_numero_lancamento = proximo_numero_lancamento + 1 "
            "WHERE id = :e RETURNING proximo_numero_lancamento - 1"
        ),
        {"e": str(empresa_id)},
    ).scalar_one()


def _efetivar(db: Session, ctx: Contexto, lanc: Lancamento) -> None:
    if lanc.status != StatusLancamento.RASCUNHO:
        raise RegraContabil("somente rascunhos podem ser efetivados")
    d = sum((p.debito for p in lanc.partidas), Decimal(0))
    c = sum((p.credito for p in lanc.partidas), Decimal(0))
    if len(lanc.partidas) < 2 or d != c:
        raise RegraContabil(f"lançamento desbalanceado: débitos {d} ≠ créditos {c}")
    periodos.garantir_aberto(db, ctx.empresa_id, lanc.data)
    lanc.numero = _proximo_numero(db, ctx.empresa_id)
    lanc.status = StatusLancamento.EFETIVADO
    lanc.efetivado_em = datetime.now(UTC)
    lanc.efetivado_por = ctx.usuario.id


def criar(db: Session, ctx: Contexto, dados: LancamentoCreate) -> Lancamento:
    lanc = Lancamento(
        empresa_id=ctx.empresa_id,
        data=dados.data,
        historico=dados.historico,
        origem=dados.origem,
        chave_externa=dados.chave_externa,
        criado_por=ctx.usuario.id,
        partidas=_montar_partidas(db, ctx, dados.partidas),
    )
    db.add(lanc)
    try:
        db.flush()
        if dados.efetivar:
            _efetivar(db, ctx, lanc)
            db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise _erro_integridade(exc) from exc
    auditoria.registrar(
        db, acao="efetivar" if dados.efetivar else "criar_rascunho", entidade="lancamento",
        entidade_id=lanc.id, empresa_id=ctx.empresa_id, usuario_id=ctx.usuario.id,
        dados={"numero": lanc.numero, "data": lanc.data, "origem": lanc.origem.value,
               "chave_externa": lanc.chave_externa, "partidas": len(lanc.partidas)},
        ip=ctx.ip,
    )
    return lanc


def atualizar_rascunho(db: Session, ctx: Contexto, lancamento_id: UUID, dados: LancamentoUpdate) -> Lancamento:
    lanc = obter(db, ctx.empresa_id, lancamento_id)
    if lanc.status != StatusLancamento.RASCUNHO:
        raise RegraContabil("somente rascunhos podem ser editados; use estorno")
    if dados.data is not None:
        lanc.data = dados.data
    if dados.historico is not None:
        lanc.historico = dados.historico
    if dados.partidas is not None:
        lanc.partidas = _montar_partidas(db, ctx, dados.partidas)
    db.flush()
    auditoria.registrar(
        db, acao="atualizar_rascunho", entidade="lancamento", entidade_id=lanc.id,
        empresa_id=ctx.empresa_id, usuario_id=ctx.usuario.id,
        dados=dados.model_dump(mode="json", exclude_unset=True), ip=ctx.ip,
    )
    return lanc


def excluir_rascunho(db: Session, ctx: Contexto, lancamento_id: UUID) -> None:
    lanc = obter(db, ctx.empresa_id, lancamento_id)
    if lanc.status != StatusLancamento.RASCUNHO:
        raise RegraContabil("somente rascunhos podem ser excluídos; use estorno")
    db.delete(lanc)
    db.flush()
    auditoria.registrar(
        db, acao="excluir_rascunho", entidade="lancamento", entidade_id=lancamento_id,
        empresa_id=ctx.empresa_id, usuario_id=ctx.usuario.id, ip=ctx.ip,
    )


def efetivar(db: Session, ctx: Contexto, lancamento_id: UUID) -> Lancamento:
    lanc = obter(db, ctx.empresa_id, lancamento_id)
    try:
        _efetivar(db, ctx, lanc)
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise _erro_integridade(exc) from exc
    auditoria.registrar(
        db, acao="efetivar", entidade="lancamento", entidade_id=lanc.id, empresa_id=ctx.empresa_id,
        usuario_id=ctx.usuario.id, dados={"numero": lanc.numero, "data": lanc.data}, ip=ctx.ip,
    )
    return lanc


def estornar(db: Session, ctx: Contexto, lancamento_id: UUID, dados: EstornoIn) -> Lancamento:
    original = obter(db, ctx.empresa_id, lancamento_id)
    if original.status != StatusLancamento.EFETIVADO:
        raise RegraContabil("somente lançamentos efetivados podem ser estornados")
    if dados.data < original.data:
        raise RegraContabil("data do estorno não pode ser anterior à do lançamento original")
    estorno = Lancamento(
        empresa_id=ctx.empresa_id,
        data=dados.data,
        historico=dados.historico or f"Estorno do lançamento nº {original.numero}: {original.historico}",
        origem=OrigemLancamento.ESTORNO,
        estorno_de_id=original.id,
        criado_por=ctx.usuario.id,
        partidas=[
            Partida(
                empresa_id=ctx.empresa_id,
                conta_id=p.conta_id,
                centro_custo_id=p.centro_custo_id,
                ordem=p.ordem,
                debito=p.credito,
                credito=p.debito,
                historico_complementar=p.historico_complementar,
            )
            for p in original.partidas
        ],
    )
    db.add(estorno)
    try:
        db.flush()
        _efetivar(db, ctx, estorno)
        db.flush()
        original.status = StatusLancamento.ESTORNADO
        original.estornado_por_id = estorno.id
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise _erro_integridade(exc) from exc
    auditoria.registrar(
        db, acao="estornar", entidade="lancamento", entidade_id=original.id, empresa_id=ctx.empresa_id,
        usuario_id=ctx.usuario.id,
        dados={"estorno_id": str(estorno.id), "estorno_numero": estorno.numero, "data": dados.data},
        ip=ctx.ip,
    )
    return estorno


def listar(
    db: Session,
    empresa_id: UUID,
    *,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    status: StatusLancamento | None = None,
    conta_codigo: str | None = None,
    texto: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Lancamento], int]:
    q = select(Lancamento).where(Lancamento.empresa_id == empresa_id)
    if data_inicio:
        q = q.where(Lancamento.data >= data_inicio)
    if data_fim:
        q = q.where(Lancamento.data <= data_fim)
    if status:
        q = q.where(Lancamento.status == status)
    if texto:
        q = q.where(Lancamento.historico.ilike(f"%{texto}%"))
    if conta_codigo:
        conta = contas.por_codigo(db, empresa_id, conta_codigo)
        q = q.where(
            Lancamento.id.in_(select(Partida.lancamento_id).where(Partida.conta_id == conta.id))
        )
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.scalars(
        q.order_by(Lancamento.data.desc(), Lancamento.numero.desc().nulls_first(), Lancamento.criado_em.desc())
        .limit(limit).offset(offset)
    )
    return list(rows), total


def para_saida(db: Session, lancs: list[Lancamento]) -> list[LancamentoOut]:
    ids = {p.conta_id for lanc in lancs for p in lanc.partidas}
    nomes: dict[UUID, Conta] = {}
    if ids:
        nomes = {c.id: c for c in db.scalars(select(Conta).where(Conta.id.in_(ids)))}
    out = []
    for lanc in lancs:
        partidas = [
            PartidaOut(
                id=p.id,
                conta_id=p.conta_id,
                conta_codigo=nomes[p.conta_id].codigo,
                conta_nome=nomes[p.conta_id].nome,
                centro_custo_id=p.centro_custo_id,
                ordem=p.ordem,
                debito=p.debito,
                credito=p.credito,
                historico_complementar=p.historico_complementar,
            )
            for p in lanc.partidas
        ]
        out.append(
            LancamentoOut(
                id=lanc.id, numero=lanc.numero, data=lanc.data, historico=lanc.historico,
                status=lanc.status, origem=lanc.origem, chave_externa=lanc.chave_externa,
                estorno_de_id=lanc.estorno_de_id, estornado_por_id=lanc.estornado_por_id,
                criado_por=lanc.criado_por, efetivado_em=lanc.efetivado_em, criado_em=lanc.criado_em,
                total_debito=sum((p.debito for p in partidas), Decimal(0)),
                total_credito=sum((p.credito for p in partidas), Decimal(0)),
                partidas=partidas,
            )
        )
    return out
