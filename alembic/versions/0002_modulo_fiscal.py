"""Módulo fiscal, fase 1: participantes, produtos, documentos fiscais, regras de contabilização.

Revision ID: 0002
Revises: 0001
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

SQL_UP = r"""
CREATE TYPE tipo_pessoa  AS ENUM ('PJ', 'PF', 'EXTERIOR');
CREATE TYPE indicador_ie AS ENUM ('CONTRIBUINTE', 'ISENTO', 'NAO_CONTRIBUINTE');

CREATE TABLE participante (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  empresa_id      uuid NOT NULL REFERENCES empresa(id),
  tipo_pessoa     tipo_pessoa NOT NULL,
  cnpj_cpf        text NOT NULL CHECK (cnpj_cpf ~ '^[0-9A-Za-z]{1,20}$'),
  razao_social    text NOT NULL,
  nome_fantasia   text,
  ie              text,
  im              text,
  indicador_ie    indicador_ie NOT NULL DEFAULT 'NAO_CONTRIBUINTE',
  logradouro      text,
  numero          text,
  complemento     text,
  bairro          text,
  codigo_municipio char(7),
  municipio       text,
  uf              char(2),
  cep             char(8),
  pais            text NOT NULL DEFAULT 'Brasil',
  email           text,
  telefone        text,
  ativo           boolean NOT NULL DEFAULT true,
  criado_em       timestamptz NOT NULL DEFAULT now(),
  atualizado_em   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (empresa_id, cnpj_cpf),
  UNIQUE (id, empresa_id)
);
CREATE TRIGGER trg_participante_touch BEFORE UPDATE ON participante
  FOR EACH ROW EXECUTE FUNCTION fn_touch_atualizado_em();

-- Tipos de item conforme tabela 4.1.? do SPED (00..99), nomeados.
CREATE TYPE tipo_item AS ENUM (
  'MERCADORIA_REVENDA', 'MATERIA_PRIMA', 'EMBALAGEM', 'PRODUTO_EM_PROCESSO', 'PRODUTO_ACABADO',
  'SUBPRODUTO', 'PRODUTO_INTERMEDIARIO', 'USO_CONSUMO', 'ATIVO_IMOBILIZADO', 'SERVICO',
  'OUTROS_INSUMOS', 'OUTRAS'
);

CREATE TABLE produto (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  empresa_id      uuid NOT NULL REFERENCES empresa(id),
  codigo          text NOT NULL,
  descricao       text NOT NULL,
  tipo_item       tipo_item NOT NULL DEFAULT 'MERCADORIA_REVENDA',
  ncm             char(8) CHECK (ncm IS NULL OR ncm ~ '^[0-9]{8}$'),
  cest            char(7) CHECK (cest IS NULL OR cest ~ '^[0-9]{7}$'),
  unidade         text NOT NULL DEFAULT 'UN',
  ean             text,
  origem          smallint CHECK (origem IS NULL OR origem BETWEEN 0 AND 8),
  codigo_servico  text,
  ativo           boolean NOT NULL DEFAULT true,
  criado_em       timestamptz NOT NULL DEFAULT now(),
  atualizado_em   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (empresa_id, codigo),
  UNIQUE (id, empresa_id)
);
CREATE TRIGGER trg_produto_touch BEFORE UPDATE ON produto
  FOR EACH ROW EXECUTE FUNCTION fn_touch_atualizado_em();

-- De-para: código do produto no fornecedor -> produto interno.
CREATE TABLE produto_referencia (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  empresa_id      uuid NOT NULL REFERENCES empresa(id),
  participante_id uuid NOT NULL,
  codigo_externo  text NOT NULL,
  produto_id      uuid NOT NULL,
  criado_em       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (empresa_id, participante_id, codigo_externo),
  FOREIGN KEY (participante_id, empresa_id) REFERENCES participante(id, empresa_id) ON DELETE CASCADE,
  FOREIGN KEY (produto_id, empresa_id)      REFERENCES produto(id, empresa_id) ON DELETE CASCADE
);

CREATE TYPE modelo_documento AS ENUM ('NFE', 'NFCE', 'NFSE', 'CTE');
CREATE TYPE tipo_operacao    AS ENUM ('ENTRADA', 'SAIDA');
CREATE TYPE status_documento AS ENUM ('DIGITADO', 'AUTORIZADO', 'CANCELADO', 'DENEGADO');
CREATE TYPE origem_documento AS ENUM ('XML', 'MANUAL', 'API');

CREATE TABLE documento_fiscal (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  empresa_id           uuid NOT NULL REFERENCES empresa(id),
  modelo               modelo_documento NOT NULL,
  tipo_operacao        tipo_operacao NOT NULL,
  status               status_documento NOT NULL DEFAULT 'DIGITADO',
  origem               origem_documento NOT NULL,
  chave_acesso         char(44) CHECK (chave_acesso IS NULL OR chave_acesso ~ '^[0-9]{44}$'),
  numero               bigint NOT NULL,
  serie                text NOT NULL DEFAULT '1',
  data_emissao         date NOT NULL,
  data_entrada_saida   date,
  participante_id      uuid,
  natureza_operacao    text,
  finalidade           smallint,
  protocolo            text,
  valor_produtos       numeric(18,2) NOT NULL DEFAULT 0,
  valor_servicos       numeric(18,2) NOT NULL DEFAULT 0,
  valor_frete          numeric(18,2) NOT NULL DEFAULT 0,
  valor_seguro         numeric(18,2) NOT NULL DEFAULT 0,
  valor_desconto       numeric(18,2) NOT NULL DEFAULT 0,
  valor_outras         numeric(18,2) NOT NULL DEFAULT 0,
  valor_ipi            numeric(18,2) NOT NULL DEFAULT 0,
  valor_icms           numeric(18,2) NOT NULL DEFAULT 0,
  valor_icms_st        numeric(18,2) NOT NULL DEFAULT 0,
  valor_pis            numeric(18,2) NOT NULL DEFAULT 0,
  valor_cofins         numeric(18,2) NOT NULL DEFAULT 0,
  valor_iss            numeric(18,2) NOT NULL DEFAULT 0,
  valor_iss_retido     numeric(18,2) NOT NULL DEFAULT 0,
  valor_irrf_retido    numeric(18,2) NOT NULL DEFAULT 0,
  valor_pis_retido     numeric(18,2) NOT NULL DEFAULT 0,
  valor_cofins_retido  numeric(18,2) NOT NULL DEFAULT 0,
  valor_csll_retida    numeric(18,2) NOT NULL DEFAULT 0,
  valor_inss_retido    numeric(18,2) NOT NULL DEFAULT 0,
  valor_total          numeric(18,2) NOT NULL DEFAULT 0,
  informacoes_complementares text,
  xml                  text,
  xml_hash             char(64),
  lancamento_id        uuid,
  contabilizado_em     timestamptz,
  cancelado_em         timestamptz,
  motivo_cancelamento  text,
  criado_por           uuid NOT NULL REFERENCES usuario(id),
  criado_em            timestamptz NOT NULL DEFAULT now(),
  atualizado_em        timestamptz NOT NULL DEFAULT now(),
  UNIQUE (id, empresa_id),
  FOREIGN KEY (participante_id, empresa_id) REFERENCES participante(id, empresa_id),
  FOREIGN KEY (lancamento_id, empresa_id)   REFERENCES lancamento(id, empresa_id)
);
CREATE UNIQUE INDEX ux_docfis_chave ON documento_fiscal (empresa_id, chave_acesso)
  WHERE chave_acesso IS NOT NULL;
CREATE UNIQUE INDEX ux_docfis_numero ON documento_fiscal (empresa_id, modelo, serie, numero, participante_id, tipo_operacao)
  WHERE chave_acesso IS NULL;
CREATE INDEX ix_docfis_empresa_data ON documento_fiscal (empresa_id, data_emissao);
CREATE INDEX ix_docfis_participante ON documento_fiscal (participante_id);
CREATE TRIGGER trg_docfis_touch BEFORE UPDATE ON documento_fiscal
  FOR EACH ROW EXECUTE FUNCTION fn_touch_atualizado_em();

-- Documento contabilizado não se apaga; cancela-se (o que estorna o lançamento).
CREATE OR REPLACE FUNCTION fn_docfis_protege() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.lancamento_id IS NOT NULL OR OLD.status = 'CANCELADO' THEN
      RAISE EXCEPTION 'documento contabilizado ou cancelado nao pode ser excluido' USING ERRCODE = 'check_violation';
    END IF;
    RETURN OLD;
  END IF;
  IF OLD.lancamento_id IS NOT NULL AND NEW.lancamento_id IS DISTINCT FROM OLD.lancamento_id
     AND NOT EXISTS (SELECT 1 FROM lancamento l WHERE l.id = OLD.lancamento_id AND l.status = 'ESTORNADO') THEN
    RAISE EXCEPTION 'vinculo contabil do documento so muda apos estorno do lancamento' USING ERRCODE = 'check_violation';
  END IF;
  IF OLD.lancamento_id IS NOT NULL AND (
       NEW.valor_total <> OLD.valor_total OR NEW.modelo <> OLD.modelo OR NEW.tipo_operacao <> OLD.tipo_operacao
       OR NEW.data_emissao <> OLD.data_emissao OR NEW.chave_acesso IS DISTINCT FROM OLD.chave_acesso) THEN
    RAISE EXCEPTION 'documento contabilizado e imutavel; cancele e reimporte' USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_docfis_protege BEFORE UPDATE OR DELETE ON documento_fiscal
  FOR EACH ROW EXECUTE FUNCTION fn_docfis_protege();

CREATE TABLE documento_fiscal_item (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  empresa_id      uuid NOT NULL REFERENCES empresa(id),
  documento_id    uuid NOT NULL,
  numero_item     smallint NOT NULL,
  produto_id      uuid,
  codigo_externo  text,
  descricao       text NOT NULL,
  ncm             char(8),
  cest            char(7),
  cfop            char(4) CHECK (cfop IS NULL OR cfop ~ '^[1-7][0-9]{3}$'),
  cfop_documento  char(4),
  codigo_servico  text,
  unidade         text,
  quantidade      numeric(15,4) NOT NULL DEFAULT 1,
  valor_unitario  numeric(21,10) NOT NULL DEFAULT 0,
  valor_bruto     numeric(18,2) NOT NULL DEFAULT 0,
  valor_frete     numeric(18,2) NOT NULL DEFAULT 0,
  valor_seguro    numeric(18,2) NOT NULL DEFAULT 0,
  valor_desconto  numeric(18,2) NOT NULL DEFAULT 0,
  valor_outras    numeric(18,2) NOT NULL DEFAULT 0,
  compoe_total    boolean NOT NULL DEFAULT true,
  icms_origem     smallint,
  icms_cst        text,
  icms_base       numeric(18,2) NOT NULL DEFAULT 0,
  icms_aliquota   numeric(7,4)  NOT NULL DEFAULT 0,
  icms_valor      numeric(18,2) NOT NULL DEFAULT 0,
  icms_st_base    numeric(18,2) NOT NULL DEFAULT 0,
  icms_st_valor   numeric(18,2) NOT NULL DEFAULT 0,
  ipi_cst         text,
  ipi_base        numeric(18,2) NOT NULL DEFAULT 0,
  ipi_aliquota    numeric(7,4)  NOT NULL DEFAULT 0,
  ipi_valor       numeric(18,2) NOT NULL DEFAULT 0,
  pis_cst         text,
  pis_base        numeric(18,2) NOT NULL DEFAULT 0,
  pis_aliquota    numeric(7,4)  NOT NULL DEFAULT 0,
  pis_valor       numeric(18,2) NOT NULL DEFAULT 0,
  cofins_cst      text,
  cofins_base     numeric(18,2) NOT NULL DEFAULT 0,
  cofins_aliquota numeric(7,4)  NOT NULL DEFAULT 0,
  cofins_valor    numeric(18,2) NOT NULL DEFAULT 0,
  iss_base        numeric(18,2) NOT NULL DEFAULT 0,
  iss_aliquota    numeric(7,4)  NOT NULL DEFAULT 0,
  iss_valor       numeric(18,2) NOT NULL DEFAULT 0,
  UNIQUE (documento_id, numero_item),
  FOREIGN KEY (documento_id, empresa_id) REFERENCES documento_fiscal(id, empresa_id) ON DELETE CASCADE,
  FOREIGN KEY (produto_id, empresa_id)   REFERENCES produto(id, empresa_id)
);
CREATE INDEX ix_docfis_item_documento ON documento_fiscal_item (documento_id);
CREATE INDEX ix_docfis_item_cfop ON documento_fiscal_item (empresa_id, cfop);

-- Componentes de valor de um documento, usados nas regras de contabilização.
CREATE TYPE componente_fiscal AS ENUM (
  'TOTAL', 'LIQUIDO', 'PRODUTOS', 'SERVICOS', 'FRETE', 'SEGURO', 'DESCONTO', 'OUTRAS',
  'IPI', 'ICMS', 'ICMS_ST', 'PIS', 'COFINS', 'ISS',
  'ISS_RETIDO', 'IRRF_RETIDO', 'PIS_RETIDO', 'COFINS_RETIDO', 'CSLL_RETIDA', 'INSS_RETIDO',
  'RESIDUAL'
);

CREATE TABLE regra_contabilizacao (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  empresa_id      uuid NOT NULL REFERENCES empresa(id),
  nome            text NOT NULL,
  prioridade      integer NOT NULL DEFAULT 100,
  ativa           boolean NOT NULL DEFAULT true,
  modelo          modelo_documento,
  tipo_operacao   tipo_operacao,
  cfops           text[],
  tipo_item       tipo_item,
  contabilizar    boolean NOT NULL DEFAULT true,
  historico_modelo text,
  criado_em       timestamptz NOT NULL DEFAULT now(),
  atualizado_em   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (id, empresa_id)
);
CREATE TRIGGER trg_regra_touch BEFORE UPDATE ON regra_contabilizacao
  FOR EACH ROW EXECUTE FUNCTION fn_touch_atualizado_em();

CREATE TABLE regra_contabilizacao_linha (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  empresa_id  uuid NOT NULL REFERENCES empresa(id),
  regra_id    uuid NOT NULL,
  ordem       smallint NOT NULL DEFAULT 0,
  componente  componente_fiscal NOT NULL,
  lado        natureza_conta NOT NULL,
  conta_id    uuid NOT NULL,
  FOREIGN KEY (regra_id, empresa_id) REFERENCES regra_contabilizacao(id, empresa_id) ON DELETE CASCADE,
  FOREIGN KEY (conta_id, empresa_id) REFERENCES conta(id, empresa_id)
);
CREATE INDEX ix_regra_linha_regra ON regra_contabilizacao_linha (regra_id);

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['participante', 'produto', 'produto_referencia', 'documento_fiscal',
                           'documento_fiscal_item', 'regra_contabilizacao', 'regra_contabilizacao_linha'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format(
      'CREATE POLICY isolamento_empresa ON %I USING (empresa_id = fn_empresa_atual()) WITH CHECK (empresa_id = fn_empresa_atual())',
      t);
  END LOOP;
END $$;
"""

SQL_DOWN = r"""
DROP TABLE IF EXISTS regra_contabilizacao_linha, regra_contabilizacao, documento_fiscal_item,
  documento_fiscal, produto_referencia, produto, participante CASCADE;
DROP FUNCTION IF EXISTS fn_docfis_protege CASCADE;
DROP TYPE IF EXISTS componente_fiscal, origem_documento, status_documento, tipo_operacao,
  modelo_documento, tipo_item, indicador_ie, tipo_pessoa;
"""


def upgrade() -> None:
    op.execute(SQL_UP)


def downgrade() -> None:
    op.execute(SQL_DOWN)
