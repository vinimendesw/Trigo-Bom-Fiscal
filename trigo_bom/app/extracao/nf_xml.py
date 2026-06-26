"""
Extração de NF-e (modelo 55) a partir do XML padronizado SEFAZ.
Aceita tanto <NFe> como raiz quanto <nfeProc><NFe>...
Namespace: http://www.portalfiscal.inf.br/nfe
"""

import json
import xml.etree.ElementTree as ET

NS = "http://www.portalfiscal.inf.br/nfe"
_NS = f"{{{NS}}}"


def _tag(nome: str) -> str:
    return f"{_NS}{nome}"


def _txt(el, *caminho: str) -> str:
    """Navega pelo caminho de tags e retorna o texto do último elemento."""
    atual = el
    for parte in caminho:
        if atual is None:
            return ""
        atual = atual.find(_tag(parte))
    return (atual.text or "").strip() if atual is not None else ""


def _formatar_data(dh: str) -> str:
    """Converte 'AAAA-MM-DDThh:mm:ss-hh:mm' para 'AAAA-MM-DD'."""
    return dh[:10] if dh else ""


def extrair_nf_xml(caminho: str) -> str:
    resultado = {
        "numero": "",
        "fornecedor": "",
        "data_emissao": "",
        "valor": None,
        "itens": [],
        "arquivo_xml": caminho,
    }

    try:
        tree = ET.parse(caminho)
        root = tree.getroot()

        # Aceita <NFe> como raiz ou <nfeProc><NFe>
        if root.tag == _tag("nfeProc"):
            nfe = root.find(_tag("NFe"))
        elif root.tag == _tag("NFe"):
            nfe = root
        else:
            # Tenta encontrar NFe em qualquer profundidade
            nfe = root.find(f".//{_tag('NFe')}")

        if nfe is None:
            resultado["_erro"] = "Elemento <NFe> não encontrado no XML."
            return json.dumps(resultado, ensure_ascii=False)

        inf = nfe.find(_tag("infNFe"))
        if inf is None:
            resultado["_erro"] = "Elemento <infNFe> não encontrado."
            return json.dumps(resultado, ensure_ascii=False)

        # ── Cabeçalho ──────────────────────────────────────────────────────
        ide  = inf.find(_tag("ide"))
        emit = inf.find(_tag("emit"))

        resultado["numero"]      = _txt(ide, "nNF") if ide is not None else ""
        resultado["fornecedor"]  = _txt(emit, "xNome") if emit is not None else ""
        resultado["data_emissao"]= _formatar_data(_txt(ide, "dhEmi") if ide is not None else "")

        total   = inf.find(_tag("total"))
        icms    = total.find(_tag("ICMSTot")) if total is not None else None
        vNF_str = _txt(icms, "vNF") if icms is not None else ""
        try:
            resultado["valor"] = float(vNF_str) if vNF_str else None
        except ValueError:
            resultado["valor"] = None

        # ── Itens ──────────────────────────────────────────────────────────
        for det in inf.findall(_tag("det")):
            prod = det.find(_tag("prod"))
            if prod is None:
                continue

            def pf(tag):  # parse float safe
                try:
                    return float(_txt(prod, tag))
                except (ValueError, TypeError):
                    return None

            resultado["itens"].append({
                "descricao":     _txt(prod, "xProd"),
                "quantidade":    pf("qCom"),
                "valor_unitario":pf("vUnCom"),
                "valor_total":   pf("vProd"),
                "ncm":           _txt(prod, "NCM"),
                "cfop":          _txt(prod, "CFOP"),
            })

    except ET.ParseError as e:
        resultado["_erro"] = f"XML inválido: {e}"
    except Exception as e:
        resultado["_erro"] = str(e)

    return json.dumps(resultado, ensure_ascii=False)
