"""Gera XML de NF-e (layout 4.00) sintético, com chave de acesso válida, para testes."""
from decimal import Decimal

from app.services.fiscal.nfe_xml import dv_chave

FORNECEDOR = "34028316000103"
CLIENTE = "12345678000195"


def chave(cnpj_emit: str, numero: int, serie: int = 1, modelo: str = "55", aamm: str = "2603", cuf: str = "35",
          cnf: str = "12345678") -> str:
    base = f"{cuf}{aamm}{cnpj_emit}{modelo}{serie:03d}{numero:09d}1{cnf}"
    return base + str(dv_chave(base))


def item(n: int, cprod: str, xprod: str, cfop: str, qtd: str, vun: str, *, ncm: str = "22021000",
         icms: dict | None = None, csosn: str | None = None, ipi: dict | None = None,
         pis: dict | None = None, cofins: dict | None = None, vfrete: str = "0.00", vdesc: str = "0.00",
         issqn: dict | None = None) -> str:
    vprod = (Decimal(qtd) * Decimal(vun)).quantize(Decimal("0.01"))
    if csosn:
        icms_xml = f"<ICMS><ICMSSN102><orig>0</orig><CSOSN>{csosn}</CSOSN></ICMSSN102></ICMS>"
    elif icms:
        icms_xml = (f"<ICMS><ICMS00><orig>0</orig><CST>00</CST><modBC>3</modBC><vBC>{icms['vBC']}</vBC>"
                    f"<pICMS>{icms['pICMS']}</pICMS><vICMS>{icms['vICMS']}</vICMS></ICMS00></ICMS>")
    else:
        icms_xml = "<ICMS><ICMS40><orig>0</orig><CST>41</CST></ICMS40></ICMS>"
    ipi_xml = ""
    if ipi:
        ipi_xml = (f"<IPI><cEnq>999</cEnq><IPITrib><CST>50</CST><vBC>{ipi['vBC']}</vBC><pIPI>{ipi['pIPI']}</pIPI>"
                   f"<vIPI>{ipi['vIPI']}</vIPI></IPITrib></IPI>")
    pis_xml = (f"<PIS><PISAliq><CST>01</CST><vBC>{pis['vBC']}</vBC><pPIS>{pis['p']}</pPIS><vPIS>{pis['v']}</vPIS></PISAliq></PIS>"
               if pis else "<PIS><PISNT><CST>07</CST></PISNT></PIS>")
    cof_xml = (f"<COFINS><COFINSAliq><CST>01</CST><vBC>{cofins['vBC']}</vBC><pCOFINS>{cofins['p']}</pCOFINS>"
               f"<vCOFINS>{cofins['v']}</vCOFINS></COFINSAliq></COFINS>"
               if cofins else "<COFINS><COFINSNT><CST>07</CST></COFINSNT></COFINS>")
    iss_xml = ""
    if issqn:
        iss_xml = (f"<ISSQN><vBC>{issqn['vBC']}</vBC><vAliq>{issqn['vAliq']}</vAliq><vISSQN>{issqn['vISSQN']}</vISSQN>"
                   f"<cMunFG>3550308</cMunFG><cListServ>{issqn['cListServ']}</cListServ><indISS>1</indISS>"
                   f"<indIncentivo>2</indIncentivo></ISSQN>")
        icms_xml = ""
    frete = f"<vFrete>{vfrete}</vFrete>" if Decimal(vfrete) else ""
    desc = f"<vDesc>{vdesc}</vDesc>" if Decimal(vdesc) else ""
    return (f'<det nItem="{n}"><prod><cProd>{cprod}</cProd><cEAN>SEM GTIN</cEAN><xProd>{xprod}</xProd>'
            f"<NCM>{ncm}</NCM><CFOP>{cfop}</CFOP><uCom>UN</uCom><qCom>{qtd}</qCom><vUnCom>{vun}</vUnCom>"
            f"<vProd>{vprod}</vProd><cEANTrib>SEM GTIN</cEANTrib><uTrib>UN</uTrib><qTrib>{qtd}</qTrib>"
            f"<vUnTrib>{vun}</vUnTrib>{frete}{desc}<indTot>1</indTot></prod>"
            f"<imposto>{icms_xml}{ipi_xml}{pis_xml}{cof_xml}{iss_xml}</imposto></det>")


def nfe(*, emit: str, dest: str, numero: int, itens: list[str], totais: dict, tpnf: int = 1, serie: int = 1,
        emissao: str = "2026-03-10T10:00:00-03:00", protocolo: bool = True, nat: str = "VENDA",
        emit_nome: str = "Fornecedor Teste Ltda", dest_nome: str = "Destinatario Teste Ltda",
        ret: dict | None = None, modelo: str = "55") -> bytes:
    ch = chave(emit, numero, serie, modelo)
    t = {"vBC": "0.00", "vICMS": "0.00", "vICMSDeson": "0.00", "vFCP": "0.00", "vBCST": "0.00", "vST": "0.00",
         "vFCPST": "0.00", "vFCPSTRet": "0.00", "vProd": "0.00", "vFrete": "0.00", "vSeg": "0.00", "vDesc": "0.00",
         "vII": "0.00", "vIPI": "0.00", "vIPIDevol": "0.00", "vPIS": "0.00", "vCOFINS": "0.00", "vOutro": "0.00",
         "vNF": "0.00", **totais}
    tot = "".join(f"<{k}>{v}</{k}>" for k, v in t.items())
    ret_xml = ""
    if ret:
        ret_xml = "<retTrib>" + "".join(f"<{k}>{v}</{k}>" for k, v in ret.items()) + "</retTrib>"
    prot = ""
    if protocolo:
        prot = (f'<protNFe versao="4.00"><infProt><tpAmb>1</tpAmb><verAplic>SP</verAplic><chNFe>{ch}</chNFe>'
                f"<dhRecbto>{emissao}</dhRecbto><nProt>135260000000001</nProt><digVal>x</digVal><cStat>100</cStat>"
                f"<xMotivo>Autorizado o uso da NF-e</xMotivo></infProt></protNFe>")
    xml = (f'<?xml version="1.0" encoding="UTF-8"?><nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">'
           f'<NFe><infNFe versao="4.00" Id="NFe{ch}"><ide><cUF>35</cUF><cNF>12345678</cNF><natOp>{nat}</natOp>'
           f"<mod>{modelo}</mod><serie>{serie}</serie><nNF>{numero}</nNF><dhEmi>{emissao}</dhEmi><tpNF>{tpnf}</tpNF>"
           f"<idDest>1</idDest><cMunFG>3550308</cMunFG><tpImp>1</tpImp><tpEmis>1</tpEmis><cDV>{ch[-1]}</cDV>"
           f"<tpAmb>1</tpAmb><finNFe>1</finNFe><indFinal>0</indFinal><indPres>1</indPres><procEmi>0</procEmi>"
           f"<verProc>1.0</verProc></ide>"
           f"<emit><CNPJ>{emit}</CNPJ><xNome>{emit_nome}</xNome><xFant>Fornecedor</xFant><enderEmit><xLgr>Rua A</xLgr>"
           f"<nro>10</nro><xBairro>Centro</xBairro><cMun>3550308</cMun><xMun>Sao Paulo</xMun><UF>SP</UF><CEP>01001000</CEP>"
           f"<cPais>1058</cPais><xPais>Brasil</xPais></enderEmit><IE>123456789012</IE><CRT>3</CRT></emit>"
           f"<dest><CNPJ>{dest}</CNPJ><xNome>{dest_nome}</xNome><enderDest><xLgr>Av B</xLgr><nro>20</nro>"
           f"<xBairro>Centro</xBairro><cMun>3550308</cMun><xMun>Sao Paulo</xMun><UF>SP</UF><CEP>01002000</CEP>"
           f"<cPais>1058</cPais><xPais>Brasil</xPais></enderDest><indIEDest>1</indIEDest><IE>987654321098</IE></dest>"
           f"{''.join(itens)}<total><ICMSTot>{tot}</ICMSTot>{ret_xml}</total><transp><modFrete>9</modFrete></transp>"
           f"<infAdic><infCpl>Teste</infCpl></infAdic></infNFe></NFe>{prot}</nfeProc>")
    return xml.encode("utf-8")
