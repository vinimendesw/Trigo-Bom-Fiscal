"""
Camada 1 — Testes de NF com itens (origem XML e manual) e migração de schema.
Os testes existentes em test_repositorio_nf.py continuam passando sem alteração
(NFs sem itens, origem pdf).
"""
import json
import sqlite3
import pytest
import db.repositorio as repo


# ── Dados de base ─────────────────────────────────────────────────────────────

NF_XML = {
    "numero": "452",
    "orgao_id": 2,
    "data_emissao": "2026-06-20",
    "valor": 420.0,
    "categoria": "Alimentícios",
    "status_pagamento": "nao_pago",
    "origem": "xml",
    "itens": [
        {"descricao": "Arroz Tipo 1 5kg", "quantidade": 10.0, "valor_unitario": 25.0, "valor_total": 250.0, "ncm": "10063021", "cfop": "5102"},
        {"descricao": "Feijão Carioca 1kg", "quantidade": 20.0, "valor_unitario": 8.5, "valor_total": 170.0, "ncm": "07133310", "cfop": "5102"},
    ],
}

NF_MANUAL = {
    "numero": "001",
    "orgao_id": 1,
    "valor": 100.0,
    "status_pagamento": "nao_pago",
    "origem": "manual",
    "itens": [
        {"descricao": "Item manual A", "quantidade": 5.0, "valor_unitario": 10.0, "valor_total": 50.0},
        {"descricao": "Item manual B", "quantidade": 2.0, "valor_unitario": 25.0, "valor_total": 50.0},
    ],
}

NF_PDF = {
    "numero": "900",
    "orgao_id": 3,
    "valor": 300.0,
    "status_pagamento": "nao_pago",
    "origem": "pdf",
}


# ── NF via XML ────────────────────────────────────────────────────────────────

def test_salvar_nf_xml_retorna_id(db_isolado):
    r = json.loads(repo.salvar_nf(json.dumps(NF_XML)))
    assert "id" in r and isinstance(r["id"], int)


def test_nf_xml_persiste_origem(db_isolado):
    nf_id = json.loads(repo.salvar_nf(json.dumps(NF_XML)))["id"]
    nfs = json.loads(repo.listar_nfs())
    nf = next(n for n in nfs if n["id"] == nf_id)
    assert nf["origem"] == "xml"


def test_nf_xml_persiste_dois_itens(db_isolado):
    nf_id = json.loads(repo.salvar_nf(json.dumps(NF_XML)))["id"]
    itens = json.loads(repo.listar_itens_nf(nf_id))
    assert len(itens) == 2


def test_nf_xml_item_descricao_e_valores(db_isolado):
    nf_id = json.loads(repo.salvar_nf(json.dumps(NF_XML)))["id"]
    itens = json.loads(repo.listar_itens_nf(nf_id))
    arroz = next(i for i in itens if "Arroz" in i["descricao"])
    assert arroz["quantidade"] == pytest.approx(10.0)
    assert arroz["valor_unitario"] == pytest.approx(25.0)
    assert arroz["valor_total"] == pytest.approx(250.0)


def test_nf_xml_item_ncm_e_cfop(db_isolado):
    nf_id = json.loads(repo.salvar_nf(json.dumps(NF_XML)))["id"]
    itens = json.loads(repo.listar_itens_nf(nf_id))
    arroz = next(i for i in itens if "Arroz" in i["descricao"])
    assert arroz["ncm"] == "10063021"
    assert arroz["cfop"] == "5102"


def test_nf_xml_delete_cascade_remove_itens(db_isolado):
    nf_id = json.loads(repo.salvar_nf(json.dumps(NF_XML)))["id"]
    with sqlite3.connect(db_isolado) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("DELETE FROM notas_fiscais WHERE id=?", (nf_id,))
    itens = json.loads(repo.listar_itens_nf(nf_id))
    assert itens == []


# ── NF manual ────────────────────────────────────────────────────────────────

def test_salvar_nf_manual_persiste_itens(db_isolado):
    nf_id = json.loads(repo.salvar_nf(json.dumps(NF_MANUAL)))["id"]
    itens = json.loads(repo.listar_itens_nf(nf_id))
    assert len(itens) == 2


def test_nf_manual_origem_gravada(db_isolado):
    nf_id = json.loads(repo.salvar_nf(json.dumps(NF_MANUAL)))["id"]
    nfs = json.loads(repo.listar_nfs())
    nf = next(n for n in nfs if n["id"] == nf_id)
    assert nf["origem"] == "manual"


def test_nf_manual_ncm_cfop_sao_none(db_isolado):
    nf_id = json.loads(repo.salvar_nf(json.dumps(NF_MANUAL)))["id"]
    itens = json.loads(repo.listar_itens_nf(nf_id))
    for item in itens:
        assert item.get("ncm") is None
        assert item.get("cfop") is None


# ── NF PDF (sem itens) ────────────────────────────────────────────────────────

def test_nf_pdf_sem_itens(db_isolado):
    nf_id = json.loads(repo.salvar_nf(json.dumps(NF_PDF)))["id"]
    itens = json.loads(repo.listar_itens_nf(nf_id))
    assert itens == []


def test_nf_pdf_origem_gravada(db_isolado):
    nf_id = json.loads(repo.salvar_nf(json.dumps(NF_PDF)))["id"]
    nfs = json.loads(repo.listar_nfs())
    nf = next(n for n in nfs if n["id"] == nf_id)
    assert nf["origem"] == "pdf"


# ── listar_itens_nf: id inexistente retorna lista vazia ──────────────────────

def test_listar_itens_nf_inexistente(db_isolado):
    assert json.loads(repo.listar_itens_nf(9999)) == []


# ── Migração: coluna origem pré-existente não quebra ─────────────────────────

def test_migracao_idempotente(db_isolado):
    """Chamar _migrar() duas vezes não deve lançar exceção."""
    repo._migrar()
    repo._migrar()


# ── Contrato: chaves de item_nota_fiscal ─────────────────────────────────────

CHAVES_ITEM_NF = {"id", "nota_fiscal_id", "descricao", "quantidade",
                  "valor_unitario", "valor_total", "ncm", "cfop"}

def test_item_nf_tem_todas_as_chaves(db_isolado):
    nf_id = json.loads(repo.salvar_nf(json.dumps(NF_XML)))["id"]
    item = json.loads(repo.listar_itens_nf(nf_id))[0]
    assert CHAVES_ITEM_NF.issubset(item.keys())
