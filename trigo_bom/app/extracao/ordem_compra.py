import json
import re
import pdfplumber
import fitz

from extracao.util import limpar_valor, primeiro_match

# Aliases internos: o restante do módulo segue usando os nomes privados, agora
# delegando às funções compartilhadas de extracao.util (antes duplicadas aqui).
_limpar_valor = limpar_valor
_primeiro_match = primeiro_match


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


def _extrair_nome_produto(descricao_completa: str, limite: int = 70) -> str:
    """Reduz a descrição completa do produto (que no PDF vem junto com a
    especificação técnica detalhada) só ao nome do item.

    Corta no primeiro "." ou ":" encontrado dentro dos primeiros `limite`
    caracteres — esse separador costuma marcar o fim do nome e o início da
    especificação ("DIFUSOR DE AMBIENTES 240M. O dispositivo deve ser..." /
    "Papel Higiênico: Folha Dupla..."). Quando não há separador nesse trecho,
    trunca no limite mesmo assim. O restante do texto (especificação) é
    descartado — não é mantido em nenhum campo.
    """
    if not descricao_completa:
        return descricao_completa
    trecho = descricao_completa[:limite]
    posicoes = [p for p in (trecho.find("."), trecho.find(":")) if p != -1]
    if posicoes:
        return descricao_completa[: min(posicoes)].strip()

    cortado = descricao_completa[:limite]
    # evita cortar no meio de uma palavra: recua até o último espaço, desde
    # que isso não descarte uma fração grande demais do limite
    ultimo_espaco = cortado.rfind(" ")
    if ultimo_espaco > limite * 0.6:
        cortado = cortado[:ultimo_espaco]
    return cortado.strip().rstrip(",;-–—")


def _extrair_itens_de_tabela(tabelas: list) -> list:
    """Tenta identificar a tabela de itens e retorna lista de dicts.

    Algumas ordens de compra (ex.: layout da Prefeitura de Goianápolis) têm
    descrição de produto longa, que pode ocupar várias linhas e até
    atravessar uma quebra de página. Quando isso acontece, o pdfplumber gera
    uma linha extra na tabela da página seguinte contendo só a continuação
    do texto, sem número de item nem valores — essa linha é mesclada à
    descrição do item anterior em vez de virar um item novo (fantasma).

    A descrição completa (nome + especificação técnica) é reduzida ao nome
    do produto só depois de toda a mesclagem de continuação estar pronta —
    ver `_extrair_nome_produto`.
    """
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

        # "PRODUTO"/"DESCRIÇÃO" tem prioridade sobre "ITEM": a coluna ITEM
        # guarda só o número sequencial do item, não o texto do produto.
        idx_item = next((i for i, c in enumerate(cabecalho) if c.strip() == "item"), None)
        idx_desc = next((i for i, c in enumerate(cabecalho) if "produto" in c), None)
        if idx_desc is None:
            idx_desc = next((i for i, c in enumerate(cabecalho) if "descri" in c), None)
        if idx_desc is None:
            idx_desc = idx_item
        idx_qtd = next((i for i, c in enumerate(cabecalho) if "qtd" in c or "quant" in c), None)
        # "un" tem que casar exatamente — "vl. unitário" também contém "un"
        # como substring e não pode ser confundido com a coluna de unidade.
        idx_un = next((i for i, c in enumerate(cabecalho) if c.strip() == "un"), None)
        idx_vunit = next((i for i, c in enumerate(cabecalho) if "unit" in c), None)
        idx_vtotal = next((i for i, c in enumerate(cabecalho) if "total" in c), None)

        for linha in tabela[1:]:
            if not linha or all(not c for c in linha):
                continue
            desc = str(linha[idx_desc] or "").strip() if idx_desc is not None else ""
            desc = re.sub(r"\s+", " ", desc).strip()
            if not desc or desc.lower() in ("item", "descrição", "produto"):
                continue

            item_num = str(linha[idx_item] or "").strip() if idx_item is not None else ""
            unidade = str(linha[idx_un] or "").strip() if idx_un is not None else ""
            qtd = _limpar_valor(str(linha[idx_qtd] or "")) if idx_qtd is not None else None
            vunit = _limpar_valor(str(linha[idx_vunit] or "")) if idx_vunit is not None else None
            vtotal = _limpar_valor(str(linha[idx_vtotal] or "")) if idx_vtotal is not None else None

            # Linha de continuação (sem número de item nem valores): junta ao
            # item anterior em vez de criar um item novo.
            if not item_num and qtd is None and vunit is None and vtotal is None and itens:
                itens[-1]["descricao"] = (itens[-1]["descricao"] + " " + desc).strip()
                continue

            if vtotal is None and qtd and vunit:
                vtotal = round(qtd * vunit, 2)
            itens.append({
                "descricao": desc,
                "unidade": unidade,
                "quantidade": qtd,
                "valor_unitario": vunit,
                "valor_total": vtotal,
            })

    for item in itens:
        item["descricao"] = _extrair_nome_produto(item["descricao"])

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
            "descricao": _extrair_nome_produto(desc),
            "unidade": "",
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
            r"ordem\s*de\s*compra\s*[-:]?\s*n[oº°\.]*\s*[-:\s]*(\d+)",
            r"OC\s*[nN][oº°]?\s*[:\s]*(\d+)",
            r"\bOC\b[^\d]*(\d{4,})",
        )

        # "EMPRESA:" tem prioridade — em layouts como o da Prefeitura de
        # Goianápolis, "CÓD. FORNECEDOR:" aparece antes no texto e é só um
        # código numérico, não o nome do fornecedor.
        resultado["fornecedor"] = _primeiro_match(
            texto,
            r"EMPRESA[:\s]+(.+?)(?=\s+[A-ZÇÃÕÁÉÍÓÚÂÊÔ]{3,}\s*:)",
            r"(?:raz[ãa]o\s*social)[:\s]+([^\n]{3,60})",
            r"(?:fornecedor)[:\s]+([^\n]{3,60})",
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

