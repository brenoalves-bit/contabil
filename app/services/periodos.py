import calendar
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Integer, cast, literal, select
from sqlalchemy.orm import Session

from app.core.errors import NotFound, RegraContabil
from app.models import (
    Conta,
    GrupoConta,
    Lancamento,
    OrigemLancamento,
    Partida,
    Periodo,
    StatusLancamento,
    StatusPeriodo,
    TipoConta,
)
from app.schemas.periodo import ApuracaoIn
from app.services import auditoria
from app.services.contexto import Contexto


def _ano_mes():
    return cast(Periodo.ano, Integer) * 100 + cast(Periodo.mes, Integer)


def listar(db: Session, empresa_id: UUID) -> list[Periodo]:
    return list(
        db.scalars(
            select(Periodo).where(Periodo.empresa_id == empresa_id).order_by(Periodo.ano, Periodo.mes)
        )
    )


def obter_ou_criar(db: Session, empresa_id: UUID, ano: int, mes: int) -> Periodo:
    p = db.scalar(
        select(Periodo).where(Periodo.empresa_id == empresa_id, Periodo.ano == ano, Periodo.mes == mes)
    )
    if p is None:
        p = Periodo(empresa_id=empresa_id, ano=ano, mes=mes, status=StatusPeriodo.ABERTO)
        db.add(p)
        db.flush()
    return p


def garantir_aberto(db: Session, empresa_id: UUID, data: date) -> None:
    """Cria o período se não existir e falha se ele, ou algum posterior, estiver fechado.
    O trigger no banco repete essa checagem; aqui a mensagem é mais amigável."""
    fechado_posterior = db.scalar(
        select(Periodo).where(
            Periodo.empresa_id == empresa_id,
            Periodo.status == StatusPeriodo.FECHADO,
            _ano_mes() >= literal(data.year * 100 + data.month, Integer),
        ).limit(1)
    )
    if fechado_posterior:
        raise RegraContabil(
            f"período {data.month:02d}/{data.year} está fechado ou é anterior ao período fechado "
            f"{fechado_posterior.mes:02d}/{fechado_posterior.ano}"
        )
    obter_ou_criar(db, empresa_id, data.year, data.month)


def fechar(db: Session, ctx: Contexto, ano: int, mes: int) -> Periodo:
    p = obter_ou_criar(db, ctx.empresa_id, ano, mes)
    if p.status == StatusPeriodo.FECHADO:
        raise RegraContabil("período já está fechado")
    anterior_aberto = db.scalar(
        select(Periodo).where(
            Periodo.empresa_id == ctx.empresa_id,
            Periodo.status == StatusPeriodo.ABERTO,
            _ano_mes() < literal(ano * 100 + mes, Integer),
        ).order_by(Periodo.ano, Periodo.mes).limit(1)
    )
    if anterior_aberto:
        raise RegraContabil(
            f"feche primeiro o período {anterior_aberto.mes:02d}/{anterior_aberto.ano}"
        )
    inicio = date(ano, mes, 1)
    fim = date(ano, mes, calendar.monthrange(ano, mes)[1])
    rascunhos = db.scalar(
        select(Lancamento.id).where(
            Lancamento.empresa_id == ctx.empresa_id,
            Lancamento.status == StatusLancamento.RASCUNHO,
            Lancamento.data.between(inicio, fim),
        ).limit(1)
    )
    if rascunhos:
        raise RegraContabil("existem rascunhos no período; efetive ou exclua antes de fechar")
    p.status = StatusPeriodo.FECHADO
    p.fechado_em = datetime.now(UTC)
    p.fechado_por = ctx.usuario.id
    db.flush()
    auditoria.registrar(
        db, acao="fechar_periodo", entidade="periodo", entidade_id=p.id, empresa_id=ctx.empresa_id,
        usuario_id=ctx.usuario.id, dados={"ano": ano, "mes": mes}, ip=ctx.ip,
    )
    return p


def reabrir(db: Session, ctx: Contexto, ano: int, mes: int, motivo: str) -> Periodo:
    p = db.scalar(
        select(Periodo).where(Periodo.empresa_id == ctx.empresa_id, Periodo.ano == ano, Periodo.mes == mes)
    )
    if p is None:
        raise NotFound("período não encontrado")
    if p.status != StatusPeriodo.FECHADO:
        raise RegraContabil("período não está fechado")
    posterior_fechado = db.scalar(
        select(Periodo.id).where(
            Periodo.empresa_id == ctx.empresa_id,
            Periodo.status == StatusPeriodo.FECHADO,
            _ano_mes() > literal(ano * 100 + mes, Integer),
        ).limit(1)
    )
    if posterior_fechado:
        raise RegraContabil("reabra primeiro os períodos posteriores")
    p.status = StatusPeriodo.ABERTO
    p.fechado_em = None
    p.fechado_por = None
    db.flush()
    auditoria.registrar(
        db, acao="reabrir_periodo", entidade="periodo", entidade_id=p.id, empresa_id=ctx.empresa_id,
        usuario_id=ctx.usuario.id, dados={"ano": ano, "mes": mes, "motivo": motivo}, ip=ctx.ip,
    )
    return p


def apurar_resultado(db: Session, ctx: Contexto, dados: ApuracaoIn, inicio_exercicio_mes: int) -> Lancamento:
    """Encerramento do exercício: zera contas de resultado contra a conta de PL indicada.

    O exercício começa em `inicio_exercicio_mes` de `ano` e termina 12 meses depois.
    Gera um único lançamento de origem APURACAO datado no último dia do exercício.
    """
    from app.services import lancamentos  # import tardio: evita ciclo

    inicio = date(dados.ano, inicio_exercicio_mes, 1)
    if inicio_exercicio_mes == 1:
        fim = date(dados.ano, 12, 31)
    else:
        ano_fim, mes_fim = dados.ano + 1, inicio_exercicio_mes - 1
        fim = date(ano_fim, mes_fim, calendar.monthrange(ano_fim, mes_fim)[1])

    conta_resultado = db.scalar(
        select(Conta).where(Conta.empresa_id == ctx.empresa_id, Conta.codigo == dados.conta_resultado_codigo)
    )
    if conta_resultado is None:
        raise NotFound(f"conta {dados.conta_resultado_codigo} não encontrada")
    if conta_resultado.grupo != GrupoConta.PATRIMONIO_LIQUIDO or conta_resultado.tipo != TipoConta.ANALITICA:
        raise RegraContabil("conta de resultado deve ser analítica do Patrimônio Líquido")

    ja_apurado = db.scalar(
        select(Lancamento.id).where(
            Lancamento.empresa_id == ctx.empresa_id,
            Lancamento.origem == OrigemLancamento.APURACAO,
            Lancamento.status == StatusLancamento.EFETIVADO,
            Lancamento.data == fim,
        ).limit(1)
    )
    if ja_apurado:
        raise RegraContabil(f"exercício encerrado em {fim.isoformat()} já foi apurado; estorne antes de repetir")

    saldos = db.execute(
        select(Conta.id, Conta.codigo, (Partida.debito - Partida.credito).label("raw"))
        .join(Partida, Partida.conta_id == Conta.id)
        .join(Lancamento, Lancamento.id == Partida.lancamento_id)
        .where(
            Conta.empresa_id == ctx.empresa_id,
            Conta.grupo.in_([GrupoConta.RECEITA, GrupoConta.DESPESA]),
            Lancamento.status != StatusLancamento.RASCUNHO,
            Lancamento.data.between(inicio, fim),
        )
    ).all()
    por_conta: dict[UUID, Decimal] = {}
    for cid, _cod, raw in saldos:
        por_conta[cid] = por_conta.get(cid, Decimal(0)) + Decimal(raw)
    por_conta = {k: v for k, v in por_conta.items() if v != 0}
    if not por_conta:
        raise RegraContabil("não há movimento em contas de resultado no exercício")

    partidas: list[Partida] = []
    resultado = Decimal(0)  # positivo = lucro (créditos > débitos nas contas de resultado)
    for i, (cid, raw) in enumerate(sorted(por_conta.items(), key=lambda kv: str(kv[0]))):
        # raw > 0 => saldo devedor => credita para zerar; raw < 0 => debita.
        partidas.append(
            Partida(
                empresa_id=ctx.empresa_id, conta_id=cid, ordem=i,
                debito=-raw if raw < 0 else Decimal(0),
                credito=raw if raw > 0 else Decimal(0),
            )
        )
        resultado -= raw
    partidas.append(
        Partida(
            empresa_id=ctx.empresa_id, conta_id=conta_resultado.id, ordem=len(partidas),
            debito=-resultado if resultado < 0 else Decimal(0),
            credito=resultado if resultado > 0 else Decimal(0),
        )
    )
    lanc = Lancamento(
        empresa_id=ctx.empresa_id,
        data=fim,
        historico=dados.historico or f"Apuração do resultado do exercício {inicio.isoformat()} a {fim.isoformat()}",
        origem=OrigemLancamento.APURACAO,
        criado_por=ctx.usuario.id,
        partidas=partidas,
    )
    db.add(lanc)
    db.flush()
    lancamentos._efetivar(db, ctx, lanc)
    db.flush()
    auditoria.registrar(
        db, acao="apurar_resultado", entidade="lancamento", entidade_id=lanc.id, empresa_id=ctx.empresa_id,
        usuario_id=ctx.usuario.id,
        dados={"inicio": inicio, "fim": fim, "resultado": str(resultado), "numero": lanc.numero}, ip=ctx.ip,
    )
    return lanc
