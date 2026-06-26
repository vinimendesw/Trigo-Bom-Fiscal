"""
Camada 1 — Testes unitários do repositório: Ordens de Compra e seus itens.
"""
import json
import pytest
import db.repositorio as repo


OC_BASE = {
    "numero": "OC-2026-001",
    "fornecedor": "Distribuidora XYZ",
    "data_emissao": "2026-01-10",
    "data_entrega_prevista": "2026-01-25",
    "arquivo_pdf": "/tmp/oc001.pdf",
    "itens": [
        {"descricao": "Arroz 5kg", "quantidade": 10, "valor_unitario": 25.0, "valor_total": 250.0},
        {"descricao": "Feijão 1kg", "quantidade": 20, "valor_unitario": 8.5, "valor_total": 170.0},
    ],
}


def test_listar_ocs_vazio(db_isolado):
    assert json.loads(repo.listar_ordens_compra()) == []


def test_salvar_oc_retorna_id(db_isolado):
    resultado = json.loads(repo.salvar_ordem_compra(json.dumps(OC_BASE)))
    assert resultado["id"] == 1


def test_salvar_oc_persiste_cabecalho(db_isolado):
    repo.salvar_ordem_compra(json.dumps(OC_BASE))
    ocs = json.loads(repo.listar_ordens_compra())
    assert len(ocs) == 1
    assert ocs[0]["numero"] == "OC-2026-001"
    assert ocs[0]["fornecedor"] == "Distribuidora XYZ"
    assert ocs[0]["status_entrega"] == "pendente"


def test_salvar_oc_persiste_itens(db_isolado):
    oc_id = json.loads(repo.salvar_ordem_compra(json.dumps(OC_BASE)))["id"]
    itens = json.loads(repo.listar_itens_oc(oc_id))
    assert len(itens) == 2
    assert itens[0]["descricao"] == "Arroz 5kg"
    assert itens[0]["quantidade"] == pytest.approx(10)
    assert itens[1]["valor_total"] == pytest.approx(170.0)


def test_oc_sem_itens(db_isolado):
    oc_sem_itens = {**OC_BASE, "itens": []}
    oc_id = json.loads(repo.salvar_ordem_compra(json.dumps(oc_sem_itens)))["id"]
    itens = json.loads(repo.listar_itens_oc(oc_id))
    assert itens == []


def test_itens_oc_inexistente_retorna_lista_vazia(db_isolado):
    itens = json.loads(repo.listar_itens_oc(9999))
    assert itens == []


def test_atualizar_status_entrega(db_isolado):
    oc_id = json.loads(repo.salvar_ordem_compra(json.dumps(OC_BASE)))["id"]

    repo.atualizar_status_entrega_oc(json.dumps({"id": oc_id, "status_entrega": "entregue"}))

    ocs = json.loads(repo.listar_ordens_compra())
    assert ocs[0]["status_entrega"] == "entregue"


def test_status_entrega_atrasada(db_isolado):
    oc_id = json.loads(repo.salvar_ordem_compra(json.dumps(OC_BASE)))["id"]
    repo.atualizar_status_entrega_oc(json.dumps({"id": oc_id, "status_entrega": "atrasada"}))
    ocs = json.loads(repo.listar_ordens_compra())
    assert ocs[0]["status_entrega"] == "atrasada"
