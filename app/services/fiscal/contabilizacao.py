"""Contabilização automática de documentos fiscais.

Um documento é dividido em grupos (CFOP, tipo de item). Para cada grupo calcula-se um mapa de
componentes de valor (PRODUTOS, ICMS, IPI, TOTAL, ...). A regra de contabilização escolhida para o
grupo diz, linha a linha, qual componente vai a débito/crédito de qual conta. A linha RESIDUAL recebe
o que falta para o grupo fechar, no lado necessário. Componentes com valor zero não geram partida.

Retenções (ISS retido, IRRF, PIS/COFINS/CSLL, INSS) são do documento, não do item: entram no primeiro
grupo. ISS = ISS próprio (total − retido); ISS_RETIDO = retido pelo tomador.
"""
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFound, RegraContabil
from app.models import (
    ComponenteFiscal as C,
)
from app.models import (
    Conta,
    DocumentoFiscal,
    DocumentoFiscalItem,
    Lancamento,
    ModeloDocumento,
    NaturezaConta,
    OrigemLancamento,
    Partida,
    Produto,
    RegimeTributario,
    RegraContabilizacao,
    RegraContabilizacaoLinha,
    StatusDocumento,
    StatusLancamento,
    TipoItem,
    TipoOperacao,
)
from app.schemas.fiscal import (
    PartidaPrevia,
    PreviaContabilizacao,
    RegraCreate,
    RegraLinhaIn,
    RegraUpdate,
)
from app.services import auditoria, contas, lancamentos
from app.services.contexto import Contexto
from app.services.fiscal import documentos as svc_docs

D0 = Decimal(0)
RETENCOES = {
    C.ISS_RETIDO: "valor_iss_retido", C.IRRF_RETIDO: "valor_irrf_retido", C.PIS_RETIDO: "valor_pis_retido",
    C.COFINS_RETIDO: "valor_cofins_retido", C.CSLL_RETIDA: "valor_csll_retida", C.INSS_RETIDO: "valor_inss_retido",
}
MODELO_LABEL = {ModeloDocumento.NFE: "NF-e", ModeloDocumento.NFCE: "NFC-e", ModeloDocumento.NFSE: "NFS-e", ModeloDocumento.CTE: "CT-e"}


@dataclass
class Grupo:
    cfop: str | None
    tipo_item: TipoItem | None
    itens: list[DocumentoFiscalItem] = field(default_factory=list)
    comp: dict[C, Decimal] = field(default_factory=dict)

    @property
    def chave(self) -> str:
        return f"CFOP {self.cfop or '-'}" + (f" / {self.tipo_item.value}" if self.tipo_item else "")


def agrupar(doc: DocumentoFiscal, produtos: dict[UUID, Produto]) -> list[Grupo]:
    grupos: dict[tuple, Grupo] = {}
    for it in doc.itens:
        if not it.compoe_total:
            continue
        ti = produtos[it.produto_id].tipo_item if it.produto_id in produtos else None
        g = grupos.setdefault((it.cfop, ti), Grupo(cfop=it.cfop, tipo_item=ti))
        g.itens.append(it)
    out = list(grupos.values())
    for g in out:
        def s(attr: str, itens=g.itens) -> Decimal:
            return sum((getattr(i, attr) for i in itens), D0)

        comp = {
            C.PRODUTOS: sum((i.valor_bruto for i in g.itens if not i.codigo_servico), D0),
            C.SERVICOS: sum((i.valor_bruto for i in g.itens if i.codigo_servico), D0),
            C.FRETE: s("valor_frete"), C.SEGURO: s("valor_seguro"), C.DESCONTO: s("valor_desconto"),
            C.OUTRAS: s("valor_outras"), C.IPI: s("ipi_valor"), C.ICMS: s("icms_valor"), C.ICMS_ST: s("icms_st_valor"),
            C.PIS: s("pis_valor"), C.COFINS: s("cofins_valor"), C.ISS: s("iss_valor"),
        }
        comp[C.TOTAL] = (comp[C.PRODUTOS] + comp[C.SERVICOS] + comp[C.FRETE] + comp[C.SEGURO] + comp[C.OUTRAS]
                         + comp[C.IPI] + comp[C.ICMS_ST] - comp[C.DESCONTO])
        for k in RETENCOES:
            comp[k] = D0
        comp[C.LIQUIDO] = comp[C.TOTAL]
        g.comp = comp
    if out:
        primeiro = out[0]
        ret_total = D0
        for k, attr in RETENCOES.items():
            v = getattr(doc, attr) or D0
            primeiro.comp[k] = v
            ret_total += v
        primeiro.comp[C.ISS] = max(primeiro.comp[C.ISS] - primeiro.comp[C.ISS_RETIDO], D0)
        primeiro.comp[C.LIQUIDO] = primeiro.comp[C.TOTAL] - ret_total
    return out


def _casa(r: RegraContabilizacao, doc: DocumentoFiscal, g: Grupo) -> int | None:
    """Retorna a especificidade da regra se ela casa com o grupo, senão None."""
    if not r.ativa:
        return None
    esp = 0
    if r.modelo is not None:
        if r.modelo != doc.modelo:
            return None
        esp += 1
    if r.tipo_operacao is not None:
        if r.tipo_operacao != doc.tipo_operacao:
            return None
        esp += 1
    if r.cfops:
        if g.cfop is None or not any(g.cfop.startswith(p) for p in r.cfops):
            return None
        esp += 2 + max(len(p) for p in r.cfops if g.cfop.startswith(p))
    if r.tipo_item is not None:
        if r.tipo_item != g.tipo_item:
            return None
        esp += 1
    return esp


def escolher_regra(regras: list[RegraContabilizacao], doc: DocumentoFiscal, g: Grupo) -> RegraContabilizacao | None:
    candidatas = []
    for r in regras:
        esp = _casa(r, doc, g)
        if esp is not None:
            candidatas.append((r.prioridade, esp, r.nome, r))
    if not candidatas:
        return None
    candidatas.sort(key=lambda t: (-t[0], -t[1], t[2]))
    return candidatas[0][3]


@dataclass
class PartidaCalc:
    conta: Conta
    lado: NaturezaConta
    valor: Decimal
    componente: C
    cfop: str | None
    regra: str


def calcular(db: Session, empresa_id: UUID, doc: DocumentoFiscal) -> tuple[list[PartidaCalc], list[str], list[str]]:
    ids = {i.produto_id for i in doc.itens if i.produto_id}
    produtos = {p.id: p for p in db.scalars(select(Produto).where(Produto.id.in_(ids)))} if ids else {}
    regras = list(db.scalars(select(RegraContabilizacao).where(RegraContabilizacao.empresa_id == empresa_id)))
    conta_ids = {ln.conta_id for r in regras for ln in r.linhas}
    contas_map = {c.id: c for c in db.scalars(select(Conta).where(Conta.id.in_(conta_ids)))} if conta_ids else {}

    partidas: list[PartidaCalc] = []
    sem_regra: list[str] = []
    avisos: list[str] = []
    grupos = agrupar(doc, produtos)
    soma_total = sum((g.comp[C.TOTAL] for g in grupos), D0)
    if abs(soma_total - doc.valor_total) > Decimal("0.05"):
        avisos.append(f"soma dos itens ({soma_total}) difere do total do documento ({doc.valor_total})")
    for g in grupos:
        r = escolher_regra(regras, doc, g)
        if r is None:
            sem_regra.append(g.chave)
            continue
        if not r.contabilizar:
            avisos.append(f"{g.chave}: regra '{r.nome}' sem efeito contábil")
            continue
        d = c = D0
        residual: RegraContabilizacaoLinha | None = None
        for ln in r.linhas:
            if ln.componente == C.RESIDUAL:
                residual = ln
                continue
            v = g.comp.get(ln.componente, D0)
            if v <= 0:
                continue
            partidas.append(PartidaCalc(contas_map[ln.conta_id], ln.lado, v, ln.componente, g.cfop, r.nome))
            if ln.lado == NaturezaConta.D:
                d += v
            else:
                c += v
        diff = d - c
        if residual is not None and diff != 0:
            lado = NaturezaConta.C if diff > 0 else NaturezaConta.D
            partidas.append(PartidaCalc(contas_map[residual.conta_id], lado, abs(diff), C.RESIDUAL, g.cfop, r.nome))
        elif diff != 0:
            raise RegraContabil(f"regra '{r.nome}' não fecha para {g.chave}: débitos {d} ≠ créditos {c}")
    return partidas, sem_regra, avisos


def _historico(doc: DocumentoFiscal, regra_nome: str | None, modelo_hist: str | None) -> str:
    nome = doc.participante.razao_social if doc.participante else "consumidor"
    base = modelo_hist or "{modelo} {numero}/{serie} - {participante}"
    try:
        return base.format(modelo=MODELO_LABEL[doc.modelo], numero=doc.numero, serie=doc.serie, participante=nome,
                           natureza=doc.natureza_operacao or "", chave=doc.chave_acesso or "")[:2000]
    except (KeyError, IndexError):
        return f"{MODELO_LABEL[doc.modelo]} {doc.numero}/{doc.serie} - {nome}"


def _data_contabil(doc: DocumentoFiscal) -> date:
    if doc.tipo_operacao == TipoOperacao.ENTRADA and doc.data_entrada_saida:
        return doc.data_entrada_saida
    return doc.data_emissao


def previa(db: Session, ctx: Contexto, doc_id: UUID) -> PreviaContabilizacao:
    doc = svc_docs.obter(db, ctx.empresa_id, doc_id)
    partidas, sem_regra, avisos = calcular(db, ctx.empresa_id, doc)
    regra0 = partidas[0].regra if partidas else None
    return PreviaContabilizacao(
        data=_data_contabil(doc), historico=_historico(doc, regra0, None),
        partidas=[PartidaPrevia(conta_codigo=p.conta.codigo, conta_nome=p.conta.nome,
                                debito=p.valor if p.lado == NaturezaConta.D else D0,
                                credito=p.valor if p.lado == NaturezaConta.C else D0,
                                componente=p.componente, cfop=p.cfop, regra=p.regra) for p in partidas],
        total_debito=sum((p.valor for p in partidas if p.lado == NaturezaConta.D), D0),
        total_credito=sum((p.valor for p in partidas if p.lado == NaturezaConta.C), D0),
        grupos_sem_regra=sem_regra, avisos=avisos,
    )


def contabilizar(db: Session, ctx: Contexto, doc_id: UUID, *, recontabilizar: bool = False) -> DocumentoFiscal:
    doc = svc_docs.obter(db, ctx.empresa_id, doc_id)
    if doc.status in (StatusDocumento.CANCELADO, StatusDocumento.DENEGADO):
        raise RegraContabil(f"documento {doc.status.value.lower()} não se contabiliza")
    if doc.lancamento_id:
        lanc_atual = db.get(Lancamento, doc.lancamento_id)
        if lanc_atual and lanc_atual.status == StatusLancamento.EFETIVADO:
            if not recontabilizar:
                raise RegraContabil("documento já contabilizado; use recontabilizar para estornar e refazer")
            from app.schemas.lancamento import EstornoIn
            lancamentos.estornar(db, ctx, lanc_atual.id, EstornoIn(
                data=_data_contabil(doc), historico=f"Estorno para recontabilização: {lanc_atual.historico}"))
    partidas, sem_regra, avisos = calcular(db, ctx.empresa_id, doc)
    if sem_regra:
        raise RegraContabil("sem regra de contabilização para: " + "; ".join(sem_regra), "sem_regra")
    if not partidas:
        doc.contabilizado_em = datetime.now(UTC)
        db.flush()
        return doc
    regra_nome = partidas[0].regra
    regra = db.scalar(select(RegraContabilizacao).where(
        RegraContabilizacao.empresa_id == ctx.empresa_id, RegraContabilizacao.nome == regra_nome))
    sufixo = "" if not recontabilizar else f":{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
    lanc = Lancamento(
        empresa_id=ctx.empresa_id, data=_data_contabil(doc),
        historico=_historico(doc, regra_nome, regra.historico_modelo if regra else None),
        origem=OrigemLancamento.INTEGRACAO, chave_externa=f"docfis:{doc.id}{sufixo}", criado_por=ctx.usuario.id,
        partidas=[Partida(
            empresa_id=ctx.empresa_id, conta_id=p.conta.id, ordem=i,
            debito=p.valor if p.lado == NaturezaConta.D else D0, credito=p.valor if p.lado == NaturezaConta.C else D0,
            historico_complementar=f"{p.componente.value}" + (f" CFOP {p.cfop}" if p.cfop else ""),
        ) for i, p in enumerate(partidas)],
    )
    db.add(lanc)
    db.flush()
    lancamentos._efetivar(db, ctx, lanc)
    doc.lancamento_id = lanc.id
    doc.contabilizado_em = datetime.now(UTC)
    db.flush()
    auditoria.registrar(db, acao="contabilizar", entidade="documento_fiscal", entidade_id=doc.id,
                        empresa_id=ctx.empresa_id, usuario_id=ctx.usuario.id,
                        dados={"lancamento_id": str(lanc.id), "numero": lanc.numero, "avisos": avisos,
                               "partidas": len(partidas)}, ip=ctx.ip)
    return doc


# ---------------------------------------------------------------- CRUD de regras
def obter_regra(db: Session, empresa_id: UUID, rid: UUID) -> RegraContabilizacao:
    r = db.scalar(select(RegraContabilizacao).where(RegraContabilizacao.id == rid, RegraContabilizacao.empresa_id == empresa_id))
    if r is None:
        raise NotFound("regra não encontrada")
    return r


def listar_regras(db: Session, empresa_id: UUID) -> list[RegraContabilizacao]:
    return list(db.scalars(select(RegraContabilizacao).where(RegraContabilizacao.empresa_id == empresa_id)
                           .order_by(RegraContabilizacao.prioridade.desc(), RegraContabilizacao.nome)))


def _linhas(db: Session, empresa_id: UUID, linhas: list[RegraLinhaIn]) -> list[RegraContabilizacaoLinha]:
    out = []
    for i, ln in enumerate(linhas):
        conta = contas.por_codigo(db, empresa_id, ln.conta_codigo)
        if conta.tipo.value != "ANALITICA":
            raise RegraContabil(f"conta {conta.codigo} é sintética")
        out.append(RegraContabilizacaoLinha(empresa_id=empresa_id, ordem=i, componente=ln.componente, lado=ln.lado,
                                            conta_id=conta.id))
    return out


def criar_regra(db: Session, ctx: Contexto, dados: RegraCreate) -> RegraContabilizacao:
    r = RegraContabilizacao(empresa_id=ctx.empresa_id, **dados.model_dump(exclude={"linhas"}),
                            linhas=_linhas(db, ctx.empresa_id, dados.linhas))
    db.add(r)
    db.flush()
    auditoria.registrar(db, acao="criar", entidade="regra_contabilizacao", entidade_id=r.id, empresa_id=ctx.empresa_id,
                        usuario_id=ctx.usuario.id, dados=dados.model_dump(mode="json"), ip=ctx.ip)
    return r


def atualizar_regra(db: Session, ctx: Contexto, rid: UUID, dados: RegraUpdate) -> RegraContabilizacao:
    r = obter_regra(db, ctx.empresa_id, rid)
    mud = dados.model_dump(exclude_unset=True)
    linhas = mud.pop("linhas", None)
    for k, v in mud.items():
        setattr(r, k, v)
    if linhas is not None:
        r.linhas = _linhas(db, ctx.empresa_id, [RegraLinhaIn(**ln) for ln in linhas])
    db.flush()
    auditoria.registrar(db, acao="atualizar", entidade="regra_contabilizacao", entidade_id=r.id, empresa_id=ctx.empresa_id,
                        usuario_id=ctx.usuario.id, dados=dados.model_dump(mode="json", exclude_unset=True), ip=ctx.ip)
    return r


def excluir_regra(db: Session, ctx: Contexto, rid: UUID) -> None:
    r = obter_regra(db, ctx.empresa_id, rid)
    db.delete(r)
    db.flush()
    auditoria.registrar(db, acao="excluir", entidade="regra_contabilizacao", entidade_id=rid, empresa_id=ctx.empresa_id,
                        usuario_id=ctx.usuario.id, ip=ctx.ip)


# ---------------------------------------------------------------- regras padrão por regime
CLIENTES, FORNEC, CONTAS_PAGAR = "1.1.02.001", "2.1.01.001", "2.1.05.002"
EST_MERC, EST_MP, IMOB = "1.1.04.001", "1.1.04.002", "1.2.03.002"
ICMS_REC, PIS_REC, COFINS_REC, IRRF_REC, IPI_REC, CSLL_REC, INSS_REC = (
    "1.1.03.001", "1.1.03.002", "1.1.03.003", "1.1.03.004", "1.1.03.005", "1.1.03.006", "1.1.03.007")
ICMS_PAG, ISS_PAG, PIS_PAG, COFINS_PAG, IRRF_PAG, ISS_RET_PAG, RET_FED_PAG, IPI_PAG, ST_PAG, INSS_RET_PAG = (
    "2.1.03.001", "2.1.03.002", "2.1.03.003", "2.1.03.004", "2.1.03.008", "2.1.03.009", "2.1.03.010",
    "2.1.03.011", "2.1.03.012", "2.1.02.006")
REC_MERC, REC_SERV = "4.1.01.001", "4.1.01.002"
DED_ICMS, DED_ISS, DED_PIS, DED_COFINS, DED_DEV = "4.2.01.001", "4.2.01.002", "4.2.01.003", "4.2.01.004", "4.2.01.006"
DESP_ENERGIA, DESP_TERC, DESP_USO, DESP_FRETE = "5.3.01.002", "5.3.01.007", "5.3.01.013", "5.3.01.014"


def _ln(comp: C, lado: str, conta: str) -> RegraLinhaIn:
    return RegraLinhaIn(componente=comp, lado=NaturezaConta(lado), conta_codigo=conta)


def regras_padrao(regime: RegimeTributario) -> list[RegraCreate]:
    credita_icms = regime in (RegimeTributario.PRESUMIDO, RegimeTributario.REAL)
    credita_pc = regime == RegimeTributario.REAL
    destaca_venda = regime in (RegimeTributario.PRESUMIDO, RegimeTributario.REAL)
    E, S = TipoOperacao.ENTRADA, TipoOperacao.SAIDA

    def compra(nome, cfops, conta_destino, *, icms=False, ipi=False, pc=False):
        linhas = [_ln(C.TOTAL, "C", FORNEC)]
        if icms and credita_icms:
            linhas.append(_ln(C.ICMS, "D", ICMS_REC))
        if ipi and credita_icms:
            linhas.append(_ln(C.IPI, "D", IPI_REC))
        if pc and credita_pc:
            linhas += [_ln(C.PIS, "D", PIS_REC), _ln(C.COFINS, "D", COFINS_REC)]
        linhas.append(_ln(C.RESIDUAL, "D", conta_destino))
        return RegraCreate(nome=nome, tipo_operacao=E, cfops=cfops, linhas=linhas)

    venda_linhas = [_ln(C.TOTAL, "D", CLIENTES), _ln(C.IPI, "C", IPI_PAG), _ln(C.ICMS_ST, "C", ST_PAG)]
    if destaca_venda:
        venda_linhas += [_ln(C.ICMS, "D", DED_ICMS), _ln(C.ICMS, "C", ICMS_PAG),
                         _ln(C.PIS, "D", DED_PIS), _ln(C.PIS, "C", PIS_PAG),
                         _ln(C.COFINS, "D", DED_COFINS), _ln(C.COFINS, "C", COFINS_PAG)]
    venda_linhas.append(_ln(C.RESIDUAL, "C", REC_MERC))

    dev_compra = [_ln(C.TOTAL, "D", FORNEC)]
    if credita_icms:
        dev_compra.append(_ln(C.ICMS, "C", ICMS_REC))
    if credita_pc:
        dev_compra += [_ln(C.PIS, "C", PIS_REC), _ln(C.COFINS, "C", COFINS_REC)]
    dev_compra.append(_ln(C.RESIDUAL, "C", EST_MERC))

    dev_venda = [_ln(C.TOTAL, "C", CLIENTES)]
    if destaca_venda:
        dev_venda += [_ln(C.ICMS, "D", ICMS_PAG), _ln(C.ICMS, "C", DED_ICMS),
                      _ln(C.PIS, "D", PIS_PAG), _ln(C.PIS, "C", DED_PIS),
                      _ln(C.COFINS, "D", COFINS_PAG), _ln(C.COFINS, "C", DED_COFINS)]
    dev_venda.append(_ln(C.RESIDUAL, "D", DED_DEV))

    serv_prestado = [_ln(C.SERVICOS, "C", REC_SERV), _ln(C.ISS_RETIDO, "D", DED_ISS),
                     _ln(C.IRRF_RETIDO, "D", IRRF_REC), _ln(C.PIS_RETIDO, "D", PIS_REC),
                     _ln(C.COFINS_RETIDO, "D", COFINS_REC), _ln(C.CSLL_RETIDA, "D", CSLL_REC),
                     _ln(C.INSS_RETIDO, "D", INSS_REC)]
    if destaca_venda:
        serv_prestado += [_ln(C.ISS, "D", DED_ISS), _ln(C.ISS, "C", ISS_PAG),
                          _ln(C.PIS, "D", DED_PIS), _ln(C.PIS, "C", PIS_PAG),
                          _ln(C.COFINS, "D", DED_COFINS), _ln(C.COFINS, "C", COFINS_PAG)]
    serv_prestado.append(_ln(C.RESIDUAL, "D", CLIENTES))

    serv_tomado = [_ln(C.SERVICOS, "D", DESP_TERC), _ln(C.ISS_RETIDO, "C", ISS_RET_PAG),
                   _ln(C.IRRF_RETIDO, "C", IRRF_PAG), _ln(C.PIS_RETIDO, "C", RET_FED_PAG),
                   _ln(C.COFINS_RETIDO, "C", RET_FED_PAG), _ln(C.CSLL_RETIDA, "C", RET_FED_PAG),
                   _ln(C.INSS_RETIDO, "C", INSS_RET_PAG)]
    if credita_pc:
        serv_tomado += [_ln(C.PIS, "D", PIS_REC), _ln(C.COFINS, "D", COFINS_REC)]
    serv_tomado.append(_ln(C.RESIDUAL, "C", CONTAS_PAGAR))

    despesa_pc = ([_ln(C.PIS, "D", PIS_REC), _ln(C.COFINS, "D", COFINS_REC)] if credita_pc else [])
    sem_efeito = [f"{b}9{n:02d}" for b in "1256" for n in range(1, 27)]

    regras = [
        compra("Compra para revenda", ["1102", "2102", "3102"], EST_MERC, icms=True, pc=True),
        compra("Compra para revenda com ST", ["1403", "2403"], EST_MERC, pc=True),
        compra("Compra para industrialização", ["1101", "2101", "3101"], EST_MP, icms=True, ipi=True, pc=True),
        compra("Compra para industrialização com ST", ["1401", "2401"], EST_MP, ipi=True, pc=True),
        compra("Material de uso e consumo", ["1556", "2556", "3556"], DESP_USO),
        compra("Ativo imobilizado", ["1551", "2551", "3551"], IMOB),
        RegraCreate(nome="Energia elétrica", tipo_operacao=E, cfops=["1252", "2252", "1253", "2253"],
                    linhas=[_ln(C.TOTAL, "C", CONTAS_PAGAR), *despesa_pc, _ln(C.RESIDUAL, "D", DESP_ENERGIA)]),
        RegraCreate(nome="Frete sobre compras", tipo_operacao=E, cfops=["1352", "2352", "1353", "2353"],
                    linhas=[_ln(C.TOTAL, "C", CONTAS_PAGAR), *despesa_pc, _ln(C.RESIDUAL, "D", DESP_FRETE)]),
        RegraCreate(nome="Devolução de venda", tipo_operacao=E, cfops=["1201", "2201", "1202", "2202", "1410", "2410", "1411", "2411"],
                    linhas=dev_venda),
        RegraCreate(nome="Serviço tomado (NF-e)", tipo_operacao=E, cfops=["1933", "2933"], linhas=serv_tomado),
        RegraCreate(nome="Serviço tomado (NFS-e)", modelo=ModeloDocumento.NFSE, tipo_operacao=E, linhas=serv_tomado),
        RegraCreate(nome="Venda de mercadorias e produtos", tipo_operacao=S,
                    cfops=["5101", "6101", "7101", "5102", "6102", "7102", "5103", "6103", "5104", "6104",
                           "5401", "6401", "5403", "6403", "5405", "6405", "5109", "6109", "5110", "6110"],
                    linhas=venda_linhas),
        RegraCreate(nome="Devolução de compra", tipo_operacao=S, cfops=["5201", "6201", "5202", "6202", "5410", "6410", "5411", "6411"],
                    linhas=dev_compra),
        RegraCreate(nome="Serviço prestado (NF-e)", tipo_operacao=S, cfops=["5933", "6933"], linhas=serv_prestado),
        RegraCreate(nome="Serviço prestado (NFS-e)", modelo=ModeloDocumento.NFSE, tipo_operacao=S, linhas=serv_prestado),
        RegraCreate(nome="Remessas, retornos e operações sem efeito contábil", prioridade=50, cfops=sem_efeito,
                    contabilizar=False, linhas=[]),
    ]
    return regras


def criar_regras_padrao(db: Session, ctx: Contexto, regime: RegimeTributario, *, substituir: bool) -> int:
    existentes = listar_regras(db, ctx.empresa_id)
    if existentes and not substituir:
        raise RegraContabil("empresa já possui regras; use substituir=true para recriar", "regras_existentes")
    for r in existentes:
        db.delete(r)
    db.flush()
    n = 0
    for dados in regras_padrao(regime):
        criar_regra(db, ctx, dados)
        n += 1
    return n
