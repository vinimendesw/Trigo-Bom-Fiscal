"""
Camada 2 — Contratos bridge ↔ JS.
Todo @Slot deve retornar JSON válido com as chaves esperadas pelo frontend,
mesmo quando a entrada está vazia, ausente ou malformada.
"""
import json
import pytest
import db.repositorio as repo


# ── Contratos de listagem (retornam sempre lista) ────────────────────────────

def test_listar_nfs_retorna_lista(db_isolado):
    assert isinstance(json.loads(repo.listar_nfs()), list)


def test_listar_nfs_filtrado_retorna_lista(db_isolado):
    assert isinstance(json.loads(repo.listar_nfs("{}")), list)


def test_listar_ocs_retorna_lista(db_isolado):
    assert isinstance(json.loads(repo.listar_ordens_compra()), list)


def test_listar_ocs_com_itens_retorna_lista(db_isolado):
    assert isinstance(json.loads(repo.listar_ordens_compra_com_itens()), list)


def test_listar_itens_oc_retorna_lista(db_isolado):
    assert isinstance(json.loads(repo.listar_itens_oc(1)), list)


def test_totais_por_orgao_retorna_lista(db_isolado):
    resultado = json.loads(repo.totais_nf_por_orgao(6, 2026))
    assert isinstance(resultado, list)


# ── Contratos de escrita (retornam {"id": int}) ──────────────────────────────

def test_salvar_nf_retorna_id_inteiro(db_isolado):
    r = json.loads(repo.salvar_nf(json.dumps({"status_pagamento": "nao_pago"})))
    assert "id" in r and isinstance(r["id"], int)


def test_salvar_oc_retorna_id_inteiro(db_isolado):
    r = json.loads(repo.salvar_ordem_compra(json.dumps({"itens": []})))
    assert "id" in r and isinstance(r["id"], int)


# ── Contratos de atualização (retornam {"ok": True}) ─────────────────────────

def test_atualizar_status_nf_retorna_ok(db_isolado):
    nf_id = json.loads(repo.salvar_nf(json.dumps({"status_pagamento": "nao_pago"})))["id"]
    r = json.loads(repo.atualizar_status_nf(json.dumps({
        "id": nf_id, "status_pagamento": "pago", "data_pagamento": "2026-02-01"
    })))
    assert r == {"ok": True}


def test_atualizar_status_oc_retorna_ok(db_isolado):
    oc_id = json.loads(repo.salvar_ordem_compra(json.dumps({"itens": []})))["id"]
    r = json.loads(repo.atualizar_status_entrega_oc(json.dumps({
        "id": oc_id, "status_entrega": "entregue"
    })))
    assert r == {"ok": True}


def test_marcar_pagas_em_massa_retorna_ok(db_isolado):
    ids = [
        json.loads(repo.salvar_nf(json.dumps({"status_pagamento": "nao_pago"})))["id"]
        for _ in range(3)
    ]
    r = json.loads(repo.marcar_pagas_em_massa(json.dumps({
        "ids": ids, "data_pagamento": "2026-06-26"
    })))
    assert r["ok"] is True
    assert r["atualizadas"] == 3


# ── Chaves obrigatórias nos objetos retornados ───────────────────────────────

CHAVES_NF = {"id", "numero", "orgao_id", "data_emissao", "valor",
             "categoria", "status_pagamento", "data_vencimento",
             "data_pagamento", "arquivo_pdf", "criado_em", "orgao_nome", "origem"}

CHAVES_OC = {"id", "numero", "fornecedor", "data_emissao",
             "data_entrega_prevista", "status_entrega", "arquivo_pdf"}

CHAVES_OC_COM_ITENS = CHAVES_OC | {"itens"}

CHAVES_ITEM_OC = {"id", "ordem_compra_id", "descricao",
                  "quantidade", "valor_unitario", "valor_total"}

CHAVES_TOTAIS_ORGAO = {"orgao_id", "orgao_nome", "total"}


def test_nf_tem_todas_as_chaves(db_isolado):
    repo.salvar_nf(json.dumps({"numero": "X", "orgao_id": 1, "valor": 100.0, "status_pagamento": "nao_pago"}))
    nf = json.loads(repo.listar_nfs())[0]
    assert CHAVES_NF.issubset(nf.keys())


def test_oc_tem_todas_as_chaves(db_isolado):
    repo.salvar_ordem_compra(json.dumps({"numero": "OC-1", "itens": []}))
    oc = json.loads(repo.listar_ordens_compra())[0]
    assert CHAVES_OC.issubset(oc.keys())


def test_oc_com_itens_tem_campo_itens(db_isolado):
    repo.salvar_ordem_compra(json.dumps({"numero": "OC-1", "itens": []}))
    oc = json.loads(repo.listar_ordens_compra_com_itens())[0]
    assert CHAVES_OC_COM_ITENS.issubset(oc.keys())
    assert isinstance(oc["itens"], list)


def test_item_oc_tem_todas_as_chaves(db_isolado):
    oc_id = json.loads(repo.salvar_ordem_compra(json.dumps({
        "itens": [{"descricao": "Item", "quantidade": 1, "valor_unitario": 1.0, "valor_total": 1.0}]
    })))["id"]
    item = json.loads(repo.listar_itens_oc(oc_id))[0]
    assert CHAVES_ITEM_OC.issubset(item.keys())


def test_totais_orgao_tem_todas_as_chaves(db_isolado):
    rows = json.loads(repo.totais_nf_por_orgao(6, 2026))
    assert len(rows) == 4  # 4 órgãos fixos
    for row in rows:
        assert CHAVES_TOTAIS_ORGAO.issubset(row.keys())
