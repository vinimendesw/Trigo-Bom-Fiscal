"""
Camada 1 + Camada 7 — Extração do destinatário e detecção automática de
órgão a partir de PDF de NF (CLAUDE.md seção 6.3).
Monta um PDF sintético reproduzindo o trecho relevante do DANFE.
"""
import json
import fitz
from extracao.nf import extrair_nf


def _pdf_com_texto(tmp_path, texto: str) -> str:
    caminho = str(tmp_path / "nf.pdf")
    doc = fitz.open()
    pagina = doc.new_page()
    pagina.insert_text((50, 50), texto)
    doc.save(caminho)
    doc.close()
    return caminho


_TRECHO_DANFE = (
    "IDENTIFICACAO DO EMITENTE\n"
    "PANIFICADORA E SUPERMERCADO TRIGO BOM - LTDA\n"
    "RUA ALAOR DA SA ABREU, 580\n"
    "DESTINATARIO/REMETENTE\n"
    "NOME / RAZAO SOCIAL\n"
    "{destinatario}\n"
    "ENDERECO\n"
    "AVENIDA CAMARA FILHO, 353\n"
    "VALOR TOTAL DA NOTA\n"
    "1.532,99\n"
)


def test_extrai_destinatario_prefeitura(tmp_path):
    texto = _TRECHO_DANFE.format(destinatario="PREFEITURA MUNICIPAL DE GOIANAPOLIS")
    caminho = _pdf_com_texto(tmp_path, texto)
    r = json.loads(extrair_nf(caminho))
    assert r["destinatario"] == "PREFEITURA MUNICIPAL DE GOIANAPOLIS"


def test_detecta_orgao_administracao_para_prefeitura_generica(tmp_path):
    texto = _TRECHO_DANFE.format(destinatario="PREFEITURA MUNICIPAL DE GOIANAPOLIS")
    caminho = _pdf_com_texto(tmp_path, texto)
    r = json.loads(extrair_nf(caminho))
    assert r["orgao_id"] == 1


def test_detecta_orgao_saude(tmp_path):
    texto = _TRECHO_DANFE.format(destinatario="SECRETARIA MUNICIPAL DE SAUDE DE GOIANAPOLIS")
    caminho = _pdf_com_texto(tmp_path, texto)
    r = json.loads(extrair_nf(caminho))
    assert r["orgao_id"] == 2


def test_destinatario_ainda_extrai_fornecedor_emitente_corretamente(tmp_path):
    texto = _TRECHO_DANFE.format(destinatario="SECRETARIA MUNICIPAL DE EDUCACAO DE GOIANAPOLIS")
    caminho = _pdf_com_texto(tmp_path, texto)
    r = json.loads(extrair_nf(caminho))
    assert r["fornecedor"] == "PANIFICADORA E SUPERMERCADO TRIGO BOM - LTDA"
    assert r["orgao_id"] == 3
