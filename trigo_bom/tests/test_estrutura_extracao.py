"""
Camada 7 — Validação estrutural da extração.
Verifica que os módulos de extração sempre retornam JSON válido com as chaves
obrigatórias — mesmo quando o arquivo não existe ou não contém dados esperados.
O frontend nunca deve receber KeyError ou JSON malformado.
"""
import json
import pytest

from extracao.nf import extrair_nf, _extrair_numero
from extracao.ordem_compra import extrair_ordem_compra


CHAVES_NF = {"numero", "fornecedor", "data_emissao", "valor", "destinatario", "orgao_id", "arquivo_pdf"}
CHAVES_OC = {"numero", "fornecedor", "data_emissao", "data_entrega_prevista", "itens", "arquivo_pdf"}


def _pdf_vazio(tmp_path) -> str:
    import fitz
    caminho = str(tmp_path / "vazio.pdf")
    doc = fitz.open()
    doc.new_page()
    doc.save(caminho)
    doc.close()
    return caminho


# ── NF ───────────────────────────────────────────────────────────────────────

def test_extracao_nf_retorna_json_valido(tmp_path):
    assert isinstance(json.loads(extrair_nf(_pdf_vazio(tmp_path))), dict)


def test_extracao_nf_tem_chaves_obrigatorias(tmp_path):
    r = json.loads(extrair_nf(_pdf_vazio(tmp_path)))
    assert CHAVES_NF.issubset(r.keys())


def test_extracao_nf_pdf_inexistente_tem_chaves(tmp_path):
    r = json.loads(extrair_nf("/caminho/que/nao/existe.pdf"))
    assert CHAVES_NF.issubset(r.keys())
    assert "_erro" in r


def test_extracao_nf_valor_e_none_quando_nao_encontrado(tmp_path):
    r = json.loads(extrair_nf(_pdf_vazio(tmp_path)))
    assert r["valor"] is None


def test_extracao_nf_preserva_caminho_original(tmp_path):
    caminho = _pdf_vazio(tmp_path)
    assert json.loads(extrair_nf(caminho))["arquivo_pdf"] == caminho


# ── OC ───────────────────────────────────────────────────────────────────────

def test_extracao_oc_retorna_json_valido(tmp_path):
    assert isinstance(json.loads(extrair_ordem_compra(_pdf_vazio(tmp_path))), dict)


def test_extracao_oc_tem_chaves_obrigatorias(tmp_path):
    r = json.loads(extrair_ordem_compra(_pdf_vazio(tmp_path)))
    assert CHAVES_OC.issubset(r.keys())


def test_extracao_oc_itens_e_lista(tmp_path):
    assert isinstance(json.loads(extrair_ordem_compra(_pdf_vazio(tmp_path)))["itens"], list)


def test_extracao_oc_pdf_inexistente_tem_chaves(tmp_path):
    r = json.loads(extrair_ordem_compra("/nao/existe.pdf"))
    assert CHAVES_OC.issubset(r.keys())
    assert "_erro" in r


# ── Número da NF: preserva zeros à esquerda, vazio não vira "0" ───────────────

def test_extrair_numero_preserva_zeros_a_esquerda():
    assert _extrair_numero("Número da nota: 000452") == "000452"


def test_extrair_numero_remove_separadores_de_milhar():
    assert _extrair_numero("Nº 12.345") == "12345"


def test_extrair_numero_vazio_nao_vira_zero():
    assert _extrair_numero("texto sem identificacao de nota") == ""
