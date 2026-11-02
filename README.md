# Fiber Finance — Contabilidade

Sistema de contabilidade multiempresa da Fiber Finance, com API REST.

- **Núcleo contábil:** plano de contas, lançamentos de partidas dobradas, períodos, razão, balancete,
  DRE, balanço patrimonial e apuração do resultado.
- **Fiscal, fase 1:** participantes, produtos com de-para de códigos, importação de XML de NF-e/NFC-e,
  documentos fiscais com impostos por item, NFS-e digitada, regras de contabilização automática com
  padrões por regime, cancelamento com estorno, resumo por CFOP.

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
uv run pytest -q        # 42 testes: invariantes contábeis, fiscal, isolamento entre empresas, auth
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
| Participantes | `GET/POST /empresas/{id}/participantes`, `GET/PATCH .../{pid}` |
| Produtos | `GET/POST /empresas/{id}/produtos`, `GET/PATCH .../{pid}`, `GET/PUT .../{pid}/referencias` |
| Documentos fiscais | `GET/POST /empresas/{id}/documentos-fiscais`, `POST .../importar-xml`, `GET .../resumo`, `GET/DELETE .../{did}`, `GET .../{did}/xml`, `PATCH .../{did}/itens/{n}`, `POST .../{did}/cancelar`, `GET .../{did}/previa-contabilizacao`, `POST .../{did}/contabilizar` |
| Regras de contabilização | `GET/POST /empresas/{id}/regras-contabilizacao`, `POST .../padrao`, `PATCH/DELETE .../{rid}` |

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

## Módulo fiscal (fase 1)

Fluxo: **importar XML → conferir/ajustar itens → prévia → contabilizar**.

1. `POST /empresas/{id}/documentos-fiscais/importar-xml` (multipart, vários arquivos). Cada XML é lido
   com `defusedxml`, a chave de acesso é validada (dígito verificador), o CNPJ do emitente é
   conferido com a chave, e o documento só entra se a empresa for emitente ou destinatária. Fornecedor
   ou cliente é cadastrado automaticamente como participante. Em entradas, o CFOP do emitente (5/6xxx)
   é convertido para o CFOP de entrada (1/2xxx); o original fica em `cfop_documento`. O XML inteiro é
   guardado com hash SHA-256.
2. Itens de entrada chegam sem produto interno (o código é do fornecedor). `PATCH .../itens/{n}` vincula
   a um produto e grava o de-para; as próximas notas do mesmo fornecedor já vêm mapeadas. O mesmo
   endpoint corrige o CFOP de entrada quando a conversão automática não serve.
3. `GET .../previa-contabilizacao` mostra as partidas que seriam geradas, sem gravar.
4. `POST .../contabilizar` gera um lançamento `INTEGRACAO` com `chave_externa = docfis:{id}`, efetivado
   no período da data de entrada/emissão. `?recontabilizar=true` estorna o lançamento atual e refaz.
5. `POST .../cancelar` marca o documento como cancelado e estorna o lançamento, se houver.

**Regras de contabilização** (`/empresas/{id}/regras-contabilizacao`): cada regra casa por modelo,
tipo de operação, lista de CFOPs (exatos ou prefixos) e tipo de item, e tem linhas
`(componente, lado, conta)`. Componentes: `TOTAL`, `PRODUTOS`, `SERVICOS`, `FRETE`, `DESCONTO`, `IPI`,
`ICMS`, `ICMS_ST`, `PIS`, `COFINS`, `ISS`, retenções (`ISS_RETIDO`, `IRRF_RETIDO`, ...) e `RESIDUAL`,
que recebe o que falta para fechar. Componentes com valor zero não geram partida, então uma regra de
venda serve para Simples (sem destaque) e para Presumido/Real (com destaque).

`POST .../regras-contabilizacao/padrao` cria 16 regras conforme o regime da empresa: compras para
revenda/industrialização/uso e consumo/imobilizado, energia, fretes, devoluções, serviços tomados e
prestados (NF-e e NFS-e), vendas e remessas sem efeito contábil. Lucro Presumido credita ICMS/IPI nas
compras; Lucro Real credita também PIS/COFINS; ambos destacam impostos nas vendas. **Essas regras são um
ponto de partida e precisam de revisão do contador responsável pela empresa**, em especial CFOPs
1949/5949, transferências e devoluções com retorno ao estoque.

Para empresas criadas antes da fase fiscal, `POST .../contas/plano-padrao?completar=true` insere as
contas novas que as regras usam, sem alterar as existentes.

## Estrutura

```
app/core        config, sessão de banco + contexto de tenant, JWT/argon2, erros de domínio
app/models      SQLAlchemy (espelham o schema da migração)
app/schemas     Pydantic de entrada/saída
app/services    regras de negócio: auth, empresas, contas, lancamentos, periodos, relatorios, auditoria
app/services/fiscal  cadastros, nfe_xml (parser), documentos, contabilizacao (motor + regras padrão)
app/api/v1      routers FastAPI; deps.py resolve usuário, papel e tenant
alembic/        migrações (schema, triggers, RLS em SQL explícito)
tests/          pytest contra Postgres real (TEST_DATABASE_URL)
```

## Roadmap

1. **Fiscal, fase 2:** leitura de XML de NFS-e (padrão nacional e ABRASF), eventos de cancelamento e
   carta de correção por XML, CT-e, apuração de tributos por período (DAS do Simples por anexo e
   fator R, ICMS, ISS, PIS/COFINS), livros de entradas e saídas.
2. **Emissão direta na SEFAZ e prefeituras:** certificado A1 por empresa, assinatura XML, envio
   síncrono/assíncrono, consulta de situação, inutilização, contingência. A camada de documentos já
   guarda chave, protocolo e XML.
3. **SPED ECD/ECF e EFD-Contribuições** a partir dos lançamentos e documentos; plano referencial.
4. **Integrações financeiras:** OFX/CNAB, conciliação bancária, chaves de API por empresa, webhooks.
5. **Interface web.**
