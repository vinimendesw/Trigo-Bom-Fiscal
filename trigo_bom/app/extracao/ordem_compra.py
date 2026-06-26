import json
import re
import pdfplumber
import fitz


def _extrair_texto_e_tabelas(caminho: str):
    """Retorna (texto_completo, lista_de_tabelas). Prefere pdfplumber."""
    try:
        with pdfplumber.open(caminho) as pdf:
            texto = "\n".join(p.extract_text() or "" for p in pdf.pages).strip()
            tabelas = []
            for p in pdf.pages:
                t = p.extract_table()
                if t:
                    tabelas.append(t)
        if texto:
            return texto, tabelas
    except Exception:
        pass

    doc = fitz.open(caminho)
    texto = "\n".join(p.get_text() for p in doc).strip()
    doc.close()
    return texto, []


def _primeiro_match(texto: str, *padroes: str) -> str:
    for p in padroes:
        m = re.search(p, texto, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return ""


def _limpar_valor(s: str) -> float | None:
    s = re.sub(r"[^\d,\.]", "", s)
    if re.search(r"\d\.\d{3},\d", s):
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _extrair_itens_de_tabela(tabelas: list) -> list:
    """Tenta identificar a tabela de itens e retorna lista de dicts."""
    itens = []
    for tabela in tabelas:
        if not tabela or len(tabela) < 2:
            continue
        cabecalho = [str(c or "").lower() for c in tabela[0]]
        # verifica se parece uma tabela de itens
        tem_desc = any("descri" in c or "item" in c or "produto" in c for c in cabecalho)
        tem_qtd = any("qtd" in c or "quant" in c for c in cabecalho)
        if not (tem_desc and tem_qtd):
            continue

        idx_desc = next((i for i, c in enumerate(cabecalho) if "descri" in c or "produto" in c or "item" in c), None)
        idx_qtd = next((i for i, c in enumerate(cabecalho) if "qtd" in c or "quant" in c), None)
        idx_vunit = next((i for i, c in enumerate(cabecalho) if "unit" in c), None)
        idx_vtotal = next((i for i, c in enumerate(cabecalho) if "total" in c), None)

        for linha in tabela[1:]:
            if not linha or all(not c for c in linha):
                continue
            desc = str(linha[idx_desc] or "").strip() if idx_desc is not None else ""
            if not desc or desc.lower() in ("item", "descrição", "produto"):
                continue
            qtd = _limpar_valor(str(linha[idx_qtd] or "")) if idx_qtd is not None else None
            vunit = _limpar_valor(str(linha[idx_vunit] or "")) if idx_vunit is not None else None
            vtotal = _limpar_valor(str(linha[idx_vtotal] or "")) if idx_vtotal is not None else None
            if vtotal is None and qtd and vunit:
                vtotal = round(qtd * vunit, 2)
            itens.append({"descricao": desc, "quantidade": qtd, "valor_unitario": vunit, "valor_total": vtotal})

    return itens


def _extrair_itens_de_texto(texto: str) -> list:
    """Fallback: tenta extrair itens por regex linha a linha."""
    itens = []
    # Padrão: número + descrição + quantidade + valor unitário + valor total
    padrao = re.compile(
        r"(\d+)\s+(.+?)\s+([\d]+[.,]?\d*)\s+([\d\.]+,\d{2})\s+([\d\.]+,\d{2})",
        re.IGNORECASE,
    )
    for m in padrao.finditer(texto):
        desc = m.group(2).strip()
        if len(desc) < 3:
            continue
        itens.append({
            "descricao": desc,
            "quantidade": _limpar_valor(m.group(3)),
            "valor_unitario": _limpar_valor(m.group(4)),
            "valor_total": _limpar_valor(m.group(5)),
        })
    return itens


def extrair_ordem_compra(caminho: str) -> str:
    resultado = {
        "numero": "",
        "fornecedor": "",
        "data_emissao": "",
        "data_entrega_prevista": "",
        "itens": [],
        "arquivo_pdf": caminho,
    }

    try:
        texto, tabelas = _extrair_texto_e_tabelas(caminho)

        resultado["numero"] = _primeiro_match(
            texto,
            r"ordem\s*de\s*compra\s*n[oº°]?\s*[:\s]*(\d+)",
            r"OC\s*[nN][oº°]?\s*[:\s]*(\d+)",
            r"\bOC\b[^\d]*(\d{4,})",
        )

        resultado["fornecedor"] = _primeiro_match(
            texto,
            r"(?:fornecedor|empresa|raz[ãa]o\s*social)[:\s]+([^\n]{3,60})",
            r"(?:ao\s+fornecedor)[:\s]+([^\n]{3,60})",
        )

        resultado["data_emissao"] = _primeiro_match(
            texto,
            r"data\s*(?:de\s*)?emiss[aã]o[:\s]*(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})",
            r"data[:\s]*(\d{2}[/\-\.]\d{2}[/\-\.]\d{4})",
        )

        resultado["data_entrega_prevista"] = _primeiro_match(
            texto,
            r"(?:prazo|data)\s*(?:de\s*)?entrega[:\s]*(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})",
            r"entrega\s*(?:prevista|at[eé])[:\s]*(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})",
        )

        itens = _extrair_itens_de_tabela(tabelas)
        if not itens:
            itens = _extrair_itens_de_texto(texto)
        resultado["itens"] = itens
        resultado["_texto_bruto"] = texto

    except Exception as e:
        resultado["_erro"] = str(e)

    return json.dumps(resultado, ensure_ascii=False)
