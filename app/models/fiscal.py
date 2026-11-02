import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models._base import IdMixin, TimestampMixin, pg_enum
from app.models.enums import (
    ComponenteFiscal,
    IndicadorIE,
    ModeloDocumento,
    NaturezaConta,
    OrigemDocumento,
    StatusDocumento,
    TipoItem,
    TipoOperacao,
    TipoPessoa,
)

D0 = Decimal(0)


def _money(**kw):
    return mapped_column(Numeric(18, 2), default=D0, nullable=False, **kw)


class Participante(IdMixin, TimestampMixin, Base):
    __tablename__ = "participante"

    empresa_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("empresa.id"), nullable=False)
    tipo_pessoa: Mapped[TipoPessoa] = mapped_column(pg_enum(TipoPessoa, "tipo_pessoa"), nullable=False)
    cnpj_cpf: Mapped[str] = mapped_column(String, nullable=False)
    razao_social: Mapped[str] = mapped_column(String, nullable=False)
    nome_fantasia: Mapped[str | None] = mapped_column(String)
    ie: Mapped[str | None] = mapped_column(String)
    im: Mapped[str | None] = mapped_column(String)
    indicador_ie: Mapped[IndicadorIE] = mapped_column(
        pg_enum(IndicadorIE, "indicador_ie"), default=IndicadorIE.NAO_CONTRIBUINTE
    )
    logradouro: Mapped[str | None] = mapped_column(String)
    numero: Mapped[str | None] = mapped_column(String)
    complemento: Mapped[str | None] = mapped_column(String)
    bairro: Mapped[str | None] = mapped_column(String)
    codigo_municipio: Mapped[str | None] = mapped_column(String(7))
    municipio: Mapped[str | None] = mapped_column(String)
    uf: Mapped[str | None] = mapped_column(String(2))
    cep: Mapped[str | None] = mapped_column(String(8))
    pais: Mapped[str] = mapped_column(String, default="Brasil")
    email: Mapped[str | None] = mapped_column(String)
    telefone: Mapped[str | None] = mapped_column(String)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)


class Produto(IdMixin, TimestampMixin, Base):
    __tablename__ = "produto"

    empresa_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("empresa.id"), nullable=False)
    codigo: Mapped[str] = mapped_column(String, nullable=False)
    descricao: Mapped[str] = mapped_column(String, nullable=False)
    tipo_item: Mapped[TipoItem] = mapped_column(pg_enum(TipoItem, "tipo_item"), default=TipoItem.MERCADORIA_REVENDA)
    ncm: Mapped[str | None] = mapped_column(String(8))
    cest: Mapped[str | None] = mapped_column(String(7))
    unidade: Mapped[str] = mapped_column(String, default="UN")
    ean: Mapped[str | None] = mapped_column(String)
    origem: Mapped[int | None] = mapped_column(SmallInteger)
    codigo_servico: Mapped[str | None] = mapped_column(String)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)


class ProdutoReferencia(IdMixin, Base):
    __tablename__ = "produto_referencia"

    empresa_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("empresa.id"), nullable=False)
    participante_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("participante.id"), nullable=False)
    codigo_externo: Mapped[str] = mapped_column(String, nullable=False)
    produto_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("produto.id"), nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")


class DocumentoFiscal(IdMixin, TimestampMixin, Base):
    __tablename__ = "documento_fiscal"

    empresa_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("empresa.id"), nullable=False)
    modelo: Mapped[ModeloDocumento] = mapped_column(pg_enum(ModeloDocumento, "modelo_documento"), nullable=False)
    tipo_operacao: Mapped[TipoOperacao] = mapped_column(pg_enum(TipoOperacao, "tipo_operacao"), nullable=False)
    status: Mapped[StatusDocumento] = mapped_column(
        pg_enum(StatusDocumento, "status_documento"), default=StatusDocumento.DIGITADO
    )
    origem: Mapped[OrigemDocumento] = mapped_column(pg_enum(OrigemDocumento, "origem_documento"), nullable=False)
    chave_acesso: Mapped[str | None] = mapped_column(String(44))
    numero: Mapped[int] = mapped_column(BigInteger, nullable=False)
    serie: Mapped[str] = mapped_column(String, default="1")
    data_emissao: Mapped[date] = mapped_column(Date, nullable=False)
    data_entrada_saida: Mapped[date | None] = mapped_column(Date)
    participante_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("participante.id"))
    natureza_operacao: Mapped[str | None] = mapped_column(String)
    finalidade: Mapped[int | None] = mapped_column(SmallInteger)
    protocolo: Mapped[str | None] = mapped_column(String)
    valor_produtos: Mapped[Decimal] = _money()
    valor_servicos: Mapped[Decimal] = _money()
    valor_frete: Mapped[Decimal] = _money()
    valor_seguro: Mapped[Decimal] = _money()
    valor_desconto: Mapped[Decimal] = _money()
    valor_outras: Mapped[Decimal] = _money()
    valor_ipi: Mapped[Decimal] = _money()
    valor_icms: Mapped[Decimal] = _money()
    valor_icms_st: Mapped[Decimal] = _money()
    valor_pis: Mapped[Decimal] = _money()
    valor_cofins: Mapped[Decimal] = _money()
    valor_iss: Mapped[Decimal] = _money()
    valor_iss_retido: Mapped[Decimal] = _money()
    valor_irrf_retido: Mapped[Decimal] = _money()
    valor_pis_retido: Mapped[Decimal] = _money()
    valor_cofins_retido: Mapped[Decimal] = _money()
    valor_csll_retida: Mapped[Decimal] = _money()
    valor_inss_retido: Mapped[Decimal] = _money()
    valor_total: Mapped[Decimal] = _money()
    informacoes_complementares: Mapped[str | None] = mapped_column(String)
    xml: Mapped[str | None] = mapped_column(String)
    xml_hash: Mapped[str | None] = mapped_column(String(64))
    lancamento_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("lancamento.id"))
    contabilizado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    motivo_cancelamento: Mapped[str | None] = mapped_column(String)
    criado_por: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("usuario.id"), nullable=False)

    itens: Mapped[list["DocumentoFiscalItem"]] = relationship(
        back_populates="documento", cascade="all, delete-orphan", order_by="DocumentoFiscalItem.numero_item",
        lazy="selectin",
    )
    participante: Mapped[Participante | None] = relationship(lazy="joined")


class DocumentoFiscalItem(IdMixin, Base):
    __tablename__ = "documento_fiscal_item"

    empresa_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("empresa.id"), nullable=False)
    documento_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documento_fiscal.id", ondelete="CASCADE"), nullable=False
    )
    numero_item: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    produto_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("produto.id"))
    codigo_externo: Mapped[str | None] = mapped_column(String)
    descricao: Mapped[str] = mapped_column(String, nullable=False)
    ncm: Mapped[str | None] = mapped_column(String(8))
    cest: Mapped[str | None] = mapped_column(String(7))
    cfop: Mapped[str | None] = mapped_column(String(4))
    cfop_documento: Mapped[str | None] = mapped_column(String(4))
    codigo_servico: Mapped[str | None] = mapped_column(String)
    unidade: Mapped[str | None] = mapped_column(String)
    quantidade: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=Decimal(1))
    valor_unitario: Mapped[Decimal] = mapped_column(Numeric(21, 10), default=D0)
    valor_bruto: Mapped[Decimal] = _money()
    valor_frete: Mapped[Decimal] = _money()
    valor_seguro: Mapped[Decimal] = _money()
    valor_desconto: Mapped[Decimal] = _money()
    valor_outras: Mapped[Decimal] = _money()
    compoe_total: Mapped[bool] = mapped_column(Boolean, default=True)
    icms_origem: Mapped[int | None] = mapped_column(SmallInteger)
    icms_cst: Mapped[str | None] = mapped_column(String)
    icms_base: Mapped[Decimal] = _money()
    icms_aliquota: Mapped[Decimal] = mapped_column(Numeric(7, 4), default=D0)
    icms_valor: Mapped[Decimal] = _money()
    icms_st_base: Mapped[Decimal] = _money()
    icms_st_valor: Mapped[Decimal] = _money()
    ipi_cst: Mapped[str | None] = mapped_column(String)
    ipi_base: Mapped[Decimal] = _money()
    ipi_aliquota: Mapped[Decimal] = mapped_column(Numeric(7, 4), default=D0)
    ipi_valor: Mapped[Decimal] = _money()
    pis_cst: Mapped[str | None] = mapped_column(String)
    pis_base: Mapped[Decimal] = _money()
    pis_aliquota: Mapped[Decimal] = mapped_column(Numeric(7, 4), default=D0)
    pis_valor: Mapped[Decimal] = _money()
    cofins_cst: Mapped[str | None] = mapped_column(String)
    cofins_base: Mapped[Decimal] = _money()
    cofins_aliquota: Mapped[Decimal] = mapped_column(Numeric(7, 4), default=D0)
    cofins_valor: Mapped[Decimal] = _money()
    iss_base: Mapped[Decimal] = _money()
    iss_aliquota: Mapped[Decimal] = mapped_column(Numeric(7, 4), default=D0)
    iss_valor: Mapped[Decimal] = _money()

    documento: Mapped[DocumentoFiscal] = relationship(back_populates="itens")


class RegraContabilizacao(IdMixin, TimestampMixin, Base):
    __tablename__ = "regra_contabilizacao"

    empresa_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("empresa.id"), nullable=False)
    nome: Mapped[str] = mapped_column(String, nullable=False)
    prioridade: Mapped[int] = mapped_column(Integer, default=100)
    ativa: Mapped[bool] = mapped_column(Boolean, default=True)
    modelo: Mapped[ModeloDocumento | None] = mapped_column(pg_enum(ModeloDocumento, "modelo_documento"))
    tipo_operacao: Mapped[TipoOperacao | None] = mapped_column(pg_enum(TipoOperacao, "tipo_operacao"))
    cfops: Mapped[list[str] | None] = mapped_column(ARRAY(String))
    tipo_item: Mapped[TipoItem | None] = mapped_column(pg_enum(TipoItem, "tipo_item"))
    contabilizar: Mapped[bool] = mapped_column(Boolean, default=True)
    historico_modelo: Mapped[str | None] = mapped_column(String)

    linhas: Mapped[list["RegraContabilizacaoLinha"]] = relationship(
        back_populates="regra", cascade="all, delete-orphan", order_by="RegraContabilizacaoLinha.ordem",
        lazy="selectin",
    )


class RegraContabilizacaoLinha(IdMixin, Base):
    __tablename__ = "regra_contabilizacao_linha"

    empresa_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("empresa.id"), nullable=False)
    regra_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("regra_contabilizacao.id", ondelete="CASCADE"), nullable=False
    )
    ordem: Mapped[int] = mapped_column(SmallInteger, default=0)
    componente: Mapped[ComponenteFiscal] = mapped_column(pg_enum(ComponenteFiscal, "componente_fiscal"), nullable=False)
    lado: Mapped[NaturezaConta] = mapped_column(pg_enum(NaturezaConta, "natureza_conta"), nullable=False)
    conta_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("conta.id"), nullable=False)

    regra: Mapped[RegraContabilizacao] = relationship(back_populates="linhas")
