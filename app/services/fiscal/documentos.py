from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import Conflict, NotFound, RegraContabil
from app.models import (
    DocumentoFiscal,
    DocumentoFiscalItem,
    Empresa,
    Lancamento,
    ModeloDocumento,
    OrigemDocumento,
    Produto,
    StatusDocumento,
    StatusLancamento,
    TipoItem,
    TipoOperacao,
)
from app.schemas.fiscal import (
    CancelarIn,
    DocumentoCreate,
    ItemPatchIn,
    ResumoCfopLinha,
    ResumoFiscalOut,
)
from app.schemas.lancamento import EstornoIn
from app.services import auditoria, lancamentos
from app.services.contexto import Contexto
from app.services.fiscal import cadastros
from app.services.fiscal.nfe_xml import NFeLida, ler_nfe

D0 = Decimal(0)


def obter(db: Session, empresa_id: UUID, doc_id: UUID) -> DocumentoFiscal:
    d = db.scalar(select(DocumentoFiscal).where(DocumentoFiscal.id == doc_id, DocumentoFiscal.empresa_id == empresa_id))
    if d is None:
        raise NotFound("documento fiscal não encontrado")
    return d


def itens_sem_produto(doc: DocumentoFiscal) -> int:
    return sum(1 for i in doc.itens if i.produto_id is None)


def listar(
    db: Session, empresa_id: UUID, *, modelo: ModeloDocumento | None, tipo_operacao: TipoOperacao | None,
    status: StatusDocumento | None, data_inicio: date | None, data_fim: date | None,
    participante_id: UUID | None, contabilizado: bool | None, chave_acesso: str | None,
    limit: int, offset: int,
) -> tuple[list[DocumentoFiscal], int]:
    q = select(DocumentoFiscal).where(DocumentoFiscal.empresa_id == empresa_id)
    if modelo:
        q = q.where(DocumentoFiscal.modelo == modelo)
    if tipo_operacao:
        q = q.where(DocumentoFiscal.tipo_operacao == tipo_operacao)
    if status:
        q = q.where(DocumentoFiscal.status == status)
    if data_inicio:
        q = q.where(DocumentoFiscal.data_emissao >= data_inicio)
    if data_fim:
        q = q.where(DocumentoFiscal.data_emissao <= data_fim)
    if participante_id:
        q = q.where(DocumentoFiscal.participante_id == participante_id)
    if contabilizado is True:
        q = q.where(DocumentoFiscal.lancamento_id.is_not(None))
    elif contabilizado is False:
        q = q.where(DocumentoFiscal.lancamento_id.is_(None))
    if chave_acesso:
        q = q.where(DocumentoFiscal.chave_acesso == chave_acesso)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.scalars(q.order_by(DocumentoFiscal.data_emissao.desc(), DocumentoFiscal.numero.desc()).limit(limit).offset(offset))
    return list(rows), total


# ---------------------------------------------------------------- criação manual
def _totalizar(doc: DocumentoFiscal) -> None:
    itens = [i for i in doc.itens if i.compoe_total is not False]
    doc.valor_produtos = sum((i.valor_bruto for i in itens if not i.codigo_servico), D0)
    doc.valor_servicos = sum((i.valor_bruto for i in itens if i.codigo_servico), D0)
    doc.valor_frete = sum((i.valor_frete for i in itens), D0)
    doc.valor_seguro = sum((i.valor_seguro for i in itens), D0)
    doc.valor_desconto = sum((i.valor_desconto for i in itens), D0)
    doc.valor_outras = sum((i.valor_outras for i in itens), D0)
    doc.valor_ipi = sum((i.ipi_valor for i in itens), D0)
    doc.valor_icms = sum((i.icms_valor for i in itens), D0)
    doc.valor_icms_st = sum((i.icms_st_valor for i in itens), D0)
    doc.valor_pis = sum((i.pis_valor for i in itens), D0)
    doc.valor_cofins = sum((i.cofins_valor for i in itens), D0)
    doc.valor_iss = sum((i.iss_valor for i in itens), D0)
    doc.valor_total = (doc.valor_produtos + doc.valor_servicos + doc.valor_frete + doc.valor_seguro
                       + doc.valor_outras + doc.valor_ipi + doc.valor_icms_st - doc.valor_desconto)


def criar_manual(db: Session, ctx: Contexto, dados: DocumentoCreate) -> DocumentoFiscal:
    if dados.participante_id:
        cadastros.obter_participante(db, ctx.empresa_id, dados.participante_id)
    doc = DocumentoFiscal(
        empresa_id=ctx.empresa_id, origem=OrigemDocumento.MANUAL, criado_por=ctx.usuario.id,
        **dados.model_dump(exclude={"itens"}),
    )
    for n, it in enumerate(dados.itens, start=1):
        produto_id = None
        if it.produto_codigo:
            p = cadastros.produto_por_codigo(db, ctx.empresa_id, it.produto_codigo)
            if p is None:
                raise NotFound(f"produto {it.produto_codigo} não encontrado")
            produto_id = p.id
        doc.itens.append(DocumentoFiscalItem(
            empresa_id=ctx.empresa_id, numero_item=n, produto_id=produto_id, compoe_total=True,
            **it.model_dump(exclude={"produto_codigo"}),
        ))
    if doc.modelo == ModeloDocumento.NFSE:
        for i in doc.itens:
            if not i.codigo_servico:
                i.codigo_servico = i.codigo_servico or "00.00"
    _totalizar(doc)
    db.add(doc)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise Conflict("documento já existe (chave de acesso ou número/série/participante repetidos)") from exc
    auditoria.registrar(db, acao="criar", entidade="documento_fiscal", entidade_id=doc.id, empresa_id=ctx.empresa_id,
                        usuario_id=ctx.usuario.id,
                        dados={"modelo": doc.modelo.value, "numero": doc.numero, "valor_total": doc.valor_total}, ip=ctx.ip)
    return doc


# ---------------------------------------------------------------- importação de XML
def _tipo_operacao(nfe: NFeLida, cnpj_empresa: str) -> TipoOperacao:
    emit = nfe.emitente["cnpj_cpf"]
    dest = (nfe.destinatario or {}).get("cnpj_cpf")
    if emit == cnpj_empresa:
        return TipoOperacao.SAIDA if nfe.tipo_nf == 1 else TipoOperacao.ENTRADA
    if dest == cnpj_empresa:
        return TipoOperacao.ENTRADA if nfe.tipo_nf == 1 else TipoOperacao.SAIDA
    raise RegraContabil(
        f"NF-e não pertence à empresa: emitente {emit}, destinatário {dest or '-'}", "documento_de_terceiro"
    )


# CFOP do emitente (5/6/7xxx) -> CFOP de entrada do destinatário (1/2/3xxx). Exceções em que o
# código final muda: venda de substituído (x405/x404) entra como compra com ST (x403).
_EXCECOES_CFOP = {"405": "403", "404": "403"}


def cfop_entrada(cfop_emitente: str | None) -> str | None:
    """Converte o CFOP de saída do emitente para o CFOP de entrada equivalente. Aproximação:
    o contador pode corrigir item a item (PATCH do item)."""
    if not cfop_emitente or len(cfop_emitente) != 4 or cfop_emitente[0] not in "567":
        return cfop_emitente
    primeiro = {"5": "1", "6": "2", "7": "3"}[cfop_emitente[0]]
    final = _EXCECOES_CFOP.get(cfop_emitente[1:], cfop_emitente[1:])
    return primeiro + final


def _status(nfe: NFeLida) -> StatusDocumento:
    if nfe.codigo_status is None:
        return StatusDocumento.DIGITADO
    if nfe.codigo_status in ("100", "150"):
        return StatusDocumento.AUTORIZADO
    if nfe.codigo_status in ("110", "301", "302", "303"):
        return StatusDocumento.DENEGADO
    return StatusDocumento.DIGITADO


def importar_xml(db: Session, ctx: Contexto, conteudo: bytes) -> DocumentoFiscal:
    nfe = ler_nfe(conteudo)
    existente = db.scalar(select(DocumentoFiscal.id).where(
        DocumentoFiscal.empresa_id == ctx.empresa_id, DocumentoFiscal.chave_acesso == nfe.chave))
    if existente:
        raise Conflict(f"NF-e {nfe.chave} já importada (documento {existente})")
    empresa = db.get(Empresa, ctx.empresa_id)
    tipo = _tipo_operacao(nfe, empresa.cnpj)

    contraparte = nfe.destinatario if nfe.emitente["cnpj_cpf"] == empresa.cnpj else nfe.emitente
    participante = None
    if contraparte:
        dados = {k: v for k, v in contraparte.items() if k != "estrangeiro"}
        dados["tipo_pessoa"] = cadastros.tipo_pessoa_por_documento(dados["cnpj_cpf"], contraparte["estrangeiro"])
        participante = cadastros.upsert_participante_xml(db, ctx.empresa_id, dados)

    doc = DocumentoFiscal(
        empresa_id=ctx.empresa_id,
        modelo=ModeloDocumento.NFE if nfe.modelo == "55" else ModeloDocumento.NFCE,
        tipo_operacao=tipo, status=_status(nfe), origem=OrigemDocumento.XML,
        chave_acesso=nfe.chave, numero=nfe.numero, serie=nfe.serie,
        data_emissao=nfe.data_emissao, data_entrada_saida=nfe.data_saida_entrada,
        participante_id=participante.id if participante else None,
        natureza_operacao=nfe.natureza_operacao, finalidade=nfe.finalidade, protocolo=nfe.protocolo,
        informacoes_complementares=nfe.informacoes_complementares, xml=nfe.xml, xml_hash=nfe.xml_hash,
        criado_por=ctx.usuario.id, **nfe.totais, **nfe.retencoes,
    )
    for it in nfe.itens:
        produto_id = _resolver_produto(db, ctx, tipo, participante.id if participante else None, it)
        doc.itens.append(DocumentoFiscalItem(
            empresa_id=ctx.empresa_id, numero_item=it.numero, produto_id=produto_id, codigo_externo=it.codigo,
            descricao=it.descricao, ncm=it.ncm, cest=it.cest, cfop_documento=it.cfop,
            cfop=cfop_entrada(it.cfop) if tipo == TipoOperacao.ENTRADA else it.cfop, codigo_servico=it.codigo_servico,
            unidade=it.unidade, quantidade=it.quantidade, valor_unitario=it.valor_unitario,
            valor_bruto=it.valor_bruto, valor_frete=it.valor_frete, valor_seguro=it.valor_seguro,
            valor_desconto=it.valor_desconto, valor_outras=it.valor_outras, compoe_total=it.compoe_total,
            icms_origem=it.icms_origem, icms_cst=it.icms_cst, icms_base=it.icms_base, icms_aliquota=it.icms_aliquota,
            icms_valor=it.icms_valor, icms_st_base=it.icms_st_base, icms_st_valor=it.icms_st_valor,
            ipi_cst=it.ipi_cst, ipi_base=it.ipi_base, ipi_aliquota=it.ipi_aliquota, ipi_valor=it.ipi_valor,
            pis_cst=it.pis_cst, pis_base=it.pis_base, pis_aliquota=it.pis_aliquota, pis_valor=it.pis_valor,
            cofins_cst=it.cofins_cst, cofins_base=it.cofins_base, cofins_aliquota=it.cofins_aliquota,
            cofins_valor=it.cofins_valor, iss_base=it.iss_base, iss_aliquota=it.iss_aliquota, iss_valor=it.iss_valor,
        ))
    db.add(doc)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise Conflict("NF-e já importada") from exc
    auditoria.registrar(db, acao="importar_xml", entidade="documento_fiscal", entidade_id=doc.id,
                        empresa_id=ctx.empresa_id, usuario_id=ctx.usuario.id,
                        dados={"chave": nfe.chave, "tipo_operacao": tipo.value, "valor_total": doc.valor_total,
                               "xml_hash": nfe.xml_hash}, ip=ctx.ip)
    return doc


def _resolver_produto(db: Session, ctx: Contexto, tipo: TipoOperacao, participante_id: UUID | None, it) -> UUID | None:
    if not it.codigo:
        return None
    if tipo == TipoOperacao.SAIDA:
        # Emissão própria: o código do item é o nosso. Cadastra se não existir.
        p = cadastros.produto_por_codigo(db, ctx.empresa_id, it.codigo)
        if p is None:
            p = Produto(
                empresa_id=ctx.empresa_id, codigo=it.codigo, descricao=it.descricao[:300],
                tipo_item=TipoItem.SERVICO if it.codigo_servico else TipoItem.MERCADORIA_REVENDA,
                ncm=it.ncm if it.ncm and len(it.ncm) == 8 else None,
                cest=it.cest if it.cest and len(it.cest) == 7 else None,
                unidade=(it.unidade or "UN")[:6], ean=it.ean, origem=it.icms_origem, codigo_servico=it.codigo_servico,
            )
            db.add(p)
            db.flush()
        return p.id
    if participante_id is None:
        return None
    ref = cadastros.referencia(db, ctx.empresa_id, participante_id, it.codigo)
    return ref.produto_id if ref else None


def alterar_item(db: Session, ctx: Contexto, doc_id: UUID, numero_item: int, dados: ItemPatchIn) -> DocumentoFiscal:
    doc = obter(db, ctx.empresa_id, doc_id)
    if doc.lancamento_id:
        lanc = db.get(Lancamento, doc.lancamento_id)
        if lanc and lanc.status == StatusLancamento.EFETIVADO:
            raise RegraContabil("documento contabilizado; estorne (recontabilizar) antes de alterar itens")
    item = next((i for i in doc.itens if i.numero_item == numero_item), None)
    if item is None:
        raise NotFound("item não encontrado")
    mud: dict = {}
    if dados.produto_codigo:
        produto = cadastros.produto_por_codigo(db, ctx.empresa_id, dados.produto_codigo)
        if produto is None:
            raise NotFound(f"produto {dados.produto_codigo} não encontrado")
        item.produto_id = produto.id
        mud["produto"] = produto.codigo
        if dados.criar_referencia and doc.participante_id and item.codigo_externo:
            from app.schemas.fiscal import ProdutoReferenciaIn
            cadastros.criar_referencia(db, ctx, produto.id, ProdutoReferenciaIn(
                participante_id=doc.participante_id, codigo_externo=item.codigo_externo))
    if dados.cfop:
        mud["cfop"] = {"de": item.cfop, "para": dados.cfop}
        item.cfop = dados.cfop
    db.flush()
    auditoria.registrar(db, acao="alterar_item", entidade="documento_fiscal", entidade_id=doc.id, empresa_id=ctx.empresa_id,
                        usuario_id=ctx.usuario.id, dados={"item": numero_item, **mud}, ip=ctx.ip)
    return doc


# ---------------------------------------------------------------- cancelamento
def cancelar(db: Session, ctx: Contexto, doc_id: UUID, dados: CancelarIn) -> DocumentoFiscal:
    doc = obter(db, ctx.empresa_id, doc_id)
    if doc.status == StatusDocumento.CANCELADO:
        raise RegraContabil("documento já cancelado")
    estorno_id = None
    if doc.lancamento_id:
        lanc = db.get(Lancamento, doc.lancamento_id)
        if lanc and lanc.status == StatusLancamento.EFETIVADO:
            est = lancamentos.estornar(db, ctx, lanc.id, EstornoIn(
                data=dados.data_estorno or date.today(),
                historico=f"Estorno por cancelamento do documento {doc.modelo.value} {doc.numero}/{doc.serie}: {dados.motivo}",
            ))
            estorno_id = est.id
    doc.status = StatusDocumento.CANCELADO
    doc.cancelado_em = datetime.now(UTC)
    doc.motivo_cancelamento = dados.motivo
    if dados.protocolo:
        doc.protocolo = dados.protocolo
    db.flush()
    auditoria.registrar(db, acao="cancelar", entidade="documento_fiscal", entidade_id=doc.id, empresa_id=ctx.empresa_id,
                        usuario_id=ctx.usuario.id, dados={"motivo": dados.motivo, "estorno_id": estorno_id}, ip=ctx.ip)
    return doc


def excluir(db: Session, ctx: Contexto, doc_id: UUID) -> None:
    doc = obter(db, ctx.empresa_id, doc_id)
    if doc.lancamento_id or doc.status == StatusDocumento.CANCELADO:
        raise RegraContabil("documento contabilizado ou cancelado não pode ser excluído")
    db.delete(doc)
    db.flush()
    auditoria.registrar(db, acao="excluir", entidade="documento_fiscal", entidade_id=doc_id, empresa_id=ctx.empresa_id,
                        usuario_id=ctx.usuario.id, ip=ctx.ip)


# ---------------------------------------------------------------- resumo por CFOP
def resumo(db: Session, empresa_id: UUID, inicio: date, fim: date) -> ResumoFiscalOut:
    I, D = DocumentoFiscalItem, DocumentoFiscal
    rows = db.execute(
        select(D.tipo_operacao, I.cfop, func.count(func.distinct(D.id)),
               func.sum(I.valor_bruto), func.sum(I.icms_base), func.sum(I.icms_valor), func.sum(I.icms_st_valor),
               func.sum(I.ipi_valor), func.sum(I.pis_valor), func.sum(I.cofins_valor), func.sum(I.iss_valor))
        .join(D, D.id == I.documento_id)
        .where(D.empresa_id == empresa_id, D.status != StatusDocumento.CANCELADO, D.status != StatusDocumento.DENEGADO,
               D.data_emissao.between(inicio, fim), I.compoe_total.is_(True))
        .group_by(D.tipo_operacao, I.cfop).order_by(D.tipo_operacao, I.cfop)
    ).all()
    linhas = [ResumoCfopLinha(
        tipo_operacao=r[0], cfop=r[1], documentos=r[2], valor_bruto=r[3] or D0, icms_base=r[4] or D0,
        icms_valor=r[5] or D0, icms_st_valor=r[6] or D0, ipi_valor=r[7] or D0, pis_valor=r[8] or D0,
        cofins_valor=r[9] or D0, iss_valor=r[10] or D0) for r in rows]
    tot = db.execute(
        select(D.tipo_operacao, func.sum(D.valor_total)).where(
            D.empresa_id == empresa_id, D.status.not_in([StatusDocumento.CANCELADO, StatusDocumento.DENEGADO]),
            D.data_emissao.between(inicio, fim)).group_by(D.tipo_operacao)
    ).all()
    totais = {t: v or D0 for t, v in tot}
    return ResumoFiscalOut(inicio=inicio, fim=fim, linhas=linhas,
                           total_entradas=totais.get(TipoOperacao.ENTRADA, D0), total_saidas=totais.get(TipoOperacao.SAIDA, D0))
