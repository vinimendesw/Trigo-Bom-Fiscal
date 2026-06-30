"""
Camada 1 — Fallback de OCR na extração de NF (CLAUDE.md seção 11: PDFs com
camada de texto corrompida, comum em DANFEs com encoding de fonte quebrado).

Usa monkeypatch para isolar cada cenário sem depender do binário real do
Tesseract: testa a lógica de decisão (quando acionar OCR), o uso do texto
OCR no resto do pipeline de extração, e os fallbacks de fornecedor/valor que
dependem de padrões só confiáveis em texto vindo de OCR (canhoto do DANFE).
"""
import json

import extracao.nf as nf


_TEXTO_CORROMPIDO = "ÿý" * 30  # curto e sem nenhuma frase-padrão do DANFE
_TEXTO_LEGIVEL = (
    "DESTINATARIO/REMETENTE\n"
    "NOME / RAZAO SOCIAL\n"
    "PREFEITURA MUNICIPAL DE GOIANAPOLIS\n"
    "VALOR TOTAL DA NOTA\n"
    "1.532,99\n"
)

_TEXTO_OCR_CANHOTO = (
    "RECEBEMOS DE PANIFICADORA E SUPERMERCADO TRIGO BOM - LTDA\n"
    "EMISSAO: 19/06/2026 OS PRODUTOS / SERVICOS CONSTANTES DA NOTA\n"
    "VALOR TOTAL: R$ 1.532,99\n"
    "DESTINATARIO/REMETENTE\n"
    "PREFEITURA MUNICIPAL DE GOIANAPOLIS\n"
    "Valor aproximado tributos R$0,00 (0,00%) Fonte: IBPT\n"
)


# ── Decisão de acionar OCR ──────────────────────────────────────────────────

def test_texto_corrompido_e_detectado():
    assert nf._texto_parece_corrompido(_TEXTO_CORROMPIDO) is True


def test_texto_legivel_nao_e_marcado_como_corrompido():
    assert nf._texto_parece_corrompido(_TEXTO_LEGIVEL) is False


def test_texto_vazio_e_tratado_como_corrompido():
    assert nf._texto_parece_corrompido("") is True


# ── extrair_nf aciona/evita OCR conforme o texto da camada do PDF ──────────

def test_extrair_nf_usa_texto_original_quando_legivel(tmp_path, monkeypatch):
    caminho = str(tmp_path / "nf.pdf")
    open(caminho, "wb").close()

    monkeypatch.setattr(nf, "_extrair_texto", lambda c: (_TEXTO_LEGIVEL, False))
    r = json.loads(nf.extrair_nf(caminho))

    assert r["_ocr_usado"] is False
    assert r["destinatario"] == "PREFEITURA MUNICIPAL DE GOIANAPOLIS"


def test_extrair_nf_usa_texto_ocr_quando_camada_corrompida(tmp_path, monkeypatch):
    caminho = str(tmp_path / "nf.pdf")
    open(caminho, "wb").close()

    monkeypatch.setattr(nf, "_extrair_texto", lambda c: (_TEXTO_OCR_CANHOTO, True))
    r = json.loads(nf.extrair_nf(caminho))

    assert r["_ocr_usado"] is True
    assert r["fornecedor"] == "PANIFICADORA E SUPERMERCADO TRIGO BOM - LTDA"


def test_ocr_pdf_retorna_vazio_quando_dependencias_ausentes(monkeypatch):
    monkeypatch.setattr(nf, "pytesseract", None)
    monkeypatch.setattr(nf, "Image", None)
    assert nf._ocr_pdf("/qualquer/caminho.pdf") == ""


def test_extrair_texto_cai_para_ocr_quando_pdfplumber_e_pymupdf_falham(tmp_path, monkeypatch):
    caminho = str(tmp_path / "nf.pdf")
    open(caminho, "wb").close()

    class _PdfplumberFalho:
        def __enter__(self):
            raise RuntimeError("falha simulada")

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(nf.pdfplumber, "open", lambda c: _PdfplumberFalho())

    def _fitz_open_falho(c):
        raise RuntimeError("falha simulada")

    monkeypatch.setattr(nf.fitz, "open", _fitz_open_falho)
    monkeypatch.setattr(nf, "_ocr_pdf", lambda c: _TEXTO_OCR_CANHOTO)

    texto, usou_ocr = nf._extrair_texto(caminho)
    assert usou_ocr is True
    assert texto == _TEXTO_OCR_CANHOTO


def test_extrair_texto_levanta_erro_para_arquivo_inexistente():
    import pytest

    with pytest.raises(FileNotFoundError):
        nf._extrair_texto("/caminho/que/nao/existe.pdf")


# ── Fallback de fornecedor via canhoto "RECEBEMOS DE ..." ──────────────────

def test_recebemos_de_e_usado_quando_identificacao_emitente_vazia(tmp_path, monkeypatch):
    caminho = str(tmp_path / "nf.pdf")
    open(caminho, "wb").close()
    monkeypatch.setattr(nf, "_extrair_texto", lambda c: (_TEXTO_OCR_CANHOTO, True))

    r = json.loads(nf.extrair_nf(caminho))
    assert r["fornecedor"] == "PANIFICADORA E SUPERMERCADO TRIGO BOM - LTDA"


def test_fornecedor_descarta_captura_que_e_cabecalho_de_destinatario(tmp_path, monkeypatch):
    # "RAZAO SOCIAL" do emitente bate, mas o texto seguinte e o cabecalho
    # da tabela do destinatario (CNPJ/ CPF DATA DA EMISSAO), nao um nome real
    # - deve ser descartado e cair para o fallback do canhoto.
    texto = (
        "RAZAO SOCIAL CNPJ/ CPF DATA DA EMISSAO\n"
        + _TEXTO_OCR_CANHOTO
    )
    caminho = str(tmp_path / "nf.pdf")
    open(caminho, "wb").close()
    monkeypatch.setattr(nf, "_extrair_texto", lambda c: (texto, True))

    r = json.loads(nf.extrair_nf(caminho))
    assert r["fornecedor"] == "PANIFICADORA E SUPERMERCADO TRIGO BOM - LTDA"


# ── Fallback de valor via canhoto, ignorando "tributos aproximados" ────────

def test_valor_usa_linha_do_canhoto_em_vez_da_linha_de_tributos(tmp_path, monkeypatch):
    caminho = str(tmp_path / "nf.pdf")
    open(caminho, "wb").close()
    monkeypatch.setattr(nf, "_extrair_texto", lambda c: (_TEXTO_OCR_CANHOTO, True))

    r = json.loads(nf.extrair_nf(caminho))
    assert r["valor"] == 1532.99


def test_valor_aceita_variante_rs_quando_ocr_engole_o_cifrao(tmp_path, monkeypatch):
    texto = _TEXTO_OCR_CANHOTO.replace("VALOR TOTAL: R$ 1.532,99", "VALOR TOTAL: RS 1.532,99")
    caminho = str(tmp_path / "nf.pdf")
    open(caminho, "wb").close()
    monkeypatch.setattr(nf, "_extrair_texto", lambda c: (texto, True))

    r = json.loads(nf.extrair_nf(caminho))
    assert r["valor"] == 1532.99
