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
