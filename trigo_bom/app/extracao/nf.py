import json
import os
import re
import io

import pdfplumber
import fitz  # PyMuPDF

from extracao.orgao import detectar_orgao
from extracao.util import limpar_valor, primeiro_match, normalizar_data

# Aliases internos: o restante deste módulo (e test_limpar_valor.py, que importa
# `_limpar_valor` daqui) continua usando os nomes privados, agora delegando às
# funções compartilhadas de extracao.util.
_limpar_valor = limpar_valor
_primeiro_match = primeiro_match
_normalizar_data = normalizar_data

try:
    import pytesseract
    from PIL import Image
except ImportError:  # pragma: no cover - ambiente sem Tesseract/Pillow instalado
    pytesseract = None
    Image = None


# Frases (nao palavras isoladas) que sempre aparecem intactas num DANFE
# legivel - usadas para detectar texto corrompido (camada de texto do PDF com
# encoding de fonte quebrado). Palavras isoladas como "valor" ou "danfe"
# podem sobreviver por coincidencia mesmo em texto corrompido (a corrupcao e
# por glifo/caractere, nao uniforme), por isso exigimos frases de multiplas
# palavras - muito mais improvavel de "sobreviver" intactas por acaso.
# Cada padrao tolera espaco opcional entre as palavras (PDFs variam: "/" colado
# ou separado por espacos, ex.: "DESTINATARIO/REMETENTE" vs "DESTINATARIO / REMETENTE").
_PADROES_DANFE = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"destinatario\s*/\s*remetente",
        r"identificacao\s*do\s*emitente",
        r"chave\s*de\s*acesso",
        r"razao\s*social",
        r"valor\s*total\s*da\s*nota",
        r"data\s*da\s*emissao",
        r"calculo\s*do\s*imposto",
        r"nota\s*fiscal\s*eletronica",
    )
)

_FORNECEDOR_INVALIDO = re.compile(
    r"^(danfe|documento\s*auxiliar|nota\s*fiscal\s*eletr[oô]nica)\b", re.IGNORECASE
)

_CABECALHO_DESTINATARIO = re.compile(
    r"raz[ãa]o\s*social|cnpj|cpf|data\s*da\s*emiss", re.IGNORECASE
)

# Linha do canhoto de recebimento ("RECEBEMOS DE <fornecedor> OS PRODUTOS...")
# - presente em todo DANFE, mesmo quando a secao "IDENTIFICACAO DO EMITENTE"
# nao e capturada pelo OCR (nome do emitente as vezes fica sobre uma imagem/
# logo). Para de capturar no CPF do recebedor (11 digitos), em "OS PRODUTOS"
# ou na quebra de linha - o que vier primeiro, pois o layout varia.
_RECEBEMOS_DE = re.compile(
    r"RECEBEMOS\s+DE\s+([A-ZÀ-Ü0-9À-Ü&\.\-\s]{3,70}?)(?:\s+\d{11}\b|\s+OS\s+PRODUTOS|\n)",
    re.IGNORECASE,
)


def _normalizar_para_comparacao(texto: str) -> str:
    """Remove acentos comuns e baixa a caixa, para comparar com as frases de
    referencia (que aparecem no PDF original com ou sem acentuacao)."""
    trocas = str.maketrans("ãáàâéêíóôõúç", "aaaaeeiooouc")
    return texto.lower().translate(trocas)


def _texto_parece_corrompido(texto: str) -> bool:
    """Texto muito curto, ou sem nenhuma das frases-padrao de um DANFE
    aparecendo intacta, e sinal de camada de texto corrompida no PDF."""
    if not texto or len(texto.strip()) < 20:
        return True
    alvo = _normalizar_para_comparacao(texto)
    return not any(p.search(alvo) for p in _PADROES_DANFE)


def _ocr_pdf(caminho: str) -> str:
    """Rasteriza as paginas do PDF (PyMuPDF) e roda OCR (pytesseract).
    Retorna string vazia se as dependencias de OCR nao estiverem disponiveis
    ou se a extracao falhar - nesse caso o chamador usa o texto original."""
    if pytesseract is None or Image is None:
        return ""
    try:
        doc = fitz.open(caminho)
        partes = []
        for pagina in doc:
            pix = pagina.get_pixmap(dpi=300)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            texto_pagina = ""
            for lang in ("por", "eng"):
                try:
                    texto_pagina = pytesseract.image_to_string(img, lang=lang)
                    break
                except Exception:
                    continue
            partes.append(texto_pagina)
        doc.close()
        return "\n".join(partes).strip()
    except Exception:
        return ""


def _extrair_texto(caminho: str):
    """Tenta pdfplumber; cai para PyMuPDF; se o texto vier vazio ou parecer
    corrompido (encoding de fonte quebrado), cai para OCR.
    Retorna (texto, usou_ocr)."""
    if not os.path.isfile(caminho):
        # Erro real (arquivo nao existe) - nao deve ser confundido com um PDF
        # valido mas sem texto extraivel (esse caso retorna texto vazio
        # normalmente, sem levantar excecao).
        raise FileNotFoundError(f"Arquivo nao encontrado: {caminho}")

    texto = ""
    try:
        with pdfplumber.open(caminho) as pdf:
            texto = "\n".join(p.extract_text() or "" for p in pdf.pages).strip()
    except Exception:
        texto = ""

    if not texto:
        try:
            doc = fitz.open(caminho)
            texto = "\n".join(p.get_text() for p in doc).strip()
            doc.close()
        except Exception:
            pass

    if _texto_parece_corrompido(texto):
        texto_ocr = _ocr_pdf(caminho)
        if texto_ocr:
            return texto_ocr, True

    return texto, False


def _maior_valor_monetario(texto: str):
    """Ultimo recurso para o valor da nota: quando nenhum rotulo
    ("VALOR TOTAL DA NOTA", "R$" etc.) foi reconhecido - comum em texto OCR,
    onde o rotulo aparece espremido/colado a outras colunas - assume-se que o
    maior valor monetario no documento e o total da nota."""
    candidatos = re.findall(r"\d{1,3}(?:\.\d{3})*,\d{2}", texto)
    valores = [v for v in (_limpar_valor(c) for c in candidatos) if v is not None]
    return max(valores) if valores else None


def _extrair_numero(texto: str) -> str:
    bruto = _primeiro_match(
        texto,
        r"n[uú]mero\s*(?:da\s*)?(?:nota|NF)[:\s]*(\d+)",
        r"NF[- ]*e?\s*[nN][oO]?\s*[:\s]*(\d+)",
        r"nota\s*fiscal\s*n[oº°]?\s*[:\s]*(\d+)",
        r"N[º°o]\.?\s*[:\-]?\s*(\d{2,3}(?:[.\s]\d{3}){1,3})",
        r"\bNF\b[^\d]*(\d{4,})",
    )
    # Preserva o número como veio, apenas removendo separadores não numéricos
    # (pontos/espaços de milhar do nNF). Não faz lstrip("0"): zeros à esquerda
    # fazem parte do número da nota (ex.: "000452"). Vazio continua vazio — nunca
    # vira "0", que seria um número de nota falso.
    return re.sub(r"\D", "", bruto)


def _extrair_destinatario(texto: str) -> str:
    # Caminho comum quando o PDF tem texto selecionavel integro (ou em texto
    # sintetico de teste): rotulo seguido de quebra de linha com o valor.
    valor = _primeiro_match(
        texto,
        r"NOME\s*/\s*RAZ[ÃA]O\s*SOCIAL[:\s]*\n([^\n]{3,80})",
        r"DESTINAT[ÁA]RIO\s*/\s*REMETENTE[:\s]*\n([^\n]{3,80})",
    )
    if valor and not _CABECALHO_DESTINATARIO.search(valor):
        return valor

    # Layout tipico de OCR: cabecalho e linha de dados da tabela
    # DESTINATARIO/REMETENTE saem como linhas distintas (ou o cabecalho vira
    # uma unica linha colada), entao ancoramos pelo CNPJ/CPF que sempre
    # acompanha o nome na linha de dados real.
    m = re.search(r"DESTINAT[ÁA]RIO\s*/?\s*REMETENTE", texto, re.IGNORECASE)
    trecho = texto[m.end():m.end() + 600] if m else texto
    m2 = re.search(
        r"([A-ZÀ-Ü][A-ZÀ-Ü0-9\.\-/ ]{5,80}?)\s+\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", trecho
    )
    return m2.group(1).strip(" -") if m2 else ""


def extrair_nf(caminho: str) -> str:
    resultado = {
        "numero": "",
        "fornecedor": "",
        "data_emissao": "",
        "valor": None,
        "destinatario": "",
        "orgao_id": None,
        "arquivo_pdf": caminho,
    }

    try:
        texto, usou_ocr = _extrair_texto(caminho)
        resultado["_ocr_usado"] = usou_ocr

        resultado["numero"] = _extrair_numero(texto)

        fornecedor = _primeiro_match(
            texto,
            r"(?:raz[ãa]o\s*social|emitente|fornecedor)[:\s]+([^\n]{3,60})",
            r"(?:nome|empresa)[:\s]+([A-ZÁÀÂÃÉÊÍÓÔÕÚ][^\n]{2,50})",
        )
        if fornecedor and (
            _FORNECEDOR_INVALIDO.match(fornecedor)
            or _CABECALHO_DESTINATARIO.search(fornecedor)
        ):
            # Descarta tambem capturas que na verdade vieram do cabecalho da
            # tabela DESTINATARIO/REMETENTE (ex.: "RAZAO SOCIAL" do emitente
            # bateu, mas o texto seguinte era "CNPJ/ CPF DATA DA EMISSAO" do
            # destinatario, nao um nome de fornecedor real).
            fornecedor = ""
        if not fornecedor:
            # Canhoto de recebimento ("RECEBEMOS DE ...") - mais confiavel em
            # PDFs OCR'd, onde a secao "IDENTIFICACAO DO EMITENTE" costuma
            # vir vazia (nome do emitente sobreposto a um logo/imagem).
            m_recebemos = _RECEBEMOS_DE.search(texto)
            if m_recebemos:
                fornecedor = m_recebemos.group(1).strip(" -")
        resultado["fornecedor"] = fornecedor

        resultado["data_emissao"] = _normalizar_data(
            _primeiro_match(
                texto,
                r"data\s*(?:de\s*)?emiss[aã]o[:\s]*(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})",
                r"emiss[aã]o[:\s]*(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})",
                r"(?<!\w)(\d{2}[/\-\.]\d{2}[/\-\.]\d{4})(?!\w)",
            )
        )

        valor_str = _primeiro_match(
            texto,
            # Linha do canhoto ("VALOR TOTAL: R$ ..." ou "...RS ...", OCR
            # as vezes engole o "$") - mais confiavel que a tabela de calculo
            # do imposto mais abaixo, onde rotulo e valor podem ficar em
            # linhas/colunas desalinhadas pelo OCR.
            r"valor\s*total[:\s]*r\$?s?\s*([\d\.]+,\d{2})",
            r"valor\s*(?:total|l[íi]quido|da\s*nota)[:\s]*([\d\.]+,\d{2})",
            r"total\s*(?:geral|da\s*nota|a\s*pagar)[:\s]*([\d\.]+,\d{2})",
            # Generico - mas nunca a linha de "tributos aproximados" (sempre
            # presente no DANFE e quase sempre 0,00, nao e o total da nota).
            r"(?<!tributos\s)R\$\s*([\d\.]+,\d{2})",
        )
        resultado["valor"] = (
            _limpar_valor(valor_str) if valor_str else _maior_valor_monetario(texto)
        )

        # Destinatario/remetente (o orgao a quem a NF foi emitida) - campo
        # proprio do DANFE, distinto do emitente/fornecedor capturado acima.
        resultado["destinatario"] = _extrair_destinatario(texto)

        # Deteccao automatica do orgao por palavra-chave (CLAUDE.md secao 6.3) -
        # pre-seleciona sem exigir confirmacao manual; usuario pode corrigir.
        resultado["orgao_id"] = detectar_orgao(resultado["destinatario"])

        resultado["_texto_bruto"] = texto

    except Exception as e:
        resultado["_erro"] = str(e)

    return json.dumps(resultado, ensure_ascii=False)
