from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

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
from app.schemas.tipos import Dinheiro

Money = Decimal


def _so_digitos(v: str | None) -> str | None:
    if v is None:
        return None
    return "".join(ch for ch in v if ch.isdigit())


# ---------------------------------------------------------------- participantes
class ParticipanteBase(BaseModel):
    razao_social: str = Field(min_length=1, max_length=300)
    nome_fantasia: str | None = Field(default=None, max_length=300)
    ie: str | None = Field(default=None, max_length=20)
    im: str | None = Field(default=None, max_length=20)
    indicador_ie: IndicadorIE = IndicadorIE.NAO_CONTRIBUINTE
    logradouro: str | None = None
    numero: str | None = None
    complemento: str | None = None
    bairro: str | None = None
    codigo_municipio: str | None = Field(default=None, pattern=r"^[0-9]{7}$")
    municipio: str | None = None
    uf: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    cep: str | None = None
    pais: str = "Brasil"
    email: str | None = None
    telefone: str | None = None

    @field_validator("cep")
    @classmethod
    def _cep(cls, v):
        v = _so_digitos(v)
        if v and len(v) != 8:
            raise ValueError("CEP deve ter 8 dígitos")
        return v or None


class ParticipanteCreate(ParticipanteBase):
    tipo_pessoa: TipoPessoa
    cnpj_cpf: str = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def _doc(self):
        if self.tipo_pessoa in (TipoPessoa.PJ, TipoPessoa.PF):
            d = _so_digitos(self.cnpj_cpf) or ""
            esperado = 14 if self.tipo_pessoa == TipoPessoa.PJ else 11
            if len(d) != esperado:
                raise ValueError(f"{'CNPJ' if esperado == 14 else 'CPF'} deve ter {esperado} dígitos")
            self.cnpj_cpf = d
        return self


class ParticipanteUpdate(BaseModel):
    razao_social: str | None = Field(default=None, min_length=1, max_length=300)
    nome_fantasia: str | None = None
    ie: str | None = None
    im: str | None = None
    indicador_ie: IndicadorIE | None = None
    logradouro: str | None = None
    numero: str | None = None
    complemento: str | None = None
    bairro: str | None = None
    codigo_municipio: str | None = None
    municipio: str | None = None
    uf: str | None = None
    cep: str | None = None
    email: str | None = None
    telefone: str | None = None
    ativo: bool | None = None


class ParticipanteOut(ParticipanteBase):
    id: UUID
    tipo_pessoa: TipoPessoa
    cnpj_cpf: str
    ativo: bool

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------- produtos
class ProdutoCreate(BaseModel):
    codigo: str = Field(min_length=1, max_length=60)
    descricao: str = Field(min_length=1, max_length=300)
    tipo_item: TipoItem = TipoItem.MERCADORIA_REVENDA
    ncm: str | None = Field(default=None, pattern=r"^[0-9]{8}$")
    cest: str | None = Field(default=None, pattern=r"^[0-9]{7}$")
    unidade: str = Field(default="UN", max_length=6)
    ean: str | None = Field(default=None, max_length=14)
    origem: int | None = Field(default=None, ge=0, le=8)
    codigo_servico: str | None = Field(default=None, max_length=20)


class ProdutoUpdate(BaseModel):
    descricao: str | None = Field(default=None, min_length=1, max_length=300)
    tipo_item: TipoItem | None = None
    ncm: str | None = Field(default=None, pattern=r"^[0-9]{8}$")
    cest: str | None = Field(default=None, pattern=r"^[0-9]{7}$")
    unidade: str | None = None
    ean: str | None = None
    origem: int | None = Field(default=None, ge=0, le=8)
    codigo_servico: str | None = None
    ativo: bool | None = None


class ProdutoOut(ProdutoCreate):
    id: UUID
    ativo: bool

    model_config = {"from_attributes": True}


class ProdutoReferenciaIn(BaseModel):
    participante_id: UUID
    codigo_externo: str = Field(min_length=1, max_length=60)


class ProdutoReferenciaOut(BaseModel):
    id: UUID
    participante_id: UUID
    codigo_externo: str
    produto_id: UUID

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------- documentos fiscais
class ItemIn(BaseModel):
    produto_codigo: str | None = None
    codigo_externo: str | None = None
    descricao: str = Field(min_length=1, max_length=500)
    ncm: str | None = Field(default=None, pattern=r"^[0-9]{8}$")
    cest: str | None = None
    cfop: str | None = Field(default=None, pattern=r"^[1-7][0-9]{3}$")
    codigo_servico: str | None = None
    unidade: str | None = None
    quantidade: Decimal = Field(default=Decimal(1), gt=0, max_digits=15, decimal_places=4)
    valor_unitario: Decimal = Field(default=Decimal(0), ge=0, max_digits=21, decimal_places=10)
    valor_bruto: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    valor_frete: Decimal = Field(default=Decimal(0), ge=0, decimal_places=2)
    valor_seguro: Decimal = Field(default=Decimal(0), ge=0, decimal_places=2)
    valor_desconto: Decimal = Field(default=Decimal(0), ge=0, decimal_places=2)
    valor_outras: Decimal = Field(default=Decimal(0), ge=0, decimal_places=2)
    icms_origem: int | None = Field(default=None, ge=0, le=8)
    icms_cst: str | None = None
    icms_base: Decimal = Field(default=Decimal(0), ge=0, decimal_places=2)
    icms_aliquota: Decimal = Field(default=Decimal(0), ge=0, decimal_places=4)
    icms_valor: Decimal = Field(default=Decimal(0), ge=0, decimal_places=2)
    icms_st_base: Decimal = Field(default=Decimal(0), ge=0, decimal_places=2)
    icms_st_valor: Decimal = Field(default=Decimal(0), ge=0, decimal_places=2)
    ipi_cst: str | None = None
    ipi_base: Decimal = Field(default=Decimal(0), ge=0, decimal_places=2)
    ipi_aliquota: Decimal = Field(default=Decimal(0), ge=0, decimal_places=4)
    ipi_valor: Decimal = Field(default=Decimal(0), ge=0, decimal_places=2)
    pis_cst: str | None = None
    pis_base: Decimal = Field(default=Decimal(0), ge=0, decimal_places=2)
    pis_aliquota: Decimal = Field(default=Decimal(0), ge=0, decimal_places=4)
    pis_valor: Decimal = Field(default=Decimal(0), ge=0, decimal_places=2)
    cofins_cst: str | None = None
    cofins_base: Decimal = Field(default=Decimal(0), ge=0, decimal_places=2)
    cofins_aliquota: Decimal = Field(default=Decimal(0), ge=0, decimal_places=4)
    cofins_valor: Decimal = Field(default=Decimal(0), ge=0, decimal_places=2)
    iss_base: Decimal = Field(default=Decimal(0), ge=0, decimal_places=2)
    iss_aliquota: Decimal = Field(default=Decimal(0), ge=0, decimal_places=4)
    iss_valor: Decimal = Field(default=Decimal(0), ge=0, decimal_places=2)


class DocumentoCreate(BaseModel):
    """Documento digitado manualmente (NFS-e, nota de serviço tomado, documentos sem XML)."""
    modelo: ModeloDocumento
    tipo_operacao: TipoOperacao
    numero: int = Field(ge=1)
    serie: str = Field(default="1", max_length=10)
    data_emissao: date
    data_entrada_saida: date | None = None
    participante_id: UUID | None = None
    natureza_operacao: str | None = Field(default=None, max_length=100)
    chave_acesso: str | None = Field(default=None, pattern=r"^[0-9]{44}$")
    status: StatusDocumento = StatusDocumento.AUTORIZADO
    protocolo: str | None = None
    informacoes_complementares: str | None = Field(default=None, max_length=5000)
    valor_iss_retido: Decimal = Field(default=Decimal(0), ge=0, decimal_places=2)
    valor_irrf_retido: Decimal = Field(default=Decimal(0), ge=0, decimal_places=2)
    valor_pis_retido: Decimal = Field(default=Decimal(0), ge=0, decimal_places=2)
    valor_cofins_retido: Decimal = Field(default=Decimal(0), ge=0, decimal_places=2)
    valor_csll_retida: Decimal = Field(default=Decimal(0), ge=0, decimal_places=2)
    valor_inss_retido: Decimal = Field(default=Decimal(0), ge=0, decimal_places=2)
    itens: list[ItemIn] = Field(min_length=1, max_length=990)


class ItemOut(BaseModel):
    id: UUID
    numero_item: int
    produto_id: UUID | None
    codigo_externo: str | None
    descricao: str
    ncm: str | None
    cest: str | None
    cfop: str | None
    cfop_documento: str | None
    codigo_servico: str | None
    unidade: str | None
    quantidade: Decimal
    valor_unitario: Decimal
    valor_bruto: Dinheiro
    valor_frete: Dinheiro
    valor_seguro: Dinheiro
    valor_desconto: Dinheiro
    valor_outras: Dinheiro
    compoe_total: bool
    icms_origem: int | None
    icms_cst: str | None
    icms_base: Dinheiro
    icms_aliquota: Decimal
    icms_valor: Dinheiro
    icms_st_base: Dinheiro
    icms_st_valor: Dinheiro
    ipi_cst: str | None
    ipi_base: Dinheiro
    ipi_aliquota: Decimal
    ipi_valor: Dinheiro
    pis_cst: str | None
    pis_base: Dinheiro
    pis_aliquota: Decimal
    pis_valor: Dinheiro
    cofins_cst: str | None
    cofins_base: Dinheiro
    cofins_aliquota: Decimal
    cofins_valor: Dinheiro
    iss_base: Dinheiro
    iss_aliquota: Decimal
    iss_valor: Dinheiro

    model_config = {"from_attributes": True}


class ParticipanteResumo(BaseModel):
    id: UUID
    cnpj_cpf: str
    razao_social: str

    model_config = {"from_attributes": True}


class DocumentoOut(BaseModel):
    id: UUID
    modelo: ModeloDocumento
    tipo_operacao: TipoOperacao
    status: StatusDocumento
    origem: OrigemDocumento
    chave_acesso: str | None
    numero: int
    serie: str
    data_emissao: date
    data_entrada_saida: date | None
    participante: ParticipanteResumo | None
    natureza_operacao: str | None
    finalidade: int | None
    protocolo: str | None
    valor_produtos: Dinheiro
    valor_servicos: Dinheiro
    valor_frete: Dinheiro
    valor_seguro: Dinheiro
    valor_desconto: Dinheiro
    valor_outras: Dinheiro
    valor_ipi: Dinheiro
    valor_icms: Dinheiro
    valor_icms_st: Dinheiro
    valor_pis: Dinheiro
    valor_cofins: Dinheiro
    valor_iss: Dinheiro
    valor_iss_retido: Dinheiro
    valor_irrf_retido: Dinheiro
    valor_pis_retido: Dinheiro
    valor_cofins_retido: Dinheiro
    valor_csll_retida: Dinheiro
    valor_inss_retido: Dinheiro
    valor_total: Dinheiro
    informacoes_complementares: str | None
    lancamento_id: UUID | None
    contabilizado_em: datetime | None
    cancelado_em: datetime | None
    motivo_cancelamento: str | None
    itens_sem_produto: int
    criado_em: datetime
    itens: list[ItemOut]

    model_config = {"from_attributes": True}


class DocumentoResumoOut(BaseModel):
    id: UUID
    modelo: ModeloDocumento
    tipo_operacao: TipoOperacao
    status: StatusDocumento
    chave_acesso: str | None
    numero: int
    serie: str
    data_emissao: date
    participante: ParticipanteResumo | None
    valor_total: Dinheiro
    lancamento_id: UUID | None

    model_config = {"from_attributes": True}


class DocumentoPage(BaseModel):
    items: list[DocumentoResumoOut]
    total: int
    limit: int
    offset: int


class ImportacaoResultado(BaseModel):
    arquivo: str
    sucesso: bool
    documento_id: UUID | None = None
    chave_acesso: str | None = None
    erro: str | None = None


class CancelarIn(BaseModel):
    motivo: str = Field(min_length=15, max_length=255)
    protocolo: str | None = None
    data_estorno: date | None = Field(default=None, description="Data do lançamento de estorno; padrão hoje")


class ItemPatchIn(BaseModel):
    produto_codigo: str | None = None
    criar_referencia: bool = Field(default=True, description="Grava o de-para fornecedor+código externo → produto")
    cfop: str | None = Field(default=None, pattern=r"^[1-7][0-9]{3}$", description="CFOP sob a ótica da empresa")

    @model_validator(mode="after")
    def _algo(self):
        if self.produto_codigo is None and self.cfop is None:
            raise ValueError("informe produto_codigo e/ou cfop")
        return self


class ResumoCfopLinha(BaseModel):
    tipo_operacao: TipoOperacao
    cfop: str | None
    documentos: int
    valor_bruto: Dinheiro
    icms_base: Dinheiro
    icms_valor: Dinheiro
    icms_st_valor: Dinheiro
    ipi_valor: Dinheiro
    pis_valor: Dinheiro
    cofins_valor: Dinheiro
    iss_valor: Dinheiro


class ResumoFiscalOut(BaseModel):
    inicio: date
    fim: date
    linhas: list[ResumoCfopLinha]
    total_entradas: Dinheiro
    total_saidas: Dinheiro


# ---------------------------------------------------------------- regras de contabilização
class RegraLinhaIn(BaseModel):
    componente: ComponenteFiscal
    lado: NaturezaConta
    conta_codigo: str


class RegraCreate(BaseModel):
    nome: str = Field(min_length=1, max_length=200)
    prioridade: int = Field(default=100, ge=0, le=10000)
    modelo: ModeloDocumento | None = None
    tipo_operacao: TipoOperacao | None = None
    cfops: list[str] | None = Field(default=None, description="CFOPs exatos ou prefixos, ex.: ['5102', '61']")
    tipo_item: TipoItem | None = None
    contabilizar: bool = True
    historico_modelo: str | None = Field(default=None, max_length=500)
    linhas: list[RegraLinhaIn] = Field(default_factory=list)

    @field_validator("cfops")
    @classmethod
    def _cfops(cls, v):
        if v is None:
            return None
        out = []
        for c in v:
            c = c.strip()
            if not c.isdigit() or not 1 <= len(c) <= 4:
                raise ValueError(f"CFOP inválido: {c!r}")
            out.append(c)
        return out or None

    @model_validator(mode="after")
    def _linhas(self):
        if self.contabilizar and len(self.linhas) < 2:
            raise ValueError("regra que contabiliza precisa de ao menos duas linhas")
        residuais = [x for x in self.linhas if x.componente == ComponenteFiscal.RESIDUAL]
        if len(residuais) > 1:
            raise ValueError("no máximo uma linha RESIDUAL por regra")
        return self


class RegraUpdate(BaseModel):
    nome: str | None = None
    prioridade: int | None = Field(default=None, ge=0, le=10000)
    ativa: bool | None = None
    modelo: ModeloDocumento | None = None
    tipo_operacao: TipoOperacao | None = None
    cfops: list[str] | None = None
    tipo_item: TipoItem | None = None
    contabilizar: bool | None = None
    historico_modelo: str | None = None
    linhas: list[RegraLinhaIn] | None = None


class RegraLinhaOut(BaseModel):
    ordem: int
    componente: ComponenteFiscal
    lado: NaturezaConta
    conta_id: UUID
    conta_codigo: str
    conta_nome: str


class RegraOut(BaseModel):
    id: UUID
    nome: str
    prioridade: int
    ativa: bool
    modelo: ModeloDocumento | None
    tipo_operacao: TipoOperacao | None
    cfops: list[str] | None
    tipo_item: TipoItem | None
    contabilizar: bool
    historico_modelo: str | None
    linhas: list[RegraLinhaOut]


class PartidaPrevia(BaseModel):
    conta_codigo: str
    conta_nome: str
    debito: Dinheiro
    credito: Dinheiro
    componente: ComponenteFiscal
    cfop: str | None
    regra: str


class PreviaContabilizacao(BaseModel):
    data: date
    historico: str
    partidas: list[PartidaPrevia]
    total_debito: Dinheiro
    total_credito: Dinheiro
    grupos_sem_regra: list[str]
    avisos: list[str]
