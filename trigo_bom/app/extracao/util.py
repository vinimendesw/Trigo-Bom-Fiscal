"""
Funções utilitárias compartilhadas pela extração de NF (nf.py / nf_xml.py) e de
Ordem de Compra (ordem_compra.py). Centraliza a limpeza de valores monetários, a
busca por padrões e a normalização de datas — antes duplicadas em cada módulo.
"""
import re


def limpar_valor(s):
    """Converte um trecho de texto em float, tolerando os formatos que aparecem
    em documentos brasileiros:

      - "1.234,56" / "10.000,00" → vírgula é o separador decimal, ponto é milhar
      - "1.500" / "10.000"       → ponto como separador de milhar, sem decimais
      - "1234.56"                → ponto como separador decimal
      - "R$ 80,00"               → símbolos não numéricos são descartados

    Retorna None quando não há dígitos ou a conversão falha.
    """
    if not s:
        return None
    s = re.sub(r"[^\d,\.]", "", s)
    if not s:
        return None
    if "," in s:
        # Formato BR: vírgula é o separador decimal; pontos (se houver) são milhar.
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(?:\.\d{3})+", s):
        # Pontos como separador de milhar, sem parte decimal (ex.: 1.500 → 1500,
        # 10.000 → 10000). Sem este caso, "1.500" seria lido como 1,5.
        s = s.replace(".", "")
    # Caso contrário, um ponto eventual é separador decimal (ex.: 1234.56) — mantém.
    try:
        return float(s)
    except ValueError:
        return None


def primeiro_match(texto: str, *padroes: str) -> str:
    """Retorna o grupo 1 do primeiro padrão que casar (IGNORECASE), já com
    .strip() aplicado; "" se nenhum casar."""
    for p in padroes:
        m = re.search(p, texto, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return ""


def normalizar_data(bruta: str) -> str:
    """Converte 'DD/MM/AAAA' (ou separado por '-'/'.') para ISO 'AAAA-MM-DD',
    formato exigido pelo <input type="date"> da tela de inclusão de NF.
    Retorna "" quando a entrada é vazia ou não casa o formato esperado."""
    if not bruta:
        return ""
    m = re.match(r"(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{2,4})", bruta)
    if not m:
        return ""
    d, mm, y = m.groups()
    if len(y) == 2:
        y = "20" + y
    try:
        return f"{int(y):04d}-{int(mm):02d}-{int(d):02d}"
    except ValueError:
        return ""
