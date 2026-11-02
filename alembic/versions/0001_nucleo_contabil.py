"""Núcleo contábil: usuários, empresas, plano de contas, lançamentos, períodos, auditoria.

Integridade garantida no banco, não só na aplicação:
  * partidas de um lançamento efetivado têm débitos = créditos (constraint trigger deferido);
  * lançamento efetivado/estornado é imutável (só muda status para ESTORNADO);
  * não se efetiva lançamento em período fechado nem anterior a um período fechado;
  * só conta ANALÍTICA ativa recebe partida;
  * Row Level Security isola cada empresa pelo GUC app.empresa_id.

Revision ID: 0001
Revises:
"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

SQL_UP = r"""
-- ---------------------------------------------------------------- utilidades
CREATE OR REPLACE FUNCTION fn_touch_atualizado_em() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  NEW.atualizado_em := now();
  RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION fn_empresa_atual() RETURNS uuid
LANGUAGE sql STABLE AS $$
  SELECT NULLIF(current_setting('app.empresa_id', true), '')::uuid
$$;

-- ---------------------------------------------------------------- identidade
CREATE TABLE usuario (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email            text NOT NULL,
  nome             text NOT NULL,
  senha_hash       text NOT NULL,
  ativo            boolean NOT NULL DEFAULT true,
  admin_escritorio boolean NOT NULL DEFAULT false,
  falhas_login     integer NOT NULL DEFAULT 0,
  bloqueado_ate    timestamptz,
  criado_em        timestamptz NOT NULL DEFAULT now(),
  atualizado_em    timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX ux_usuario_email ON usuario (lower(email));
CREATE TRIGGER trg_usuario_touch BEFORE UPDATE ON usuario
  FOR EACH ROW EXECUTE FUNCTION fn_touch_atualizado_em();

CREATE TABLE refresh_token (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  usuario_id  uuid NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
  token_hash  text NOT NULL UNIQUE,
  expira_em   timestamptz NOT NULL,
  revogado_em timestamptz,
  criado_em   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_refresh_token_usuario ON refresh_token (usuario_id);

CREATE TYPE regime_tributario AS ENUM ('MEI', 'SIMPLES', 'PRESUMIDO', 'REAL');

CREATE TABLE empresa (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  razao_social         text NOT NULL,
  nome_fantasia        text,
  cnpj                 char(14) NOT NULL UNIQUE CHECK (cnpj ~ '^[0-9]{14}$'),
  regime_tributario    regime_tributario NOT NULL,
  inicio_exercicio_mes smallint NOT NULL DEFAULT 1 CHECK (inicio_exercicio_mes BETWEEN 1 AND 12),
  ativa                boolean NOT NULL DEFAULT true,
  proximo_numero_lancamento bigint NOT NULL DEFAULT 1,
  criado_em            timestamptz NOT NULL DEFAULT now(),
  atualizado_em        timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER trg_empresa_touch BEFORE UPDATE ON empresa
  FOR EACH ROW EXECUTE FUNCTION fn_touch_atualizado_em();

CREATE TYPE papel_empresa AS ENUM ('ADMIN', 'CONTADOR', 'LEITURA');

CREATE TABLE usuario_empresa (
  usuario_id uuid NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
  empresa_id uuid NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
  papel      papel_empresa NOT NULL,
  criado_em  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (usuario_id, empresa_id)
);

-- ---------------------------------------------------------------- plano de contas
CREATE TYPE grupo_conta    AS ENUM ('ATIVO', 'PASSIVO', 'PATRIMONIO_LIQUIDO', 'RECEITA', 'DESPESA');
CREATE TYPE natureza_conta AS ENUM ('D', 'C');
CREATE TYPE tipo_conta     AS ENUM ('SINTETICA', 'ANALITICA');

CREATE TABLE conta (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  empresa_id        uuid NOT NULL REFERENCES empresa(id),
  codigo            text NOT NULL CHECK (codigo ~ '^[0-9]+(\.[0-9]+)*$'),
  nome              text NOT NULL,
  grupo             grupo_conta NOT NULL,
  natureza          natureza_conta NOT NULL,
  tipo              tipo_conta NOT NULL,
  conta_pai_id      uuid,
  nivel             smallint NOT NULL,
  codigo_referencial text,
  ativa             boolean NOT NULL DEFAULT true,
  criado_em         timestamptz NOT NULL DEFAULT now(),
  atualizado_em     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (empresa_id, codigo),
  UNIQUE (id, empresa_id),
  FOREIGN KEY (conta_pai_id, empresa_id) REFERENCES conta(id, empresa_id)
);
CREATE INDEX ix_conta_pai ON conta (conta_pai_id);
CREATE TRIGGER trg_conta_touch BEFORE UPDATE ON conta
  FOR EACH ROW EXECUTE FUNCTION fn_touch_atualizado_em();

CREATE OR REPLACE FUNCTION fn_conta_valida() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE pai conta%ROWTYPE;
BEGIN
  IF NEW.conta_pai_id IS NULL THEN
    NEW.nivel := 1;
  ELSE
    SELECT * INTO pai FROM conta WHERE id = NEW.conta_pai_id;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'conta pai inexistente' USING ERRCODE = 'check_violation';
    END IF;
    IF pai.tipo <> 'SINTETICA' THEN
      RAISE EXCEPTION 'conta pai % deve ser SINTETICA', pai.codigo USING ERRCODE = 'check_violation';
    END IF;
    IF pai.grupo <> NEW.grupo THEN
      RAISE EXCEPTION 'conta % deve pertencer ao mesmo grupo da conta pai (%)', NEW.codigo, pai.grupo
        USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.codigo NOT LIKE pai.codigo || '.%' THEN
      RAISE EXCEPTION 'codigo % deve iniciar com o codigo da conta pai (%)', NEW.codigo, pai.codigo
        USING ERRCODE = 'check_violation';
    END IF;
    NEW.nivel := pai.nivel + 1;
  END IF;
  IF TG_OP = 'UPDATE' AND OLD.tipo = 'ANALITICA' AND NEW.tipo = 'SINTETICA'
     AND EXISTS (SELECT 1 FROM partida WHERE conta_id = NEW.id) THEN
    RAISE EXCEPTION 'conta % possui partidas e nao pode virar SINTETICA', NEW.codigo
      USING ERRCODE = 'check_violation';
  END IF;
  IF TG_OP = 'UPDATE' AND OLD.tipo = 'SINTETICA' AND NEW.tipo = 'ANALITICA'
     AND EXISTS (SELECT 1 FROM conta WHERE conta_pai_id = NEW.id) THEN
    RAISE EXCEPTION 'conta % possui filhas e nao pode virar ANALITICA', NEW.codigo
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_conta_valida BEFORE INSERT OR UPDATE ON conta
  FOR EACH ROW EXECUTE FUNCTION fn_conta_valida();

CREATE TABLE centro_custo (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  empresa_id    uuid NOT NULL REFERENCES empresa(id),
  codigo        text NOT NULL,
  nome          text NOT NULL,
  ativo         boolean NOT NULL DEFAULT true,
  criado_em     timestamptz NOT NULL DEFAULT now(),
  atualizado_em timestamptz NOT NULL DEFAULT now(),
  UNIQUE (empresa_id, codigo),
  UNIQUE (id, empresa_id)
);
CREATE TRIGGER trg_centro_custo_touch BEFORE UPDATE ON centro_custo
  FOR EACH ROW EXECUTE FUNCTION fn_touch_atualizado_em();

-- ---------------------------------------------------------------- períodos
CREATE TYPE status_periodo AS ENUM ('ABERTO', 'FECHADO');

CREATE TABLE periodo (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  empresa_id  uuid NOT NULL REFERENCES empresa(id),
  ano         smallint NOT NULL CHECK (ano BETWEEN 1990 AND 2100),
  mes         smallint NOT NULL CHECK (mes BETWEEN 1 AND 12),
  status      status_periodo NOT NULL DEFAULT 'ABERTO',
  fechado_em  timestamptz,
  fechado_por uuid REFERENCES usuario(id),
  criado_em   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (empresa_id, ano, mes)
);

-- ---------------------------------------------------------------- lançamentos
CREATE TYPE status_lancamento AS ENUM ('RASCUNHO', 'EFETIVADO', 'ESTORNADO');
CREATE TYPE origem_lancamento AS ENUM ('MANUAL', 'INTEGRACAO', 'APURACAO', 'ESTORNO');

CREATE TABLE lancamento (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  empresa_id       uuid NOT NULL REFERENCES empresa(id),
  numero           bigint,
  data             date NOT NULL,
  historico        text NOT NULL CHECK (length(historico) BETWEEN 1 AND 2000),
  status           status_lancamento NOT NULL DEFAULT 'RASCUNHO',
  origem           origem_lancamento NOT NULL DEFAULT 'MANUAL',
  chave_externa    text,
  estorno_de_id    uuid,
  estornado_por_id uuid,
  criado_por       uuid NOT NULL REFERENCES usuario(id),
  efetivado_em     timestamptz,
  efetivado_por    uuid REFERENCES usuario(id),
  criado_em        timestamptz NOT NULL DEFAULT now(),
  atualizado_em    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (empresa_id, numero),
  UNIQUE (empresa_id, chave_externa),
  UNIQUE (id, empresa_id),
  FOREIGN KEY (estorno_de_id, empresa_id)    REFERENCES lancamento(id, empresa_id),
  FOREIGN KEY (estornado_por_id, empresa_id) REFERENCES lancamento(id, empresa_id),
  CHECK (status = 'RASCUNHO' OR numero IS NOT NULL),
  CHECK (status = 'RASCUNHO' OR efetivado_em IS NOT NULL)
);
CREATE INDEX ix_lancamento_empresa_data ON lancamento (empresa_id, data);
CREATE INDEX ix_lancamento_empresa_status ON lancamento (empresa_id, status);
CREATE TRIGGER trg_lancamento_touch BEFORE UPDATE ON lancamento
  FOR EACH ROW EXECUTE FUNCTION fn_touch_atualizado_em();

CREATE TABLE partida (
  id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  empresa_id             uuid NOT NULL REFERENCES empresa(id),
  lancamento_id          uuid NOT NULL,
  conta_id               uuid NOT NULL,
  centro_custo_id        uuid,
  ordem                  smallint NOT NULL DEFAULT 0,
  debito                 numeric(18,2) NOT NULL DEFAULT 0 CHECK (debito >= 0),
  credito                numeric(18,2) NOT NULL DEFAULT 0 CHECK (credito >= 0),
  historico_complementar text,
  CHECK ((debito > 0 AND credito = 0) OR (credito > 0 AND debito = 0)),
  FOREIGN KEY (lancamento_id, empresa_id)   REFERENCES lancamento(id, empresa_id) ON DELETE CASCADE,
  FOREIGN KEY (conta_id, empresa_id)        REFERENCES conta(id, empresa_id),
  FOREIGN KEY (centro_custo_id, empresa_id) REFERENCES centro_custo(id, empresa_id)
);
CREATE INDEX ix_partida_lancamento ON partida (lancamento_id);
CREATE INDEX ix_partida_conta ON partida (empresa_id, conta_id);

-- Partida só em conta analítica ativa.
CREATE OR REPLACE FUNCTION fn_partida_valida() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE c conta%ROWTYPE;
BEGIN
  SELECT * INTO c FROM conta WHERE id = NEW.conta_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'conta inexistente' USING ERRCODE = 'check_violation';
  END IF;
  IF c.tipo <> 'ANALITICA' THEN
    RAISE EXCEPTION 'conta % e SINTETICA e nao aceita partidas', c.codigo USING ERRCODE = 'check_violation';
  END IF;
  IF NOT c.ativa THEN
    RAISE EXCEPTION 'conta % esta inativa', c.codigo USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_partida_valida BEFORE INSERT OR UPDATE ON partida
  FOR EACH ROW EXECUTE FUNCTION fn_partida_valida();

-- Partidas de lançamento não-rascunho são imutáveis.
CREATE OR REPLACE FUNCTION fn_partida_imutavel() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE st status_lancamento;
BEGIN
  SELECT status INTO st FROM lancamento WHERE id = COALESCE(OLD.lancamento_id, NEW.lancamento_id);
  IF st IS NOT NULL AND st <> 'RASCUNHO' THEN
    RAISE EXCEPTION 'partidas de lancamento % nao podem ser alteradas', st USING ERRCODE = 'check_violation';
  END IF;
  IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_partida_imutavel BEFORE UPDATE OR DELETE ON partida
  FOR EACH ROW EXECUTE FUNCTION fn_partida_imutavel();

-- Lançamento: imutável depois de efetivado, salvo a transição EFETIVADO -> ESTORNADO.
CREATE OR REPLACE FUNCTION fn_lancamento_imutavel() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.status <> 'RASCUNHO' THEN
      RAISE EXCEPTION 'lancamento % nao pode ser excluido; use estorno', OLD.status USING ERRCODE = 'check_violation';
    END IF;
    RETURN OLD;
  END IF;
  IF OLD.status = 'ESTORNADO' THEN
    RAISE EXCEPTION 'lancamento estornado e imutavel' USING ERRCODE = 'check_violation';
  END IF;
  IF OLD.status = 'EFETIVADO' THEN
    IF NOT (NEW.status = 'ESTORNADO'
            AND NEW.estornado_por_id IS NOT NULL
            AND NEW.numero IS NOT DISTINCT FROM OLD.numero
            AND NEW.data = OLD.data
            AND NEW.historico = OLD.historico
            AND NEW.origem = OLD.origem
            AND NEW.chave_externa IS NOT DISTINCT FROM OLD.chave_externa
            AND NEW.estorno_de_id IS NOT DISTINCT FROM OLD.estorno_de_id
            AND NEW.efetivado_em = OLD.efetivado_em
            AND NEW.empresa_id = OLD.empresa_id) THEN
      RAISE EXCEPTION 'lancamento efetivado e imutavel; use estorno' USING ERRCODE = 'check_violation';
    END IF;
  END IF;
  IF NEW.status = 'RASCUNHO' AND OLD.status <> 'RASCUNHO' THEN
    RAISE EXCEPTION 'lancamento nao pode voltar a RASCUNHO' USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_lancamento_imutavel BEFORE UPDATE OR DELETE ON lancamento
  FOR EACH ROW EXECUTE FUNCTION fn_lancamento_imutavel();

-- Não se efetiva em período fechado nem em data anterior a período fechado.
CREATE OR REPLACE FUNCTION fn_lancamento_periodo_aberto() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.status = 'EFETIVADO' AND (TG_OP = 'INSERT' OR OLD.status <> 'EFETIVADO') THEN
    IF EXISTS (
      SELECT 1 FROM periodo p
      WHERE p.empresa_id = NEW.empresa_id
        AND p.status = 'FECHADO'
        AND make_date(p.ano, p.mes, 1) >= date_trunc('month', NEW.data)::date
    ) THEN
      RAISE EXCEPTION 'periodo contabil de % esta fechado ou anterior a periodo fechado', to_char(NEW.data, 'MM/YYYY')
        USING ERRCODE = 'check_violation';
    END IF;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_lancamento_periodo_aberto BEFORE INSERT OR UPDATE ON lancamento
  FOR EACH ROW EXECUTE FUNCTION fn_lancamento_periodo_aberto();

-- Partidas dobradas: ao final da transação, todo lançamento não-rascunho fecha.
CREATE OR REPLACE FUNCTION fn_verifica_balanco(p_lancamento uuid) RETURNS void
LANGUAGE plpgsql AS $$
DECLARE st status_lancamento; n int; d numeric; c numeric;
BEGIN
  SELECT status INTO st FROM lancamento WHERE id = p_lancamento;
  IF st IS NULL OR st = 'RASCUNHO' THEN RETURN; END IF;
  SELECT count(*), coalesce(sum(debito),0), coalesce(sum(credito),0) INTO n, d, c
    FROM partida WHERE lancamento_id = p_lancamento;
  IF n < 2 THEN
    RAISE EXCEPTION 'lancamento precisa de ao menos duas partidas' USING ERRCODE = 'check_violation';
  END IF;
  IF d <> c THEN
    RAISE EXCEPTION 'lancamento desbalanceado: debitos % <> creditos %', d, c USING ERRCODE = 'check_violation';
  END IF;
END $$;

CREATE OR REPLACE FUNCTION fn_trg_balanco_partida() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  PERFORM fn_verifica_balanco(COALESCE(NEW.lancamento_id, OLD.lancamento_id));
  RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER trg_balanco_partida
  AFTER INSERT OR UPDATE OR DELETE ON partida
  DEFERRABLE INITIALLY DEFERRED
  FOR EACH ROW EXECUTE FUNCTION fn_trg_balanco_partida();

CREATE OR REPLACE FUNCTION fn_trg_balanco_lancamento() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  PERFORM fn_verifica_balanco(NEW.id);
  RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER trg_balanco_lancamento
  AFTER INSERT OR UPDATE OF status ON lancamento
  DEFERRABLE INITIALLY DEFERRED
  FOR EACH ROW EXECUTE FUNCTION fn_trg_balanco_lancamento();

-- ---------------------------------------------------------------- auditoria
CREATE TABLE auditoria (
  id          bigserial PRIMARY KEY,
  empresa_id  uuid,
  usuario_id  uuid,
  acao        text NOT NULL,
  entidade    text NOT NULL,
  entidade_id text,
  dados       jsonb,
  ip          text,
  criado_em   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_auditoria_empresa ON auditoria (empresa_id, criado_em DESC);

-- Auditoria é somente-acréscimo.
CREATE OR REPLACE FUNCTION fn_auditoria_somente_insert() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'auditoria e somente-acrescimo' USING ERRCODE = 'check_violation';
END $$;
CREATE TRIGGER trg_auditoria_somente_insert BEFORE UPDATE OR DELETE ON auditoria
  FOR EACH ROW EXECUTE FUNCTION fn_auditoria_somente_insert();

-- ---------------------------------------------------------------- Row Level Security
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['conta', 'centro_custo', 'periodo', 'lancamento', 'partida'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format(
      'CREATE POLICY isolamento_empresa ON %I USING (empresa_id = fn_empresa_atual()) WITH CHECK (empresa_id = fn_empresa_atual())',
      t);
  END LOOP;
END $$;
"""

SQL_DOWN = r"""
DROP TABLE IF EXISTS auditoria, partida, lancamento, periodo, centro_custo, conta,
  usuario_empresa, empresa, refresh_token, usuario CASCADE;
DROP FUNCTION IF EXISTS fn_trg_balanco_lancamento, fn_trg_balanco_partida, fn_verifica_balanco,
  fn_lancamento_periodo_aberto, fn_lancamento_imutavel, fn_partida_imutavel, fn_partida_valida,
  fn_conta_valida, fn_auditoria_somente_insert, fn_empresa_atual, fn_touch_atualizado_em CASCADE;
DROP TYPE IF EXISTS origem_lancamento, status_lancamento, status_periodo, tipo_conta,
  natureza_conta, grupo_conta, papel_empresa, regime_tributario;
"""


def upgrade() -> None:
    op.execute(SQL_UP)


def downgrade() -> None:
    op.execute(SQL_DOWN)
