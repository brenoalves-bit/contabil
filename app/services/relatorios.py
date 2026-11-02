"""Relatórios contábeis calculados a partir das partidas de lançamentos não-rascunho.

Convenção de sinal: `raw` = débitos − créditos. Para exibição, saldo é apresentado
em valor absoluto acompanhado da natureza (D/C) que ele assume.
"""
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.models import (
    Conta,
    GrupoConta,
    Lancamento,
    NaturezaConta,
    Partida,
    Periodo,
    StatusLancamento,
)
from app.schemas.relatorio import (
    BalanceteOut,
    BalancoOut,
    DREOut,
    LinhaBalancete,
    LinhaDemonstrativo,
    LinhaRazao,
    RazaoOut,
)

ZERO = Decimal(0)


def _dc(raw: Decimal, natureza_conta: NaturezaConta) -> tuple[Decimal, NaturezaConta]:
    if raw > 0:
        return raw, NaturezaConta.D
    if raw < 0:
        return -raw, NaturezaConta.C
    return ZERO, natureza_conta


def _movimento(db: Session, empresa_id: UUID, inicio: date | None, fim: date | None) -> dict[UUID, tuple[Decimal, Decimal]]:
    q = (
        select(Partida.conta_id, func.sum(Partida.debito), func.sum(Partida.credito))
        .join(Lancamento, Lancamento.id == Partida.lancamento_id)
        .where(Partida.empresa_id == empresa_id, Lancamento.status != StatusLancamento.RASCUNHO)
        .group_by(Partida.conta_id)
    )
    if inicio is not None:
        q = q.where(Lancamento.data >= inicio)
    if fim is not None:
        q = q.where(Lancamento.data <= fim)
    return {cid: (Decimal(d), Decimal(c)) for cid, d, c in db.execute(q)}


@dataclass
class _No:
    conta: Conta
    filhos: list["_No"] = field(default_factory=list)
    ant_d: Decimal = ZERO
    ant_c: Decimal = ZERO
    mov_d: Decimal = ZERO
    mov_c: Decimal = ZERO


def _chave(codigo: str) -> tuple[int, ...]:
    return tuple(int(p) for p in codigo.split("."))


def _arvore(db: Session, empresa_id: UUID, anterior: dict, movimento: dict) -> list[_No]:
    contas = list(db.scalars(select(Conta).where(Conta.empresa_id == empresa_id)))
    nos = {c.id: _No(conta=c) for c in contas}
    for cid, (d, c) in anterior.items():
        if cid in nos:
            nos[cid].ant_d, nos[cid].ant_c = d, c
    for cid, (d, c) in movimento.items():
        if cid in nos:
            nos[cid].mov_d, nos[cid].mov_c = d, c
    raizes: list[_No] = []
    for no in nos.values():
        if no.conta.conta_pai_id and no.conta.conta_pai_id in nos:
            nos[no.conta.conta_pai_id].filhos.append(no)
        else:
            raizes.append(no)

    def consolidar(no: _No) -> None:
        for f in sorted(no.filhos, key=lambda n: _chave(n.conta.codigo)):
            consolidar(f)
            no.ant_d += f.ant_d
            no.ant_c += f.ant_c
            no.mov_d += f.mov_d
            no.mov_c += f.mov_c

    for r in raizes:
        consolidar(r)
    return raizes


def _achatar(raizes: list[_No]) -> list[_No]:
    out: list[_No] = []

    def visita(no: _No) -> None:
        out.append(no)
        for f in sorted(no.filhos, key=lambda n: _chave(n.conta.codigo)):
            visita(f)

    for r in sorted(raizes, key=lambda n: _chave(n.conta.codigo)):
        visita(r)
    return out


def _periodo_fechado(db: Session, empresa_id: UUID, fim: date) -> bool:
    return db.scalar(
        select(Periodo.id).where(
            Periodo.empresa_id == empresa_id,
            Periodo.ano == fim.year,
            Periodo.mes == fim.month,
            Periodo.status == "FECHADO",
        ).limit(1)
    ) is not None


# ---------------------------------------------------------------- razão
def razao(db: Session, empresa_id: UUID, conta_codigo: str, inicio: date, fim: date) -> RazaoOut:
    conta = db.scalar(select(Conta).where(Conta.empresa_id == empresa_id, Conta.codigo == conta_codigo))
    if conta is None:
        raise NotFound(f"conta {conta_codigo} não encontrada")
    ids_conta = [conta.id]
    if conta.tipo.value == "SINTETICA":
        ids_conta = [
            c.id for c in db.scalars(
                select(Conta).where(Conta.empresa_id == empresa_id, Conta.codigo.like(conta.codigo + ".%"))
            )
        ] + [conta.id]
    ant = db.execute(
        select(func.coalesce(func.sum(Partida.debito), 0), func.coalesce(func.sum(Partida.credito), 0))
        .join(Lancamento, Lancamento.id == Partida.lancamento_id)
        .where(
            Partida.conta_id.in_(ids_conta),
            Lancamento.status != StatusLancamento.RASCUNHO,
            Lancamento.data < inicio,
        )
    ).one()
    saldo = Decimal(ant[0]) - Decimal(ant[1])
    saldo_anterior, nat_ant = _dc(saldo, conta.natureza)
    rows = db.execute(
        select(Lancamento.data, Lancamento.id, Lancamento.numero, Lancamento.historico,
               Partida.historico_complementar, Partida.debito, Partida.credito)
        .join(Lancamento, Lancamento.id == Partida.lancamento_id)
        .where(
            Partida.conta_id.in_(ids_conta),
            Lancamento.status != StatusLancamento.RASCUNHO,
            Lancamento.data.between(inicio, fim),
        )
        .order_by(Lancamento.data, Lancamento.numero, Partida.ordem)
    ).all()
    linhas = []
    for data, lid, numero, hist, hist_c, d, c in rows:
        saldo += Decimal(d) - Decimal(c)
        v, n = _dc(saldo, conta.natureza)
        linhas.append(LinhaRazao(
            data=data, lancamento_id=lid, numero=numero, historico=hist, historico_complementar=hist_c,
            debito=Decimal(d), credito=Decimal(c), saldo=v, saldo_natureza=n,
        ))
    sf, nf = _dc(saldo, conta.natureza)
    return RazaoOut(
        conta_codigo=conta.codigo, conta_nome=conta.nome, natureza=conta.natureza, inicio=inicio, fim=fim,
        saldo_anterior=saldo_anterior, saldo_anterior_natureza=nat_ant, linhas=linhas,
        saldo_final=sf, saldo_final_natureza=nf,
    )


# ---------------------------------------------------------------- balancete
def balancete(db: Session, empresa_id: UUID, inicio: date, fim: date, *, somente_com_movimento: bool = False) -> BalanceteOut:
    anterior = _movimento(db, empresa_id, None, date.fromordinal(inicio.toordinal() - 1))
    movimento = _movimento(db, empresa_id, inicio, fim)
    nos = _achatar(_arvore(db, empresa_id, anterior, movimento))
    linhas: list[LinhaBalancete] = []
    tot_d = tot_c = tot_sd = tot_sc = ZERO
    for no in nos:
        c = no.conta
        raw_ant = no.ant_d - no.ant_c
        raw_atual = raw_ant + no.mov_d - no.mov_c
        if somente_com_movimento and raw_ant == 0 and no.mov_d == 0 and no.mov_c == 0:
            continue
        sa, na = _dc(raw_ant, c.natureza)
        s, n = _dc(raw_atual, c.natureza)
        linhas.append(LinhaBalancete(
            conta_id=c.id, codigo=c.codigo, nome=c.nome, grupo=c.grupo, natureza=c.natureza, tipo=c.tipo,
            nivel=c.nivel, saldo_anterior=sa, saldo_anterior_natureza=na, debitos=no.mov_d,
            creditos=no.mov_c, saldo_atual=s, saldo_atual_natureza=n,
        ))
        if c.tipo.value == "ANALITICA":
            tot_d += no.mov_d
            tot_c += no.mov_c
            if n == NaturezaConta.D:
                tot_sd += s
            else:
                tot_sc += s
    return BalanceteOut(
        inicio=inicio, fim=fim, linhas=linhas, total_debitos=tot_d, total_creditos=tot_c,
        total_saldo_devedor=tot_sd, total_saldo_credor=tot_sc, fechado=_periodo_fechado(db, empresa_id, fim),
    )


# ---------------------------------------------------------------- DRE
def _linhas_grupo(nos: list[_No], grupo: GrupoConta, sinal_credor: bool) -> tuple[list[LinhaDemonstrativo], Decimal]:
    linhas = []
    total = ZERO
    for no in nos:
        if no.conta.grupo != grupo:
            continue
        raw = (no.ant_d + no.mov_d) - (no.ant_c + no.mov_c)
        valor = -raw if sinal_credor else raw
        linhas.append(LinhaDemonstrativo(
            codigo=no.conta.codigo, nome=no.conta.nome, nivel=no.conta.nivel, tipo=no.conta.tipo, valor=valor,
        ))
        if no.conta.nivel == 1:
            total += valor
    return linhas, total


def dre(db: Session, empresa_id: UUID, inicio: date, fim: date) -> DREOut:
    movimento = _movimento(db, empresa_id, inicio, fim)
    nos = _achatar(_arvore(db, empresa_id, {}, movimento))
    receitas, tot_r = _linhas_grupo(nos, GrupoConta.RECEITA, sinal_credor=True)
    despesas, tot_d = _linhas_grupo(nos, GrupoConta.DESPESA, sinal_credor=False)
    return DREOut(
        inicio=inicio, fim=fim, receitas=receitas, despesas=despesas,
        total_receitas=tot_r, total_despesas=tot_d, resultado=tot_r - tot_d,
    )


# ---------------------------------------------------------------- balanço patrimonial
def balanco(db: Session, empresa_id: UUID, data: date) -> BalancoOut:
    acumulado = _movimento(db, empresa_id, None, data)
    nos = _achatar(_arvore(db, empresa_id, {}, acumulado))
    ativo, tot_a = _linhas_grupo(nos, GrupoConta.ATIVO, sinal_credor=False)
    passivo, tot_p = _linhas_grupo(nos, GrupoConta.PASSIVO, sinal_credor=True)
    pl, tot_pl = _linhas_grupo(nos, GrupoConta.PATRIMONIO_LIQUIDO, sinal_credor=True)
    _, tot_r = _linhas_grupo(nos, GrupoConta.RECEITA, sinal_credor=True)
    _, tot_d = _linhas_grupo(nos, GrupoConta.DESPESA, sinal_credor=False)
    resultado = tot_r - tot_d  # contas de resultado ainda não apuradas
    return BalancoOut(
        data=data, ativo=ativo, passivo=passivo, patrimonio_liquido=pl, resultado_periodo=resultado,
        total_ativo=tot_a, total_passivo=tot_p, total_patrimonio_liquido=tot_pl + resultado,
        total_passivo_e_pl=tot_p + tot_pl + resultado, fechado=_periodo_fechado(db, empresa_id, data),
    )
