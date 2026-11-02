# Fiber Finance — Contabilidade

Núcleo contábil multiempresa da Fiber Finance, com API REST. Primeira entrega: plano de contas,
lançamentos de partidas dobradas, períodos contábeis, razão, balancete, DRE, balanço patrimonial
e apuração do resultado. Sem módulo fiscal ainda (ver Roadmap).

## Stack

Python 3.12+ · FastAPI · SQLAlchemy 2 · PostgreSQL 16 · Alembic · pytest · uv.

## Subir em desenvolvimento

```bash
cp .env.example .env            # ajuste JWT_SECRET (64+ caracteres aleatórios)
docker compose up -d db         # ou use um Postgres 16 local com o usuário/banco do .env
uv sync
uv run alembic upgrade head
uv run python scripts/bootstrap_admin.py --email adm@fiber.com.br --nome "Admin" --senha 'SenhaForte!2026xyz'
uv run uvicorn app.main:app --reload
```

Swagger em `http://localhost:8000/docs` (desligado quando `ENV=prod`).

```bash
uv run pytest -q        # 27 testes: invariantes contábeis, isolamento entre empresas, auth
uv run ruff check .
```

## Onde a integridade mora: no banco, não só na aplicação

O serviço Python valida e devolve mensagens amigáveis, mas o Postgres é a última linha. Mesmo um
`UPDATE` direto por SQL esbarra nisto (`alembic/versions/0001_nucleo_contabil.py`):

| Regra | Mecanismo |
|---|---|
| Débitos = créditos em todo lançamento efetivado | constraint trigger deferido, checado no commit |
| Lançamento efetivado é imutável; só transita para ESTORNADO | trigger BEFORE UPDATE/DELETE |
| Partidas de lançamento não-rascunho são imutáveis | trigger BEFORE UPDATE/DELETE |
| Não se efetiva em período fechado nem antes de um período fechado | trigger BEFORE INSERT/UPDATE |
| Partida só em conta ANALÍTICA ativa | trigger + FK composta `(conta_id, empresa_id)` |
| Conta filha herda grupo e prefixo de código da conta pai | trigger |
| Auditoria é somente-acréscimo | trigger bloqueia UPDATE/DELETE |
| Uma empresa nunca enxerga dados de outra | Row Level Security com `FORCE`, política por `app.empresa_id` |

Correção de erro é sempre por **estorno** (lançamento inverso com `origem=ESTORNO`, vínculo nos dois
sentidos). Numeração sequencial por empresa é atribuída na efetivação, sob lock da linha da empresa.

## Modelo de segurança

- **Autenticação:** JWT de acesso curto (15 min) + refresh token rotativo (hash SHA-256 no banco).
  Reuso de refresh token já rotacionado revoga todas as sessões do usuário.
- **Senhas:** argon2id. Bloqueio temporário após 5 falhas. Resposta idêntica para usuário
  inexistente e senha errada.
- **Autorização em dois níveis:**
  - `admin_escritorio`: administra usuários e cadastra empresas; tem papel ADMIN em todas.
  - papel por empresa: `LEITURA` (relatórios) < `CONTADOR` (lança, efetiva, estorna) < `ADMIN`
    (plano de contas, fechamento/reabertura de período, apuração, vínculos de usuários).
- **Isolamento de tenant:** toda rota `/empresas/{empresa_id}/...` verifica vínculo e faz
  `SET LOCAL app.empresa_id` na transação. Sem o GUC, as tabelas de tenant retornam zero linhas.
  Empresa à qual o usuário não tem acesso responde **404**, não 403.
- **Auditoria:** quem, quando, de onde (IP) e o quê, para toda mutação relevante, inclusive
  tentativas de login falhas e reaberturas de período (com motivo obrigatório).
- **Cabeçalhos:** `nosniff`, `X-Frame-Options: DENY`, `Cache-Control: no-store`, HSTS em prod.
- **Pendente para produção:** rate limiting na borda, TLS terminado por proxy, rotação de
  `JWT_SECRET`, backup com PITR, chaves de API para integrações máquina-a-máquina.

## API (prefixo `/api/v1`)

| Área | Rotas |
|---|---|
| Auth | `POST /auth/login`, `/auth/refresh`, `/auth/logout`, `/auth/trocar-senha`, `GET /auth/me` |
| Usuários (admin escritório) | `POST/GET /usuarios`, `PATCH /usuarios/{id}` |
| Empresas | `POST/GET /empresas`, `GET/PATCH /empresas/{id}`, `GET/PUT/DELETE /empresas/{id}/usuarios` |
| Plano de contas | `GET/POST /empresas/{id}/contas`, `GET/PATCH .../contas/{codigo}`, `POST .../contas/plano-padrao` |
| Centros de custo | `GET/POST /empresas/{id}/centros-custo`, `PATCH .../{codigo}` |
| Lançamentos | `GET/POST /empresas/{id}/lancamentos`, `GET/PUT/DELETE .../{lid}`, `POST .../{lid}/efetivar`, `POST .../{lid}/estornar` |
| Períodos | `GET /empresas/{id}/periodos`, `POST .../{ano}/{mes}/fechar`, `.../reabrir`, `POST .../apuracao` |
| Relatórios | `GET /empresas/{id}/relatorios/razao`, `/balancete`, `/dre`, `/balanco` |
| Auditoria | `GET /empresas/{id}/auditoria` |

Exemplo de lançamento (integração idempotente por `chave_externa`):

```json
POST /api/v1/empresas/{id}/lancamentos
{
  "data": "2026-10-15",
  "historico": "NF-e 1234 — venda à vista",
  "origem": "INTEGRACAO",
  "chave_externa": "nfe-1234",
  "partidas": [
    {"conta_codigo": "1.1.01.001", "debito": "1800.50"},
    {"conta_codigo": "4.1.01.001", "credito": "1800.50"}
  ]
}
```

Repetir a mesma `chave_externa` devolve **409**; erros de regra contábil devolvem **422** com
`{"code": "regra_contabil", "detail": "..."}`. Valores monetários trafegam como string com duas
casas decimais, nunca como float.

## Estrutura

```
app/core        config, sessão de banco + contexto de tenant, JWT/argon2, erros de domínio
app/models      SQLAlchemy (espelham o schema da migração)
app/schemas     Pydantic de entrada/saída
app/services    regras de negócio: auth, empresas, contas, lancamentos, periodos, relatorios, auditoria
app/api/v1      routers FastAPI; deps.py resolve usuário, papel e tenant
alembic/        migrações (schema, triggers, RLS em SQL explícito)
tests/          pytest contra Postgres real (TEST_DATABASE_URL)
```

## Roadmap

1. **Fiscal:** cadastro de produtos/serviços com NCM/CFOP/CST, apuração de ICMS/ISS/PIS/COFINS por
   regime, integração com API de emissão de NF-e/NFS-e e consulta SEFAZ, geração de SPED ECD/ECF.
   Cada documento fiscal gera lançamento com `origem=INTEGRACAO` e `chave_externa` = chave do documento.
2. **Integrações financeiras:** importação OFX/CNAB, conciliação bancária, webhooks de entrada.
3. **Plano de contas referencial** (SPED) por regime, com mapeamento `codigo_referencial`.
4. **Multi-tenant SaaS:** cadastro self-service, chaves de API por empresa, limites por plano.
5. **Interface web.**
