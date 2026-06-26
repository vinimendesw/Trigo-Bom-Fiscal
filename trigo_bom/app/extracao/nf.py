import json
import re
import pdfplumber
import fitz  # PyMuPDF


def _extrair_texto(caminho: str) -> str:
    """Tenta pdfplumber; cai para PyMuPDF se o resultado vier vazio."""
    try:
        with pdfplumber.open(caminho) as pdf:
            texto = "\n".join(p.extract_text() or "" for p in pdf.pages).strip()
        if texto:
            return texto
    except Exception:
        pass

    doc = fitz.open(caminho)
    texto = "\n".join(p.get_text() for p in doc).strip()
    doc.close()
    return texto


def _primeiro_match(texto: str, *padroes: str) -> str:
    for p in padroes:
        m = re.search(p, texto, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return ""


def _limpar_valor(s: str) -> float | None:
    s = re.sub(r"[^\d,\.]", "", s)
    # Formato BR: 1.234,56 → 1234.56
    if re.search(r"\d\.\d{3},\d", s):
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def extrair_nf(caminho: str) -> str:
    resultado = {
        "numero": "",
        "fornecedor": "",
        "data_emissao": "",
        "valor": None,
        "arquivo_pdf": caminho,
    }

    try:
        texto = _extrair_texto(caminho)

        resultado["numero"] = _primeiro_match(
            texto,
            r"n[uú]mero\s*(?:da\s*)?(?:nota|NF)[:\s]*(\d+)",
            r"NF[- ]*e?\s*[nN][oO]?\s*[:\s]*(\d+)",
            r"nota\s*fiscal\s*n[oº°]?\s*[:\s]*(\d+)",
            r"\bNF\b[^\d]*(\d{4,})",
        )

        resultado["fornecedor"] = _primeiro_match(
            texto,
            r"(?:raz[ãa]o\s*social|emitente|fornecedor)[:\s]+([^\n]{3,60})",
            r"(?:nome|empresa)[:\s]+([A-ZÁÀÂÃÉÊÍÓÔÕÚ][^\n]{2,50})",
        )

        resultado["data_emissao"] = _primeiro_match(
            texto,
            r"data\s*(?:de\s*)?emiss[aã]o[:\s]*(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})",
            r"emiss[aã]o[:\s]*(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})",
            r"(?<!\w)(\d{2}[/\-\.]\d{2}[/\-\.]\d{4})(?!\w)",
        )

        valor_str = _primeiro_match(
            texto,
            r"valor\s*(?:total|l[íi]quido|da\s*nota)[:\s]*([\d\.]+,\d{2})",
            r"total\s*(?:geral|da\s*nota|a\s*pagar)[:\s]*([\d\.]+,\d{2})",
            r"R\$\s*([\d\.]+,\d{2})",
        )
        if valor_str:
            resultado["valor"] = _limpar_valor(valor_str)

        resultado["_texto_bruto"] = texto

    except Exception as e:
        resultado["_erro"] = str(e)

    return json.dumps(resultado, ensure_ascii=False)
