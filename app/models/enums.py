import enum


class RegimeTributario(str, enum.Enum):
    MEI = "MEI"
    SIMPLES = "SIMPLES"
    PRESUMIDO = "PRESUMIDO"
    REAL = "REAL"


class PapelEmpresa(str, enum.Enum):
    ADMIN = "ADMIN"
    CONTADOR = "CONTADOR"
    LEITURA = "LEITURA"


class GrupoConta(str, enum.Enum):
    ATIVO = "ATIVO"
    PASSIVO = "PASSIVO"
    PATRIMONIO_LIQUIDO = "PATRIMONIO_LIQUIDO"
    RECEITA = "RECEITA"
    DESPESA = "DESPESA"


class NaturezaConta(str, enum.Enum):
    D = "D"
    C = "C"


class TipoConta(str, enum.Enum):
    SINTETICA = "SINTETICA"
    ANALITICA = "ANALITICA"


class StatusPeriodo(str, enum.Enum):
    ABERTO = "ABERTO"
    FECHADO = "FECHADO"


class StatusLancamento(str, enum.Enum):
    RASCUNHO = "RASCUNHO"
    EFETIVADO = "EFETIVADO"
    ESTORNADO = "ESTORNADO"


class OrigemLancamento(str, enum.Enum):
    MANUAL = "MANUAL"
    INTEGRACAO = "INTEGRACAO"
    APURACAO = "APURACAO"
    ESTORNO = "ESTORNO"


# ---------------------------------------------------------------- fiscal
class TipoPessoa(str, enum.Enum):
    PJ = "PJ"
    PF = "PF"
    EXTERIOR = "EXTERIOR"


class IndicadorIE(str, enum.Enum):
    CONTRIBUINTE = "CONTRIBUINTE"
    ISENTO = "ISENTO"
    NAO_CONTRIBUINTE = "NAO_CONTRIBUINTE"


class TipoItem(str, enum.Enum):
    MERCADORIA_REVENDA = "MERCADORIA_REVENDA"
    MATERIA_PRIMA = "MATERIA_PRIMA"
    EMBALAGEM = "EMBALAGEM"
    PRODUTO_EM_PROCESSO = "PRODUTO_EM_PROCESSO"
    PRODUTO_ACABADO = "PRODUTO_ACABADO"
    SUBPRODUTO = "SUBPRODUTO"
    PRODUTO_INTERMEDIARIO = "PRODUTO_INTERMEDIARIO"
    USO_CONSUMO = "USO_CONSUMO"
    ATIVO_IMOBILIZADO = "ATIVO_IMOBILIZADO"
    SERVICO = "SERVICO"
    OUTROS_INSUMOS = "OUTROS_INSUMOS"
    OUTRAS = "OUTRAS"


class ModeloDocumento(str, enum.Enum):
    NFE = "NFE"
    NFCE = "NFCE"
    NFSE = "NFSE"
    CTE = "CTE"


class TipoOperacao(str, enum.Enum):
    ENTRADA = "ENTRADA"
    SAIDA = "SAIDA"


class StatusDocumento(str, enum.Enum):
    DIGITADO = "DIGITADO"
    AUTORIZADO = "AUTORIZADO"
    CANCELADO = "CANCELADO"
    DENEGADO = "DENEGADO"


class OrigemDocumento(str, enum.Enum):
    XML = "XML"
    MANUAL = "MANUAL"
    API = "API"


class ComponenteFiscal(str, enum.Enum):
    TOTAL = "TOTAL"
    LIQUIDO = "LIQUIDO"
    PRODUTOS = "PRODUTOS"
    SERVICOS = "SERVICOS"
    FRETE = "FRETE"
    SEGURO = "SEGURO"
    DESCONTO = "DESCONTO"
    OUTRAS = "OUTRAS"
    IPI = "IPI"
    ICMS = "ICMS"
    ICMS_ST = "ICMS_ST"
    PIS = "PIS"
    COFINS = "COFINS"
    ISS = "ISS"
    ISS_RETIDO = "ISS_RETIDO"
    IRRF_RETIDO = "IRRF_RETIDO"
    PIS_RETIDO = "PIS_RETIDO"
    COFINS_RETIDO = "COFINS_RETIDO"
    CSLL_RETIDA = "CSLL_RETIDA"
    INSS_RETIDO = "INSS_RETIDO"
    RESIDUAL = "RESIDUAL"
