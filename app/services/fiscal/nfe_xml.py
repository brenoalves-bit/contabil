"""Leitura do XML da NF-e / NFC-e (layout 4.00) para a estrutura interna.

Parse com defusedxml: XML vindo de terceiros é entrada hostil (XXE, bombas de entidade).
Os namespaces são removidos para simplificar os caminhos.
"""
import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from defusedxml import ElementTree as DET

from app.core.errors import DomainError

NS = "http://www.portalfiscal.inf.br/nfe"
D0 = Decimal(0)


class XmlInvalido(DomainError):
    status_code = 422
    code = "xml_invalido"


@dataclass
class ItemNFe:
    numero: int
    codigo: str | None
    ean: str | None
    descricao: str
    ncm: str | None
    cest: str | None
    cfop: str | None
    unidade: str | None
    quantidade: Decimal
    valor_unitario: Decimal
    valor_bruto: Decimal
    valor_frete: Decimal
    valor_seguro: Decimal
    valor_desconto: Decimal
    valor_outras: Decimal
    compoe_total: bool
    icms_origem: int | None = None
    icms_cst: str | None = None
    icms_base: Decimal = D0
    icms_aliquota: Decimal = D0
    icms_valor: Decimal = D0
    icms_st_base: Decimal = D0
    icms_st_valor: Decimal = D0
    ipi_cst: str | None = None
    ipi_base: Decimal = D0
    ipi_aliquota: Decimal = D0
    ipi_valor: Decimal = D0
    pis_cst: str | None = None
    pis_base: Decimal = D0
    pis_aliquota: Decimal = D0
    pis_valor: Decimal = D0
    cofins_cst: str | None = None
    cofins_base: Decimal = D0
    cofins_aliquota: Decimal = D0
    cofins_valor: Decimal = D0
    codigo_servico: str | None = None
    iss_base: Decimal = D0
    iss_aliquota: Decimal = D0
    iss_valor: Decimal = D0


@dataclass
class NFeLida:
    chave: str
    modelo: str  # '55' ou '65'
    serie: str
    numero: int
    data_emissao: date
    data_saida_entrada: date | None
    tipo_nf: int  # 0 entrada, 1 saída (do ponto de vista do emitente)
    natureza_operacao: str
    finalidade: int | None
    emitente: dict
    destinatario: dict | None
    itens: list[ItemNFe]
    totais: dict
    retencoes: dict
    informacoes_complementares: str | None
    protocolo: str | None
    codigo_status: str | None
    xml_hash: str
    xml: str
    avisos: list[str] = field(default_factory=list)


def _strip_ns(el) -> None:
    for e in el.iter():
        if isinstance(e.tag, str) and "}" in e.tag:
            e.tag = e.tag.split("}", 1)[1]


def _t(el, path: str, default=None):
    if el is None:
        return default
    found = el.find(path)
    if found is None or found.text is None:
        return default
    return found.text.strip()


def _d(el, path: str) -> Decimal:
    v = _t(el, path)
    try:
        return Decimal(v) if v not in (None, "") else D0
    except Exception as exc:
        raise XmlInvalido(f"valor numérico inválido em {path}: {v!r}") from exc


def _data(v: str | None) -> date | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(v).date()
    except ValueError:
        return date.fromisoformat(v[:10])


def dv_chave(chave43: str) -> int:
    pesos = [2, 3, 4, 5, 6, 7, 8, 9]
    soma = 0
    for i, ch in enumerate(reversed(chave43)):
        soma += int(ch) * pesos[i % 8]
    resto = soma % 11
    return 0 if resto < 2 else 11 - resto


def validar_chave(chave: str) -> None:
    if len(chave) != 44 or not chave.isdigit():
        raise XmlInvalido("chave de acesso deve ter 44 dígitos")
    if dv_chave(chave[:43]) != int(chave[43]):
        raise XmlInvalido("dígito verificador da chave de acesso inválido")


def _endereco(el) -> dict:
    if el is None:
        return {}
    cep = _t(el, "CEP")
    return {
        "logradouro": _t(el, "xLgr"), "numero": _t(el, "nro"), "complemento": _t(el, "xCpl"),
        "bairro": _t(el, "xBairro"), "codigo_municipio": _t(el, "cMun"), "municipio": _t(el, "xMun"),
        "uf": _t(el, "UF"), "cep": cep if cep and len(cep) == 8 else None,
        "pais": _t(el, "xPais") or "Brasil", "telefone": _t(el, "fone"),
    }


def _pessoa(el, tag_end: str) -> dict | None:
    if el is None:
        return None
    cnpj = _t(el, "CNPJ")
    cpf = _t(el, "CPF")
    estrangeiro = _t(el, "idEstrangeiro")
    doc = cnpj or cpf or estrangeiro
    if not doc:
        return None
    ind = _t(el, "indIEDest")
    indicador = {"1": "CONTRIBUINTE", "2": "ISENTO", "9": "NAO_CONTRIBUINTE"}.get(ind or "", None)
    ie = _t(el, "IE")
    if indicador is None:
        indicador = "CONTRIBUINTE" if ie and ie.upper() != "ISENTO" else ("ISENTO" if ie else "NAO_CONTRIBUINTE")
    return {
        "cnpj_cpf": doc,
        "estrangeiro": bool(estrangeiro) and not (cnpj or cpf),
        "razao_social": _t(el, "xNome") or doc,
        "nome_fantasia": _t(el, "xFant"),
        "ie": None if (ie or "").upper() == "ISENTO" else ie,
        "im": _t(el, "IM"),
        "indicador_ie": indicador,
        "email": _t(el, "email"),
        **_endereco(el.find(tag_end)),
    }


def _icms(imp) -> dict:
    icms = imp.find("ICMS") if imp is not None else None
    if icms is None or len(icms) == 0:
        return {}
    grupo = icms[0]  # ICMS00, ICMS10, ..., ICMSSN101, ...
    cst = _t(grupo, "CST") or _t(grupo, "CSOSN")
    orig = _t(grupo, "orig")
    return {
        "icms_origem": int(orig) if orig and orig.isdigit() else None,
        "icms_cst": cst,
        "icms_base": _d(grupo, "vBC"),
        "icms_aliquota": _d(grupo, "pICMS"),
        "icms_valor": _d(grupo, "vICMS"),
        "icms_st_base": _d(grupo, "vBCST"),
        "icms_st_valor": _d(grupo, "vICMSST"),
    }


def _ipi(imp) -> dict:
    ipi = imp.find("IPI") if imp is not None else None
    if ipi is None:
        return {}
    trib = ipi.find("IPITrib")
    nt = ipi.find("IPINT")
    if trib is not None:
        return {"ipi_cst": _t(trib, "CST"), "ipi_base": _d(trib, "vBC"), "ipi_aliquota": _d(trib, "pIPI"),
                "ipi_valor": _d(trib, "vIPI")}
    if nt is not None:
        return {"ipi_cst": _t(nt, "CST")}
    return {}


def _pis_cofins(imp, nome: str) -> dict:
    grp = imp.find(nome) if imp is not None else None
    if grp is None or len(grp) == 0:
        return {}
    sub = grp[0]  # PISAliq, PISQtde, PISNT, PISOutr
    chave = nome.lower()
    return {
        f"{chave}_cst": _t(sub, "CST"),
        f"{chave}_base": _d(sub, "vBC"),
        f"{chave}_aliquota": _d(sub, f"p{nome}"),
        f"{chave}_valor": _d(sub, f"v{nome}"),
    }


def _issqn(imp) -> dict:
    iss = imp.find("ISSQN") if imp is not None else None
    if iss is None:
        return {}
    return {"codigo_servico": _t(iss, "cListServ"), "iss_base": _d(iss, "vBC"),
            "iss_aliquota": _d(iss, "vAliq"), "iss_valor": _d(iss, "vISSQN")}


def ler_nfe(conteudo: bytes) -> NFeLida:
    if len(conteudo) > 5 * 1024 * 1024:
        raise XmlInvalido("XML maior que 5 MB")
    try:
        root = DET.fromstring(conteudo)
    except Exception as exc:
        raise XmlInvalido(f"XML malformado: {exc}") from exc
    _strip_ns(root)

    if root.tag == "nfeProc":
        nfe = root.find("NFe")
        prot = root.find("protNFe/infProt")
    elif root.tag == "NFe":
        nfe, prot = root, None
    else:
        raise XmlInvalido(f"raiz {root.tag!r} não é NF-e (esperado nfeProc ou NFe)")
    inf = nfe.find("infNFe") if nfe is not None else None
    if inf is None:
        raise XmlInvalido("infNFe ausente")
    chave = (inf.get("Id") or "").replace("NFe", "")
    validar_chave(chave)

    ide = inf.find("ide")
    modelo = _t(ide, "mod")
    if modelo not in ("55", "65"):
        raise XmlInvalido(f"modelo {modelo!r} não suportado (55 ou 65)")
    if chave[20:22] != modelo:
        raise XmlInvalido("modelo do XML não confere com a chave de acesso")

    emit = _pessoa(inf.find("emit"), "enderEmit")
    if emit is None:
        raise XmlInvalido("emitente sem CNPJ/CPF")
    if chave[6:20] != emit["cnpj_cpf"].zfill(14):
        raise XmlInvalido("CNPJ do emitente não confere com a chave de acesso")
    dest = _pessoa(inf.find("dest"), "enderDest")

    itens: list[ItemNFe] = []
    for det in inf.findall("det"):
        prod = det.find("prod")
        imp = det.find("imposto")
        n = int(det.get("nItem") or (len(itens) + 1))
        item = ItemNFe(
            numero=n,
            codigo=_t(prod, "cProd"),
            ean=None if _t(prod, "cEAN") in (None, "SEM GTIN") else _t(prod, "cEAN"),
            descricao=_t(prod, "xProd") or f"item {n}",
            ncm=_t(prod, "NCM"),
            cest=_t(prod, "CEST"),
            cfop=_t(prod, "CFOP"),
            unidade=_t(prod, "uCom"),
            quantidade=_d(prod, "qCom") or Decimal(1),
            valor_unitario=_d(prod, "vUnCom"),
            valor_bruto=_d(prod, "vProd"),
            valor_frete=_d(prod, "vFrete"),
            valor_seguro=_d(prod, "vSeg"),
            valor_desconto=_d(prod, "vDesc"),
            valor_outras=_d(prod, "vOutro"),
            compoe_total=(_t(prod, "indTot") or "1") == "1",
        )
        for k, v in {**_icms(imp), **_ipi(imp), **_pis_cofins(imp, "PIS"), **_pis_cofins(imp, "COFINS"),
                     **_issqn(imp)}.items():
            setattr(item, k, v)
        itens.append(item)
    if not itens:
        raise XmlInvalido("NF-e sem itens")

    tot = inf.find("total/ICMSTot")
    iss_tot = inf.find("total/ISSQNtot")
    ret = inf.find("total/retTrib")
    totais = {
        "valor_produtos": _d(tot, "vProd"), "valor_frete": _d(tot, "vFrete"), "valor_seguro": _d(tot, "vSeg"),
        "valor_desconto": _d(tot, "vDesc"), "valor_outras": _d(tot, "vOutro"), "valor_ipi": _d(tot, "vIPI"),
        "valor_icms": _d(tot, "vICMS"), "valor_icms_st": _d(tot, "vST"),
        "valor_pis": _d(tot, "vPIS") + _d(iss_tot, "vPIS"), "valor_cofins": _d(tot, "vCOFINS") + _d(iss_tot, "vCOFINS"),
        "valor_servicos": _d(iss_tot, "vServ"), "valor_iss": _d(iss_tot, "vISS"),
        "valor_total": _d(tot, "vNF"),
    }
    retencoes = {
        "valor_pis_retido": _d(ret, "vRetPIS"), "valor_cofins_retido": _d(ret, "vRetCOFINS"),
        "valor_csll_retida": _d(ret, "vRetCSLL"), "valor_irrf_retido": _d(ret, "vIRRF"),
        "valor_inss_retido": _d(ret, "vRetPrev"), "valor_iss_retido": _d(iss_tot, "vISSRet"),
    }
    fin = _t(ide, "finNFe")
    return NFeLida(
        chave=chave, modelo=modelo, serie=_t(ide, "serie") or "1", numero=int(_t(ide, "nNF") or 0),
        data_emissao=_data(_t(ide, "dhEmi") or _t(ide, "dEmi")),
        data_saida_entrada=_data(_t(ide, "dhSaiEnt") or _t(ide, "dSaiEnt")),
        tipo_nf=int(_t(ide, "tpNF") or 1), natureza_operacao=_t(ide, "natOp") or "",
        finalidade=int(fin) if fin and fin.isdigit() else None,
        emitente=emit, destinatario=dest, itens=itens, totais=totais, retencoes=retencoes,
        informacoes_complementares=_t(inf, "infAdic/infCpl"),
        protocolo=_t(prot, "nProt"), codigo_status=_t(prot, "cStat"),
        xml_hash=hashlib.sha256(conteudo).hexdigest(), xml=conteudo.decode("utf-8", errors="replace"),
    )
