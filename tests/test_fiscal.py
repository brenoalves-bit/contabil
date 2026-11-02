from sqlalchemy import text

from app.core.db import engine
from tests.conftest import CNPJ_A, CNPJ_B, criar_empresa, criar_usuario, login
from tests.nfe_builder import CLIENTE, FORNECEDOR, item, nfe


def _url(e, *p):
    return "/api/v1/empresas/" + "/".join([e, *p])


def importar(client, headers, empresa, *xmls):
    files = [("arquivos", (f"nota{i}.xml", x, "application/xml")) for i, x in enumerate(xmls)]
    r = client.post(_url(empresa, "documentos-fiscais", "importar-xml"), headers=headers, files=files)
    assert r.status_code == 200, r.text
    return r.json()


def xml_compra_simples(numero=100):
    """Compra para revenda emitida por fornecedor (Simples: itens com CSOSN, sem destaque)."""
    return nfe(emit=FORNECEDOR, dest=CNPJ_A, numero=numero, nat="VENDA DE MERCADORIA",
               itens=[item(1, "F-001", "Refrigerante lata", "5102", "100.0000", "2.5000000000", csosn="102"),
                      item(2, "F-002", "Agua mineral", "5102", "50.0000", "1.0000000000", csosn="102", vfrete="10.00")],
               totais={"vProd": "300.00", "vFrete": "10.00", "vNF": "310.00"})


def xml_compra_real(numero=200):
    """Compra com ICMS 18%, IPI 10%, PIS 1,65%, COFINS 7,6% destacados."""
    return nfe(emit=FORNECEDOR, dest=CNPJ_A, numero=numero,
               itens=[item(1, "F-010", "Insumo X", "5102", "10.0000", "100.0000000000",
                           icms={"vBC": "1000.00", "pICMS": "18.00", "vICMS": "180.00"},
                           ipi={"vBC": "1000.00", "pIPI": "10.00", "vIPI": "100.00"},
                           pis={"vBC": "1000.00", "p": "1.65", "v": "16.50"},
                           cofins={"vBC": "1000.00", "p": "7.60", "v": "76.00"})],
               totais={"vBC": "1000.00", "vICMS": "180.00", "vProd": "1000.00", "vIPI": "100.00",
                       "vPIS": "16.50", "vCOFINS": "76.00", "vNF": "1100.00"})


def xml_venda(numero=300, empresa_cnpj=CNPJ_A):
    """Venda emitida pela própria empresa, com ICMS 18% e PIS/COFINS cumulativos."""
    return nfe(emit=empresa_cnpj, dest=CLIENTE, numero=numero, emit_nome="Minha Empresa", dest_nome="Cliente Bom",
               itens=[item(1, "P-001", "Produto A", "5102", "2.0000", "500.0000000000",
                           icms={"vBC": "1000.00", "pICMS": "18.00", "vICMS": "180.00"},
                           pis={"vBC": "1000.00", "p": "0.65", "v": "6.50"},
                           cofins={"vBC": "1000.00", "p": "3.00", "v": "30.00"})],
               totais={"vBC": "1000.00", "vICMS": "180.00", "vProd": "1000.00", "vPIS": "6.50",
                       "vCOFINS": "30.00", "vNF": "1000.00"})


# ---------------------------------------------------------------- importação
def test_importa_nfe_de_compra(client, admin, empresa):
    res = importar(client, admin, empresa, xml_compra_simples())
    assert res[0]["sucesso"], res
    doc = client.get(_url(empresa, "documentos-fiscais", res[0]["documento_id"]), headers=admin).json()
    assert doc["modelo"] == "NFE" and doc["tipo_operacao"] == "ENTRADA" and doc["status"] == "AUTORIZADO"
    assert doc["numero"] == 100 and doc["valor_total"] == "310.00" and doc["valor_frete"] == "10.00"
    assert doc["participante"]["cnpj_cpf"] == FORNECEDOR
    assert doc["protocolo"] == "135260000000001"
    assert len(doc["itens"]) == 2 and doc["itens"][0]["cfop"] == "1102" and doc["itens"][0]["cfop_documento"] == "5102"
    assert doc["itens"][0]["icms_cst"] == "102"
    assert doc["itens"][1]["valor_frete"] == "10.00"
    assert doc["itens_sem_produto"] == 2  # entrada: código é do fornecedor, sem de-para ainda
    # participante criado com endereço
    p = client.get(_url(empresa, "participantes"), headers=admin, params={"q": "Fornecedor"}).json()
    assert len(p) == 1 and p[0]["uf"] == "SP" and p[0]["indicador_ie"] == "CONTRIBUINTE"
    # duplicado
    res = importar(client, admin, empresa, xml_compra_simples())
    assert not res[0]["sucesso"] and "já importada" in res[0]["erro"]
    # XML baixável
    r = client.get(_url(empresa, "documentos-fiscais", doc["id"], "xml"), headers=admin)
    assert r.status_code == 200 and b"nfeProc" in r.content


def test_importa_venda_cria_produtos(client, admin, empresa):
    res = importar(client, admin, empresa, xml_venda())
    assert res[0]["sucesso"], res
    doc = client.get(_url(empresa, "documentos-fiscais", res[0]["documento_id"]), headers=admin).json()
    assert doc["tipo_operacao"] == "SAIDA" and doc["itens_sem_produto"] == 0
    assert doc["participante"]["cnpj_cpf"] == CLIENTE
    prods = client.get(_url(empresa, "produtos"), headers=admin).json()
    assert [p["codigo"] for p in prods] == ["P-001"] and prods[0]["ncm"] == "22021000"


def test_xml_de_terceiro_e_malformado(client, admin, empresa):
    terceiro = nfe(emit=FORNECEDOR, dest=CLIENTE, numero=1, itens=[item(1, "X", "X", "5102", "1", "1", csosn="102")],
                   totais={"vProd": "1.00", "vNF": "1.00"})
    res = importar(client, admin, empresa, terceiro, b"<isso nao e xml", b"<nfeProc></nfeProc>")
    assert [r["sucesso"] for r in res] == [False, False, False]
    assert "não pertence" in res[0]["erro"]
    # chave com dígito verificador errado
    ruim = xml_compra_simples()
    ch = ruim.split(b'Id="NFe')[1][:44]
    ruim = ruim.replace(ch, ch[:-1] + (b"0" if ch[-1:] != b"0" else b"1"))
    res = importar(client, admin, empresa, ruim)
    assert not res[0]["sucesso"] and "verificador" in res[0]["erro"]
    # XXE: entidade externa é bloqueada pelo defusedxml
    xxe = (b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
           b'<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe"><NFe><infNFe Id="NFe1">&xxe;</infNFe></NFe></nfeProc>')
    res = importar(client, admin, empresa, xxe)
    assert not res[0]["sucesso"]
    assert client.get(_url(empresa, "documentos-fiscais"), headers=admin).json()["total"] == 0


def test_leitura_nao_importa(client, admin, empresa):
    criar_usuario("leitor@fiber-finance.com.br")
    uid = next(u["id"] for u in client.get("/api/v1/usuarios", headers=admin).json() if u["email"].startswith("leitor"))
    client.put(_url(empresa, "usuarios"), headers=admin, json={"usuario_id": uid, "papel": "LEITURA"})
    hl = {"Authorization": login(client, "leitor@fiber-finance.com.br")["Authorization"]}
    r = client.post(_url(empresa, "documentos-fiscais", "importar-xml"), headers=hl,
                    files=[("arquivos", ("n.xml", xml_compra_simples(), "application/xml"))])
    assert r.status_code == 403


# ---------------------------------------------------------------- contabilização
def _padrao(client, admin, empresa):
    r = client.post(_url(empresa, "regras-contabilizacao", "padrao"), headers=admin)
    assert r.status_code == 201, r.text
    return r.json()


def _partidas(client, admin, empresa, lancamento_id):
    lanc = client.get(_url(empresa, "lancamentos", lancamento_id), headers=admin).json()
    return lanc, {(p["conta_codigo"], "D" if p["debito"] != "0.00" else "C"): p for p in lanc["partidas"]}


def test_compra_simples_contabiliza_pelo_total(client, admin, empresa):
    assert _padrao(client, admin, empresa)["regime"] == "SIMPLES"
    doc_id = importar(client, admin, empresa, xml_compra_simples())[0]["documento_id"]
    # prévia não grava nada
    pv = client.get(_url(empresa, "documentos-fiscais", doc_id, "previa-contabilizacao"), headers=admin).json()
    assert pv["total_debito"] == pv["total_credito"] == "310.00" and pv["grupos_sem_regra"] == []
    assert client.get(_url(empresa, "lancamentos"), headers=admin).json()["total"] == 0
    r = client.post(_url(empresa, "documentos-fiscais", doc_id, "contabilizar"), headers=admin)
    assert r.status_code == 200, r.text
    doc = r.json()
    assert doc["lancamento_id"] and doc["contabilizado_em"]
    lanc, p = _partidas(client, admin, empresa, doc["lancamento_id"])
    assert lanc["status"] == "EFETIVADO" and lanc["origem"] == "INTEGRACAO" and lanc["data"] == "2026-03-10"
    assert p[("2.1.01.001", "C")]["credito"] == "310.00"   # fornecedores pelo total
    assert p[("1.1.04.001", "D")]["debito"] == "310.00"    # estoque = residual (Simples não credita)
    assert "NF-e 100/1 - Fornecedor Teste Ltda" in lanc["historico"]
    # contabilizar de novo: não
    r = client.post(_url(empresa, "documentos-fiscais", doc_id, "contabilizar"), headers=admin)
    assert r.status_code == 422


def test_compra_lucro_real_credita_impostos(client, admin):
    emp = criar_empresa(client, admin, cnpj=CNPJ_A, nome="Real", regime="REAL")
    _padrao(client, admin, emp)
    doc_id = importar(client, admin, emp, xml_compra_real())[0]["documento_id"]
    r = client.post(_url(emp, "documentos-fiscais", doc_id, "contabilizar"), headers=admin)
    assert r.status_code == 200, r.text
    lanc, p = _partidas(client, admin, emp, r.json()["lancamento_id"])
    assert p[("2.1.01.001", "C")]["credito"] == "1100.00"  # fornecedores: produtos + IPI
    assert p[("1.1.03.001", "D")]["debito"] == "180.00"    # ICMS a recuperar
    assert p[("1.1.03.002", "D")]["debito"] == "16.50"     # PIS
    assert p[("1.1.03.003", "D")]["debito"] == "76.00"     # COFINS
    assert ("1.1.03.005", "D") not in p                    # IPI não credita em compra para revenda
    assert p[("1.1.04.001", "D")]["debito"] == "827.50"    # estoque líquido dos créditos (1100 - 180 - 16.5 - 76)
    assert lanc["total_debito"] == lanc["total_credito"] == "1100.00"


def test_venda_presumido_destaca_impostos(client, admin):
    emp = criar_empresa(client, admin, cnpj=CNPJ_A, nome="Presumido", regime="PRESUMIDO")
    _padrao(client, admin, emp)
    doc_id = importar(client, admin, emp, xml_venda())[0]["documento_id"]
    r = client.post(_url(emp, "documentos-fiscais", doc_id, "contabilizar"), headers=admin)
    assert r.status_code == 200, r.text
    lanc, p = _partidas(client, admin, emp, r.json()["lancamento_id"])
    assert p[("1.1.02.001", "D")]["debito"] == "1000.00"   # clientes
    assert p[("4.1.01.001", "C")]["credito"] == "1000.00"  # receita bruta (residual)
    assert p[("4.2.01.001", "D")]["debito"] == "180.00" and p[("2.1.03.001", "C")]["credito"] == "180.00"  # ICMS
    assert p[("4.2.01.003", "D")]["debito"] == "6.50" and p[("2.1.03.003", "C")]["credito"] == "6.50"      # PIS
    assert p[("4.2.01.004", "D")]["debito"] == "30.00" and p[("2.1.03.004", "C")]["credito"] == "30.00"    # COFINS
    assert lanc["total_debito"] == "1216.50"
    # DRE reflete: receita bruta 1000, deduções 216,50
    dre = client.get(_url(emp, "relatorios", "dre"), headers=admin, params={"inicio": "2026-03-01", "fim": "2026-03-31"}).json()
    assert dre["total_receitas"] == "783.50"


def test_sem_regra_e_remessa(client, admin, empresa):
    _padrao(client, admin, empresa)
    transf = nfe(emit=FORNECEDOR, dest=CNPJ_A, numero=400, itens=[item(1, "T", "Transferencia", "5152", "1", "10", csosn="102")],
                 totais={"vProd": "10.00", "vNF": "10.00"})
    doc_id = importar(client, admin, empresa, transf)[0]["documento_id"]
    r = client.post(_url(empresa, "documentos-fiscais", doc_id, "contabilizar"), headers=admin)
    assert r.status_code == 422 and r.json()["code"] == "sem_regra" and "1152" in r.json()["detail"]
    # contador corrige o CFOP do item para uso e consumo e contabiliza
    r = client.patch(_url(empresa, "documentos-fiscais", doc_id, "itens", "1"), headers=admin, json={"cfop": "1556"})
    assert r.status_code == 200 and r.json()["itens"][0]["cfop"] == "1556"
    r = client.post(_url(empresa, "documentos-fiscais", doc_id, "contabilizar"), headers=admin)
    assert r.status_code == 200 and r.json()["lancamento_id"]
    remessa = nfe(emit=FORNECEDOR, dest=CNPJ_A, numero=401, itens=[item(1, "R", "Remessa conserto", "5915", "1", "10", csosn="102")],
                  totais={"vProd": "10.00", "vNF": "10.00"})
    doc_id = importar(client, admin, empresa, remessa)[0]["documento_id"]
    r = client.post(_url(empresa, "documentos-fiscais", doc_id, "contabilizar"), headers=admin)
    assert r.status_code == 200 and r.json()["lancamento_id"] is None and r.json()["contabilizado_em"]


def test_cancelamento_estorna(client, admin, empresa):
    _padrao(client, admin, empresa)
    doc_id = importar(client, admin, empresa, xml_compra_simples())[0]["documento_id"]
    lid = client.post(_url(empresa, "documentos-fiscais", doc_id, "contabilizar"), headers=admin).json()["lancamento_id"]
    r = client.post(_url(empresa, "documentos-fiscais", doc_id, "cancelar"), headers=admin,
                    json={"motivo": "Nota emitida em duplicidade pelo fornecedor", "data_estorno": "2026-03-15"})
    assert r.status_code == 200 and r.json()["status"] == "CANCELADO"
    lanc = client.get(_url(empresa, "lancamentos", lid), headers=admin).json()
    assert lanc["status"] == "ESTORNADO"
    est = client.get(_url(empresa, "lancamentos", lanc["estornado_por_id"]), headers=admin).json()
    assert est["origem"] == "ESTORNO" and est["data"] == "2026-03-15"
    saldo = client.get(_url(empresa, "relatorios", "razao"), headers=admin,
                       params={"conta_codigo": "1.1.04.001", "inicio": "2026-03-01", "fim": "2026-03-31"}).json()
    assert saldo["saldo_final"] == "0.00"
    assert client.delete(_url(empresa, "documentos-fiscais", doc_id), headers=admin).status_code == 422
    assert client.post(_url(empresa, "documentos-fiscais", doc_id, "contabilizar"), headers=admin).status_code == 422


def test_recontabilizar_apos_mudar_regra(client, admin, empresa):
    _padrao(client, admin, empresa)
    doc_id = importar(client, admin, empresa, xml_compra_simples())[0]["documento_id"]
    lid1 = client.post(_url(empresa, "documentos-fiscais", doc_id, "contabilizar"), headers=admin).json()["lancamento_id"]
    regra = next(r for r in client.get(_url(empresa, "regras-contabilizacao"), headers=admin).json() if r["nome"] == "Compra para revenda")
    r = client.patch(_url(empresa, "regras-contabilizacao", regra["id"]), headers=admin, json={"linhas": [
        {"componente": "TOTAL", "lado": "C", "conta_codigo": "2.1.05.002"},
        {"componente": "FRETE", "lado": "D", "conta_codigo": "5.3.01.014"},
        {"componente": "RESIDUAL", "lado": "D", "conta_codigo": "1.1.04.001"}]})
    assert r.status_code == 200
    r = client.post(_url(empresa, "documentos-fiscais", doc_id, "contabilizar"), headers=admin, params={"recontabilizar": "true"})
    assert r.status_code == 200, r.text
    lid2 = r.json()["lancamento_id"]
    assert lid2 != lid1
    assert client.get(_url(empresa, "lancamentos", lid1), headers=admin).json()["status"] == "ESTORNADO"
    _, p = _partidas(client, admin, empresa, lid2)
    assert p[("2.1.05.002", "C")]["credito"] == "310.00" and p[("5.3.01.014", "D")]["debito"] == "10.00"
    assert p[("1.1.04.001", "D")]["debito"] == "300.00"


def test_nfse_manual_com_retencoes(client, admin):
    emp = criar_empresa(client, admin, cnpj=CNPJ_A, nome="Presumido", regime="PRESUMIDO")
    _padrao(client, admin, emp)
    cli = client.post(_url(emp, "participantes"), headers=admin, json={
        "tipo_pessoa": "PJ", "cnpj_cpf": "12.345.678/0001-95", "razao_social": "Tomador SA"}).json()
    r = client.post(_url(emp, "documentos-fiscais"), headers=admin, json={
        "modelo": "NFSE", "tipo_operacao": "SAIDA", "numero": 77, "serie": "A", "data_emissao": "2026-04-05",
        "participante_id": cli["id"], "valor_irrf_retido": "150.00", "valor_iss_retido": "500.00",
        "itens": [{"descricao": "Consultoria contábil", "codigo_servico": "17.19", "valor_bruto": "10000.00",
                   "iss_base": "10000.00", "iss_aliquota": "5.00", "iss_valor": "500.00"}]})
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["valor_servicos"] == "10000.00" and doc["valor_total"] == "10000.00"
    r = client.post(_url(emp, "documentos-fiscais", doc["id"], "contabilizar"), headers=admin)
    assert r.status_code == 200, r.text
    lanc, p = _partidas(client, admin, emp, r.json()["lancamento_id"])
    assert p[("4.1.01.002", "C")]["credito"] == "10000.00"   # receita de serviços
    assert p[("4.2.01.002", "D")]["debito"] == "500.00"      # ISS retido como dedução (não há ISS próprio)
    assert ("2.1.03.002", "C") not in p                      # nada a recolher: ISS foi todo retido
    assert p[("1.1.03.004", "D")]["debito"] == "150.00"      # IRRF a recuperar
    assert p[("1.1.02.001", "D")]["debito"] == "9350.00"     # clientes pelo líquido
    assert lanc["total_debito"] == lanc["total_credito"] == "10000.00"
    # duplicidade número/série/participante
    r = client.post(_url(emp, "documentos-fiscais"), headers=admin, json={
        "modelo": "NFSE", "tipo_operacao": "SAIDA", "numero": 77, "serie": "A", "data_emissao": "2026-04-05",
        "participante_id": cli["id"], "itens": [{"descricao": "x", "valor_bruto": "1.00"}]})
    assert r.status_code == 409


def test_de_para_de_produto(client, admin, empresa):
    doc_id = importar(client, admin, empresa, xml_compra_simples())[0]["documento_id"]
    client.post(_url(empresa, "produtos"), headers=admin, json={"codigo": "REFRI-LATA", "descricao": "Refrigerante lata 350ml", "ncm": "22021000"})
    r = client.patch(_url(empresa, "documentos-fiscais", doc_id, "itens", "1"), headers=admin,
                     json={"produto_codigo": "REFRI-LATA"})
    assert r.status_code == 200 and r.json()["itens_sem_produto"] == 1
    # próxima nota do mesmo fornecedor com o mesmo código já vem mapeada
    doc2 = importar(client, admin, empresa, xml_compra_simples(numero=101))[0]["documento_id"]
    d2 = client.get(_url(empresa, "documentos-fiscais", doc2), headers=admin).json()
    assert d2["itens"][0]["produto_id"] is not None and d2["itens_sem_produto"] == 1


def test_resumo_por_cfop_e_filtros(client, admin, empresa):
    importar(client, admin, empresa, xml_compra_simples(), xml_compra_real(), xml_venda())
    res = client.get(_url(empresa, "documentos-fiscais", "resumo"), headers=admin,
                     params={"inicio": "2026-03-01", "fim": "2026-03-31"}).json()
    assert res["total_entradas"] == "1410.00" and res["total_saidas"] == "1000.00"
    ent = next(x for x in res["linhas"] if x["tipo_operacao"] == "ENTRADA" and x["cfop"] == "1102")
    assert ent["documentos"] == 2 and ent["valor_bruto"] == "1300.00" and ent["icms_valor"] == "180.00" and ent["ipi_valor"] == "100.00"
    r = client.get(_url(empresa, "documentos-fiscais"), headers=admin, params={"tipo_operacao": "SAIDA"}).json()
    assert r["total"] == 1 and r["items"][0]["valor_total"] == "1000.00"
    r = client.get(_url(empresa, "documentos-fiscais"), headers=admin, params={"contabilizado": "false"}).json()
    assert r["total"] == 3


def test_regra_invalida(client, admin, empresa):
    r = client.post(_url(empresa, "regras-contabilizacao"), headers=admin, json={
        "nome": "Errada", "cfops": ["5102"], "linhas": [{"componente": "TOTAL", "lado": "C", "conta_codigo": "1.1.01"}]})
    assert r.status_code == 422  # menos de duas linhas
    r = client.post(_url(empresa, "regras-contabilizacao"), headers=admin, json={
        "nome": "Errada", "cfops": ["5102"], "linhas": [{"componente": "TOTAL", "lado": "C", "conta_codigo": "1.1.01"},
                                                        {"componente": "RESIDUAL", "lado": "D", "conta_codigo": "1.1.04.001"}]})
    assert r.status_code == 422 and "sintética" in r.json()["detail"]
    r = client.post(_url(empresa, "regras-contabilizacao", "padrao"), headers=admin)
    assert r.status_code == 201
    assert client.post(_url(empresa, "regras-contabilizacao", "padrao"), headers=admin).status_code == 422


def test_rls_tabelas_fiscais(client, admin, empresa):
    importar(client, admin, empresa, xml_compra_simples())
    criar_empresa(client, admin, cnpj=CNPJ_B, nome="Empresa B")
    with engine.connect() as conn:
        for t in ("documento_fiscal", "documento_fiscal_item", "participante", "produto"):
            assert conn.execute(text(f"SELECT count(*) FROM {t}")).scalar() == 0
    with engine.begin() as conn:
        conn.execute(text("SELECT set_config('app.empresa_id', :e, true)"), {"e": empresa})
        assert conn.execute(text("SELECT count(*) FROM documento_fiscal")).scalar() == 1
