from decimal import Decimal

from sqlalchemy import text

from app.core.db import engine
from tests.conftest import CNPJ_B, criar_empresa, criar_usuario, lancar, login, p

CAIXA, BANCO, CLIENTES = "1.1.01.001", "1.1.01.002", "1.1.02.001"
FORNEC, CAPITAL, LUCROS = "2.1.01.001", "3.1.01.001", "3.3.01.001"
REC_SERV, DESP_ALUGUEL = "4.1.01.002", "5.3.01.001"


def _url(e, *partes):
    return "/api/v1/empresas/" + "/".join([e, *partes])


# ---------------------------------------------------------------- plano de contas
def test_plano_padrao_criado(client, admin, empresa):
    r = client.get(_url(empresa, "contas"), headers=admin)
    assert r.status_code == 200
    contas = r.json()
    assert len(contas) > 100
    assert contas[0]["codigo"] == "1" and contas[0]["tipo"] == "SINTETICA"
    caixa = next(c for c in contas if c["codigo"] == CAIXA)
    assert caixa["tipo"] == "ANALITICA" and caixa["nivel"] == 4 and caixa["natureza"] == "D"
    r = client.post(_url(empresa, "contas", "plano-padrao"), headers=admin)
    assert r.status_code == 409
    # completar: nada falta
    r = client.post(_url(empresa, "contas", "plano-padrao"), headers=admin, params={"completar": "true"})
    assert r.status_code == 201 and r.json()["contas_criadas"] == 0
    # inativa uma conta e completa de novo: não recria nem reativa
    client.patch(_url(empresa, "contas", CAIXA), headers=admin, json={"ativa": False})
    r = client.post(_url(empresa, "contas", "plano-padrao"), headers=admin, params={"completar": "true"})
    assert r.json()["contas_criadas"] == 0
    assert client.get(_url(empresa, "contas", CAIXA), headers=admin).json()["ativa"] is False


def test_conta_nova_valida_hierarquia(client, admin, empresa):
    r = client.post(_url(empresa, "contas"), headers=admin, json={
        "codigo": "1.1.01.009", "nome": "Cofre", "grupo": "ATIVO", "natureza": "D",
        "tipo": "ANALITICA", "conta_pai_codigo": "1.1.01"})
    assert r.status_code == 201 and r.json()["nivel"] == 4
    # grupo diferente do pai
    r = client.post(_url(empresa, "contas"), headers=admin, json={
        "codigo": "1.1.01.010", "nome": "Errada", "grupo": "PASSIVO", "natureza": "C",
        "tipo": "ANALITICA", "conta_pai_codigo": "1.1.01"})
    assert r.status_code == 422
    # pai analítica
    r = client.post(_url(empresa, "contas"), headers=admin, json={
        "codigo": "1.1.01.001.1", "nome": "Errada", "grupo": "ATIVO", "natureza": "D",
        "tipo": "ANALITICA", "conta_pai_codigo": CAIXA})
    assert r.status_code == 422
    # código duplicado
    r = client.post(_url(empresa, "contas"), headers=admin, json={
        "codigo": CAIXA, "nome": "Dup", "grupo": "ATIVO", "natureza": "D", "tipo": "ANALITICA"})
    assert r.status_code == 409


# ---------------------------------------------------------------- lançamentos
def test_lancamento_efetivado_numeracao(client, admin, empresa):
    r = lancar(client, admin, empresa, "2026-01-10", "Integralização de capital",
               [p(BANCO, debito=10000), p(CAPITAL, credito=10000)])
    assert r.status_code == 201, r.text
    l1 = r.json()
    assert l1["status"] == "EFETIVADO" and l1["numero"] == 1
    assert l1["total_debito"] == "10000.00" and l1["total_credito"] == "10000.00"
    r = lancar(client, admin, empresa, "2026-01-15", "Receita de serviço",
               [p(CLIENTES, debito=2500), p(REC_SERV, credito=2500)])
    assert r.json()["numero"] == 2


def test_lancamento_desbalanceado_rejeitado(client, admin, empresa):
    r = lancar(client, admin, empresa, "2026-01-10", "Errado",
               [p(BANCO, debito=100), p(CAPITAL, credito=90)])
    assert r.status_code == 422
    # Rascunho desbalanceado pode existir, mas não efetiva.
    r = lancar(client, admin, empresa, "2026-01-10", "Rascunho",
               [p(BANCO, debito=100), p(CAPITAL, credito=90)], efetivar=False)
    assert r.status_code == 201 and r.json()["status"] == "RASCUNHO"
    lid = r.json()["id"]
    r = client.post(_url(empresa, "lancamentos", lid, "efetivar"), headers=admin)
    assert r.status_code == 422
    assert "desbalanceado" in r.json()["detail"]


def test_partida_em_sintetica_rejeitada(client, admin, empresa):
    r = lancar(client, admin, empresa, "2026-01-10", "Errado",
               [p("1.1.01", debito=100), p(CAPITAL, credito=100)])
    assert r.status_code == 422
    assert "SINTETICA" in r.json()["detail"]


def test_partida_debito_e_credito_juntos_rejeitada(client, admin, empresa):
    r = lancar(client, admin, empresa, "2026-01-10", "Errado",
               [{"conta_codigo": BANCO, "debito": "10", "credito": "10"}, p(CAPITAL, credito=0)])
    assert r.status_code == 422


def test_rascunho_edita_efetiva_e_fica_imutavel(client, admin, empresa):
    r = lancar(client, admin, empresa, "2026-01-10", "Rascunho",
               [p(BANCO, debito=100), p(CAPITAL, credito=100)], efetivar=False)
    lid = r.json()["id"]
    assert r.json()["numero"] is None
    r = client.put(_url(empresa, "lancamentos", lid), headers=admin, json={
        "historico": "Editado", "partidas": [p(CAIXA, debito=250), p(CAPITAL, credito=250)]})
    assert r.status_code == 200 and r.json()["historico"] == "Editado"
    r = client.post(_url(empresa, "lancamentos", lid, "efetivar"), headers=admin)
    assert r.status_code == 200 and r.json()["numero"] == 1
    # imutável
    r = client.put(_url(empresa, "lancamentos", lid), headers=admin, json={"historico": "Hack"})
    assert r.status_code == 422
    r = client.delete(_url(empresa, "lancamentos", lid), headers=admin)
    assert r.status_code == 422
    # mesmo por SQL direto o banco bloqueia
    with engine.begin() as conn:
        conn.execute(text("SELECT set_config('app.empresa_id', :e, true)"), {"e": empresa})
        try:
            conn.execute(text("UPDATE lancamento SET historico = 'hack' WHERE id = :i"), {"i": lid})
            assert False, "deveria falhar"
        except Exception as exc:  # noqa: BLE001
            assert "imutavel" in str(exc)
    with engine.begin() as conn:
        conn.execute(text("SELECT set_config('app.empresa_id', :e, true)"), {"e": empresa})
        try:
            conn.execute(text("UPDATE partida SET debito = 999 WHERE lancamento_id = :i AND debito > 0"), {"i": lid})
            assert False, "deveria falhar"
        except Exception as exc:  # noqa: BLE001
            assert "nao podem ser alteradas" in str(exc)


def test_estorno(client, admin, empresa):
    r = lancar(client, admin, empresa, "2026-01-10", "Aluguel",
               [p(DESP_ALUGUEL, debito=1200), p(BANCO, credito=1200)])
    lid = r.json()["id"]
    r = client.post(_url(empresa, "lancamentos", lid, "estornar"), headers=admin, json={"data": "2026-01-20"})
    assert r.status_code == 201, r.text
    est = r.json()
    assert est["origem"] == "ESTORNO" and est["estorno_de_id"] == lid and est["numero"] == 2
    partidas = {x["conta_codigo"]: x for x in est["partidas"]}
    assert partidas[DESP_ALUGUEL]["credito"] == "1200.00" and partidas[BANCO]["debito"] == "1200.00"
    orig = client.get(_url(empresa, "lancamentos", lid), headers=admin).json()
    assert orig["status"] == "ESTORNADO" and orig["estornado_por_id"] == est["id"]
    # estornar de novo: não
    r = client.post(_url(empresa, "lancamentos", lid, "estornar"), headers=admin, json={"data": "2026-01-21"})
    assert r.status_code == 422
    # saldo líquido zero no razão
    r = client.get(_url(empresa, "relatorios", "razao"), headers=admin,
                   params={"conta_codigo": DESP_ALUGUEL, "inicio": "2026-01-01", "fim": "2026-01-31"})
    assert r.json()["saldo_final"] == "0.00" and len(r.json()["linhas"]) == 2


def test_chave_externa_idempotente(client, admin, empresa):
    partidas = [p(BANCO, debito=10), p(CAPITAL, credito=10)]
    r = lancar(client, admin, empresa, "2026-01-10", "Integração", partidas,
               origem="INTEGRACAO", chave_externa="erp-123")
    assert r.status_code == 201
    r = lancar(client, admin, empresa, "2026-01-10", "Integração repetida", partidas,
               origem="INTEGRACAO", chave_externa="erp-123")
    assert r.status_code == 409


def test_listagem_filtros(client, admin, empresa):
    lancar(client, admin, empresa, "2026-01-10", "Capital", [p(BANCO, debito=100), p(CAPITAL, credito=100)])
    lancar(client, admin, empresa, "2026-02-10", "Aluguel", [p(DESP_ALUGUEL, debito=50), p(BANCO, credito=50)])
    r = client.get(_url(empresa, "lancamentos"), headers=admin, params={"conta_codigo": DESP_ALUGUEL})
    assert r.json()["total"] == 1 and r.json()["items"][0]["historico"] == "Aluguel"
    r = client.get(_url(empresa, "lancamentos"), headers=admin, params={"data_fim": "2026-01-31"})
    assert r.json()["total"] == 1
    r = client.get(_url(empresa, "lancamentos"), headers=admin, params={"q": "alug"})
    assert r.json()["total"] == 1


# ---------------------------------------------------------------- períodos
def test_fechamento_de_periodo(client, admin, empresa):
    lancar(client, admin, empresa, "2026-01-10", "Capital", [p(BANCO, debito=100), p(CAPITAL, credito=100)])
    lancar(client, admin, empresa, "2026-02-10", "Aluguel", [p(DESP_ALUGUEL, debito=50), p(BANCO, credito=50)])
    # fevereiro antes de janeiro: não
    r = client.post(_url(empresa, "periodos", "2026", "2", "fechar"), headers=admin)
    assert r.status_code == 422 and "01/2026" in r.json()["detail"]
    r = client.post(_url(empresa, "periodos", "2026", "1", "fechar"), headers=admin)
    assert r.status_code == 200 and r.json()["status"] == "FECHADO"
    # lançar em janeiro: não
    r = lancar(client, admin, empresa, "2026-01-31", "Atrasado", [p(BANCO, debito=1), p(CAPITAL, credito=1)])
    assert r.status_code == 422 and "fechado" in r.json()["detail"]
    # lançar antes de janeiro (dez/2025): também não
    r = lancar(client, admin, empresa, "2025-12-31", "Retroativo", [p(BANCO, debito=1), p(CAPITAL, credito=1)])
    assert r.status_code == 422
    # trigger do banco também bloqueia update direto para EFETIVADO em período fechado
    r = lancar(client, admin, empresa, "2026-01-05", "Rascunho jan", [p(BANCO, debito=1), p(CAPITAL, credito=1)],
               efetivar=False)
    lid = r.json()["id"]
    with engine.begin() as conn:
        conn.execute(text("SELECT set_config('app.empresa_id', :e, true)"), {"e": empresa})
        try:
            conn.execute(text(
                "UPDATE lancamento SET status='EFETIVADO', numero=999, efetivado_em=now() WHERE id=:i"), {"i": lid})
            assert False
        except Exception as exc:  # noqa: BLE001
            assert "fechado" in str(exc)
    # fevereiro fecha; reabrir janeiro antes de fevereiro: não
    r = client.post(_url(empresa, "periodos", "2026", "2", "fechar"), headers=admin)
    assert r.status_code == 200
    r = client.post(_url(empresa, "periodos", "2026", "1", "reabrir"), headers=admin,
                    json={"motivo": "ajuste solicitado pelo cliente"})
    assert r.status_code == 422
    r = client.post(_url(empresa, "periodos", "2026", "2", "reabrir"), headers=admin,
                    json={"motivo": "ajuste solicitado pelo cliente"})
    assert r.status_code == 200 and r.json()["status"] == "ABERTO"
    r = lancar(client, admin, empresa, "2026-02-28", "Agora pode", [p(BANCO, debito=1), p(CAPITAL, credito=1)])
    assert r.status_code == 201
    # auditoria registrou a reabertura com motivo
    r = client.get(_url(empresa, "auditoria"), headers=admin, params={"entidade": "periodo"})
    acoes = [a["acao"] for a in r.json()]
    assert "reabrir_periodo" in acoes
    assert any(a["dados"].get("motivo") for a in r.json() if a["acao"] == "reabrir_periodo")


def test_fechar_com_rascunho_bloqueia(client, admin, empresa):
    lancar(client, admin, empresa, "2026-01-10", "Rascunho", [p(BANCO, debito=1), p(CAPITAL, credito=1)], efetivar=False)
    r = client.post(_url(empresa, "periodos", "2026", "1", "fechar"), headers=admin)
    assert r.status_code == 422 and "rascunhos" in r.json()["detail"]


# ---------------------------------------------------------------- relatórios
def _cenario(client, admin, empresa):
    lancar(client, admin, empresa, "2026-01-02", "Capital", [p(BANCO, debito=50000), p(CAPITAL, credito=50000)])
    lancar(client, admin, empresa, "2026-01-10", "Serviço a prazo", [p(CLIENTES, debito=12000), p(REC_SERV, credito=12000)])
    lancar(client, admin, empresa, "2026-01-15", "Aluguel", [p(DESP_ALUGUEL, debito=3000), p(BANCO, credito=3000)])
    lancar(client, admin, empresa, "2026-02-05", "Recebimento", [p(BANCO, debito=12000), p(CLIENTES, credito=12000)])
    lancar(client, admin, empresa, "2026-02-20", "Compra a prazo (estoque)",
           [p("1.1.04.001", debito=8000), p(FORNEC, credito=8000)])


def test_razao(client, admin, empresa):
    _cenario(client, admin, empresa)
    r = client.get(_url(empresa, "relatorios", "razao"), headers=admin,
                   params={"conta_codigo": BANCO, "inicio": "2026-02-01", "fim": "2026-02-28"})
    j = r.json()
    assert j["saldo_anterior"] == "47000.00" and j["saldo_anterior_natureza"] == "D"
    assert len(j["linhas"]) == 1 and j["linhas"][0]["saldo"] == "59000.00"
    assert j["saldo_final"] == "59000.00"
    # razão de sintética consolida filhas
    r = client.get(_url(empresa, "relatorios", "razao"), headers=admin,
                   params={"conta_codigo": "1.1.01", "inicio": "2026-01-01", "fim": "2026-02-28"})
    assert r.json()["saldo_final"] == "59000.00"


def test_balancete_fecha(client, admin, empresa):
    _cenario(client, admin, empresa)
    r = client.get(_url(empresa, "relatorios", "balancete"), headers=admin,
                   params={"inicio": "2026-02-01", "fim": "2026-02-28", "somente_com_movimento": "true"})
    j = r.json()
    assert j["total_debitos"] == j["total_creditos"] == "20000.00"
    assert j["total_saldo_devedor"] == j["total_saldo_credor"]
    linhas = {x["codigo"]: x for x in j["linhas"]}
    assert linhas[BANCO]["saldo_anterior"] == "47000.00"
    assert linhas[BANCO]["saldo_atual"] == "59000.00"
    assert linhas[CLIENTES]["saldo_atual"] == "0.00"
    assert linhas["1"]["saldo_atual"] == "67000.00"  # ativo consolidado
    assert linhas["1.1.01"]["debitos"] == "12000.00"


def test_dre_e_balanco(client, admin, empresa):
    _cenario(client, admin, empresa)
    r = client.get(_url(empresa, "relatorios", "dre"), headers=admin, params={"inicio": "2026-01-01", "fim": "2026-02-28"})
    j = r.json()
    assert j["total_receitas"] == "12000.00" and j["total_despesas"] == "3000.00" and j["resultado"] == "9000.00"
    r = client.get(_url(empresa, "relatorios", "balanco"), headers=admin, params={"data": "2026-02-28"})
    b = r.json()
    assert b["total_ativo"] == "67000.00"
    assert b["total_passivo"] == "8000.00"
    assert b["resultado_periodo"] == "9000.00"
    assert b["total_patrimonio_liquido"] == "59000.00"
    assert b["total_passivo_e_pl"] == b["total_ativo"]
    # balanço em 31/01 não vê fevereiro
    r = client.get(_url(empresa, "relatorios", "balanco"), headers=admin, params={"data": "2026-01-31"})
    assert r.json()["total_ativo"] == "59000.00"


def test_apuracao_resultado(client, admin, empresa):
    _cenario(client, admin, empresa)
    r = client.post(_url(empresa, "periodos", "apuracao"), headers=admin,
                    json={"ano": 2026, "conta_resultado_codigo": LUCROS})
    assert r.status_code == 201, r.text
    ap = r.json()
    assert ap["origem"] == "APURACAO" and ap["data"] == "2026-12-31"
    partidas = {x["conta_codigo"]: x for x in ap["partidas"]}
    assert partidas[REC_SERV]["debito"] == "12000.00"
    assert partidas[DESP_ALUGUEL]["credito"] == "3000.00"
    assert partidas[LUCROS]["credito"] == "9000.00"
    b = client.get(_url(empresa, "relatorios", "balanco"), headers=admin, params={"data": "2026-12-31"}).json()
    assert b["resultado_periodo"] == "0.00"
    assert b["total_patrimonio_liquido"] == "59000.00" and b["total_passivo_e_pl"] == b["total_ativo"]
    # repetir: não
    r = client.post(_url(empresa, "periodos", "apuracao"), headers=admin,
                    json={"ano": 2026, "conta_resultado_codigo": LUCROS})
    assert r.status_code == 422


# ---------------------------------------------------------------- isolamento entre empresas
def test_isolamento_entre_empresas(client, admin, empresa):
    empresa_b = criar_empresa(client, admin, cnpj=CNPJ_B, nome="Empresa B")
    lancar(client, admin, empresa, "2026-01-10", "Só na A", [p(BANCO, debito=100), p(CAPITAL, credito=100)])
    criar_usuario("contador@fiber-finance.com.br")
    uid = client.get("/api/v1/usuarios", headers=admin).json()
    uid = next(u["id"] for u in uid if u["email"] == "contador@fiber-finance.com.br")
    r = client.put(_url(empresa_b, "usuarios"), headers=admin, json={"usuario_id": uid, "papel": "CONTADOR"})
    assert r.status_code == 200
    hc = {"Authorization": login(client, "contador@fiber-finance.com.br")["Authorization"]}
    # vê B, não vê A (404 e não 403: não revela existência)
    assert client.get(_url(empresa_b, "lancamentos"), headers=hc).status_code == 200
    assert client.get(_url(empresa, "lancamentos"), headers=hc).status_code == 404
    assert client.get(_url(empresa, "relatorios", "balanco"), headers=hc, params={"data": "2026-01-31"}).status_code == 404
    assert [e["id"] for e in client.get("/api/v1/empresas", headers=hc).json()] == [empresa_b]
    # contador não fecha período nem cria conta (papel ADMIN)
    assert client.post(_url(empresa_b, "periodos", "2026", "1", "fechar"), headers=hc).status_code == 403
    # RLS no banco: sem tenant, zero linhas; com tenant B, zero lançamentos da A
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM lancamento")).scalar() == 0
        assert conn.execute(text("SELECT count(*) FROM conta")).scalar() == 0
    with engine.begin() as conn:
        conn.execute(text("SELECT set_config('app.empresa_id', :e, true)"), {"e": empresa_b})
        assert conn.execute(text("SELECT count(*) FROM lancamento")).scalar() == 0
        conn.execute(text("SELECT set_config('app.empresa_id', :e, true)"), {"e": empresa})
        assert conn.execute(text("SELECT count(*) FROM lancamento")).scalar() == 1
        # inserir partida apontando para conta de outra empresa: FK composta bloqueia
        conta_b = conn.execute(text("SELECT id FROM conta WHERE empresa_id = :b LIMIT 1"), {"b": empresa_b}).scalar()
        assert conta_b is None  # RLS: nem enxerga


def test_leitura_nao_lanca(client, admin, empresa):
    criar_usuario("leitor@fiber-finance.com.br")
    uid = next(u["id"] for u in client.get("/api/v1/usuarios", headers=admin).json() if u["email"] == "leitor@fiber-finance.com.br")
    client.put(_url(empresa, "usuarios"), headers=admin, json={"usuario_id": uid, "papel": "LEITURA"})
    hl = {"Authorization": login(client, "leitor@fiber-finance.com.br")["Authorization"]}
    assert client.get(_url(empresa, "contas"), headers=hl).status_code == 200
    r = lancar(client, hl, empresa, "2026-01-10", "Não pode", [p(BANCO, debito=1), p(CAPITAL, credito=1)])
    assert r.status_code == 403


def test_auditoria_somente_acrescimo():
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO auditoria (acao, entidade) VALUES ('x', 'y')"))
    with engine.begin() as conn:
        try:
            conn.execute(text("DELETE FROM auditoria"))
            assert False
        except Exception as exc:  # noqa: BLE001
            assert "somente-acrescimo" in str(exc)


def test_decimal_precisao(client, admin, empresa):
    r = lancar(client, admin, empresa, "2026-01-10", "Centavos",
               [p(BANCO, debito="0.10"), p(CAIXA, debito="0.20"), p(CAPITAL, credito="0.30")])
    assert r.status_code == 201
    assert Decimal(r.json()["total_debito"]) == Decimal("0.30")
    r = lancar(client, admin, empresa, "2026-01-10", "Três casas",
               [p(BANCO, debito="0.105"), p(CAPITAL, credito="0.105")])
    assert r.status_code == 422
