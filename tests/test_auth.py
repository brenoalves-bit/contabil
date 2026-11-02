from tests.conftest import SENHA, criar_usuario, login


def test_login_e_me(client):
    criar_usuario("ana@fiber-finance.com.br")
    h = login(client, "ana@fiber-finance.com.br")
    r = client.get("/api/v1/auth/me", headers={"Authorization": h["Authorization"]})
    assert r.status_code == 200
    assert r.json()["email"] == "ana@fiber-finance.com.br"
    assert r.json()["admin_escritorio"] is False


def test_senha_errada_e_bloqueio(client):
    criar_usuario("ana@fiber-finance.com.br")
    for _ in range(5):
        r = client.post("/api/v1/auth/login", json={"email": "ana@fiber-finance.com.br", "senha": "errada-errada-1"})
        assert r.status_code == 401
    r = client.post("/api/v1/auth/login", json={"email": "ana@fiber-finance.com.br", "senha": SENHA})
    assert r.status_code == 401
    assert r.json()["code"] == "bloqueado"


def test_usuario_inexistente_mesma_resposta(client):
    r = client.post("/api/v1/auth/login", json={"email": "ninguem@fiber-finance.com.br", "senha": SENHA})
    assert r.status_code == 401
    assert r.json()["detail"] == "credenciais inválidas"


def test_refresh_rotaciona_e_detecta_reuso(client):
    criar_usuario("ana@fiber-finance.com.br")
    h = login(client, "ana@fiber-finance.com.br")
    r1 = client.post("/api/v1/auth/refresh", json={"refresh_token": h["_refresh"]})
    assert r1.status_code == 200
    novo = r1.json()["refresh_token"]
    # reuso do token antigo => revoga tudo
    r2 = client.post("/api/v1/auth/refresh", json={"refresh_token": h["_refresh"]})
    assert r2.status_code == 401
    r3 = client.post("/api/v1/auth/refresh", json={"refresh_token": novo})
    assert r3.status_code == 401


def test_sem_token(client):
    assert client.get("/api/v1/empresas").status_code == 401
    assert client.get("/api/v1/auth/me", headers={"Authorization": "Bearer lixo"}).status_code == 401


def test_nao_admin_nao_cria_usuario_nem_empresa(client):
    criar_usuario("ana@fiber-finance.com.br")
    h = {"Authorization": login(client, "ana@fiber-finance.com.br")["Authorization"]}
    r = client.post("/api/v1/usuarios", headers=h, json={"email": "x@fiber-finance.com.br", "nome": "X", "senha": SENHA})
    assert r.status_code == 403
    r = client.post("/api/v1/empresas", headers=h, json={
        "razao_social": "Z", "cnpj": "11222333000181", "regime_tributario": "SIMPLES"})
    assert r.status_code == 403


def test_cabecalhos_seguranca(client):
    r = client.get("/health")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["Cache-Control"] == "no-store"
