"""
Camada 1 + Camada 7 — Testes de extração de NF-e a partir de XML.
"""
import json
import os
import pytest
from extracao.nf_xml import extrair_nf_xml

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "nfe_exemplo.xml")
FIXTURE_COM_DEST_SAUDE = os.path.join(os.path.dirname(__file__), "fixtures", "nfe_com_dest_saude.xml")


# ── Estrutura obrigatória ─────────────────────────────────────────────────────

CHAVES_NF_XML = {"numero", "fornecedor", "data_emissao", "valor", "itens",
                 "destinatario", "orgao_id", "arquivo_xml"}


def test_retorna_json_valido():
    r = json.loads(extrair_nf_xml(FIXTURE))
    assert isinstance(r, dict)


def test_tem_chaves_obrigatorias():
    r = json.loads(extrair_nf_xml(FIXTURE))
    assert CHAVES_NF_XML.issubset(r.keys())


def test_itens_e_lista():
    r = json.loads(extrair_nf_xml(FIXTURE))
    assert isinstance(r["itens"], list)


# ── Valores extraídos ─────────────────────────────────────────────────────────

def test_extrai_numero():
    r = json.loads(extrair_nf_xml(FIXTURE))
    assert r["numero"] == "452"


def test_extrai_fornecedor():
    r = json.loads(extrair_nf_xml(FIXTURE))
    assert r["fornecedor"] == "Distribuidora Central Ltda"


def test_extrai_data_emissao():
    r = json.loads(extrair_nf_xml(FIXTURE))
    assert r["data_emissao"] == "2026-06-20"


def test_extrai_valor_total():
    r = json.loads(extrair_nf_xml(FIXTURE))
    assert r["valor"] == pytest.approx(420.0)


def test_extrai_dois_itens():
    r = json.loads(extrair_nf_xml(FIXTURE))
    assert len(r["itens"]) == 2


def test_item1_descricao():
    r = json.loads(extrair_nf_xml(FIXTURE))
    assert r["itens"][0]["descricao"] == "Arroz Tipo 1 5kg"


def test_item1_quantidade():
    r = json.loads(extrair_nf_xml(FIXTURE))
    assert r["itens"][0]["quantidade"] == pytest.approx(10.0)


def test_item1_valor_total():
    r = json.loads(extrair_nf_xml(FIXTURE))
    assert r["itens"][0]["valor_total"] == pytest.approx(250.0)


def test_item1_ncm():
    r = json.loads(extrair_nf_xml(FIXTURE))
    assert r["itens"][0]["ncm"] == "10063021"


def test_item1_cfop():
    r = json.loads(extrair_nf_xml(FIXTURE))
    assert r["itens"][0]["cfop"] == "5102"


def test_item2_valores():
    r = json.loads(extrair_nf_xml(FIXTURE))
    it = r["itens"][1]
    assert it["descricao"] == "Feijão Carioca 1kg"
    assert it["quantidade"] == pytest.approx(20.0)
    assert it["valor_unitario"] == pytest.approx(8.5)
    assert it["valor_total"] == pytest.approx(170.0)


# ── Destinatário / detecção automática de órgão (CLAUDE.md seção 6.3) ────────

def test_xml_sem_dest_tem_destinatario_vazio_e_orgao_none():
    r = json.loads(extrair_nf_xml(FIXTURE))
    assert r["destinatario"] == ""
    assert r["orgao_id"] is None


def test_xml_com_dest_extrai_destinatario():
    r = json.loads(extrair_nf_xml(FIXTURE_COM_DEST_SAUDE))
    assert r["destinatario"] == "SECRETARIA MUNICIPAL DE SAUDE DE GOIANAPOLIS"


def test_xml_com_dest_detecta_orgao_saude():
    r = json.loads(extrair_nf_xml(FIXTURE_COM_DEST_SAUDE))
    assert r["orgao_id"] == 2


# ── Arquivo inexistente ───────────────────────────────────────────────────────

def test_arquivo_inexistente_tem_chaves():
    r = json.loads(extrair_nf_xml("/nao/existe.xml"))
    assert CHAVES_NF_XML.issubset(r.keys())
    assert "_erro" in r


def test_arquivo_inexistente_itens_e_lista():
    r = json.loads(extrair_nf_xml("/nao/existe.xml"))
    assert isinstance(r["itens"], list)


# ── XML inválido ──────────────────────────────────────────────────────────────

def test_xml_invalido_retorna_erro(tmp_path):
    f = tmp_path / "invalido.xml"
    f.write_text("isto não é xml <>>><", encoding="utf-8")
    r = json.loads(extrair_nf_xml(str(f)))
    assert "_erro" in r
    assert CHAVES_NF_XML.issubset(r.keys())


def test_xml_sem_nfe_retorna_erro(tmp_path):
    f = tmp_path / "sem_nfe.xml"
    f.write_text('<?xml version="1.0"?><raiz><filho>x</filho></raiz>', encoding="utf-8")
    r = json.loads(extrair_nf_xml(str(f)))
    assert "_erro" in r


# ── NFe como raiz (sem nfeProc) ──────────────────────────────────────────────

def test_aceita_nfe_como_raiz(tmp_path):
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<NFe xmlns="http://www.portalfiscal.inf.br/nfe">
  <infNFe>
    <ide><nNF>99</nNF><dhEmi>2026-01-15T08:00:00-03:00</dhEmi></ide>
    <emit><xNome>Empresa Teste</xNome></emit>
    <total><ICMSTot><vNF>100.00</vNF></ICMSTot></total>
  </infNFe>
</NFe>"""
    f = tmp_path / "nfe_raiz.xml"
    f.write_text(xml, encoding="utf-8")
    r = json.loads(extrair_nf_xml(str(f)))
    assert r["numero"] == "99"
    assert r["fornecedor"] == "Empresa Teste"
    assert r["data_emissao"] == "2026-01-15"
    assert r["valor"] == pytest.approx(100.0)
