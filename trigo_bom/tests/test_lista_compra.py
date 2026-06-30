"""
Camada 1 — Testes das listas de compra:
  - Criação com nome auto-gerado
  - OCs vinculadas a listas
  - Agregação de itens com normalização de descrição
  - OCs sem lista
  - Status por lista
  - Exclusão de lista (OCs ficam órfãs)
"""
import json
import pytest
import db.repositorio as repo


# ── Fixtures auxiliares ──────────────────────────────────────────────────────

def _criar_lista(data_prevista=None):
    return json.loads(repo.criar_lista(json.dumps({"data_prevista": data_prevista})))


def _oc(lista_id=None, numero="OC-1", itens=None):
    return json.loads(repo.salvar_ordem_compra(json.dumps({
        "numero": numero,
        "fornecedor": "Fornecedor",
        "itens": itens or [],
        "lista_id": lista_id,
    })))["id"]


# ── Criação de lista ──────────────────────────────────────────────────────────

def test_criar_lista_retorna_id_e_nome(db_isolado):
    r = _criar_lista()
    assert "id" in r and isinstance(r["id"], int)
    assert "nome" in r and r["nome"].startswith("Lista")


def test_nomes_auto_incrementais(db_isolado):
    n1 = _criar_lista()["nome"]
    n2 = _criar_lista()["nome"]
    n3 = _criar_lista()["nome"]
    assert n1 != n2 != n3
    assert n1 == "Lista 01"
    assert n2 == "Lista 02"
    assert n3 == "Lista 03"


def test_nome_unico_apos_exclusao(db_isolado):
    # Regressão: com COUNT(*), excluir a Lista 02 de 3 fazia a próxima virar
    # "Lista 03", colidindo com a existente. Agora o número vem do id (nunca
    # reutilizado), garantindo unicidade.
    n1 = _criar_lista()  # Lista 01 (id 1)
    n2 = _criar_lista()  # Lista 02 (id 2)
    n3 = _criar_lista()  # Lista 03 (id 3)
    repo.excluir_lista(n2["id"])
    n4 = _criar_lista()["nome"]  # id 4 → Lista 04

    listas = json.loads(repo.listar_listas_com_ocs())
    nomes = [l["nome"] for l in listas]
    assert len(nomes) == len(set(nomes))  # todos os nomes únicos
    assert n4 == "Lista 04"
    assert n4 not in (n1["nome"], n3["nome"])


def test_lista_criada_com_status_pendente(db_isolado):
    lid = _criar_lista()["id"]
    listas = json.loads(repo.listar_listas_com_ocs())
    lista  = next(l for l in listas if l["id"] == lid)
    assert lista["status_entrega"] == "pendente"


def test_lista_com_data_prevista(db_isolado):
    lid = _criar_lista("2026-07-15")["id"]
    listas = json.loads(repo.listar_listas_com_ocs())
    lista  = next(l for l in listas if l["id"] == lid)
    assert lista["data_prevista"] == "2026-07-15"


# ── OCs vinculadas à lista ────────────────────────────────────────────────────

def test_oc_aparece_na_lista(db_isolado):
    lid  = _criar_lista()["id"]
    oc_id = _oc(lista_id=lid)
    listas = json.loads(repo.listar_listas_com_ocs())
    lista  = next(l for l in listas if l["id"] == lid)
    assert any(oc["id"] == oc_id for oc in lista["ocs"])


def test_oc_sem_lista_nao_aparece_em_lista(db_isolado):
    lid   = _criar_lista()["id"]
    _oc(lista_id=None)
    listas = json.loads(repo.listar_listas_com_ocs())
    lista  = next(l for l in listas if l["id"] == lid)
    assert lista["ocs"] == []


# ── OCs sem lista ─────────────────────────────────────────────────────────────

def test_listar_ocs_sem_lista(db_isolado):
    lid   = _criar_lista()["id"]
    _oc(lista_id=lid, numero="COM")       # com lista
    _oc(lista_id=None, numero="SEM")      # sem lista
    avulsas = json.loads(repo.listar_ocs_sem_lista())
    assert len(avulsas) == 1
    assert avulsas[0]["numero"] == "SEM"


def test_listar_ocs_sem_lista_vazio(db_isolado):
    assert json.loads(repo.listar_ocs_sem_lista()) == []


# ── Agregação de itens ────────────────────────────────────────────────────────

def test_itens_iguais_somados(db_isolado):
    lid = _criar_lista()["id"]
    _oc(lid, "OC-1", itens=[
        {"descricao": "Água Mineral 500ml", "unidade": "UN", "quantidade": 3, "valor_unitario": 2.5, "valor_total": 7.5},
    ])
    _oc(lid, "OC-2", itens=[
        {"descricao": "Água Mineral 500ml", "unidade": "UN", "quantidade": 4, "valor_unitario": 2.5, "valor_total": 10.0},
    ])
    lista = next(l for l in json.loads(repo.listar_listas_com_ocs()) if l["id"] == lid)
    agregados = lista["itens_agregados"]
    assert len(agregados) == 1
    assert agregados[0]["quantidade"] == pytest.approx(7.0)
    assert agregados[0]["valor_total"]  == pytest.approx(17.5)


def test_normalizacao_case_insensitive(db_isolado):
    lid = _criar_lista()["id"]
    _oc(lid, "OC-1", itens=[{"descricao": "PAPEL HIGIÊNICO", "quantidade": 5, "valor_total": 10.0}])
    _oc(lid, "OC-2", itens=[{"descricao": "papel higiênico", "quantidade": 3, "valor_total": 6.0}])
    lista = next(l for l in json.loads(repo.listar_listas_com_ocs()) if l["id"] == lid)
    assert len(lista["itens_agregados"]) == 1
    assert lista["itens_agregados"][0]["quantidade"] == pytest.approx(8.0)


def test_normalizacao_sem_acento(db_isolado):
    lid = _criar_lista()["id"]
    _oc(lid, "OC-1", itens=[{"descricao": "Agua Mineral", "quantidade": 2, "valor_total": 5.0}])
    _oc(lid, "OC-2", itens=[{"descricao": "Água Mineral", "quantidade": 3, "valor_total": 7.5}])
    lista = next(l for l in json.loads(repo.listar_listas_com_ocs()) if l["id"] == lid)
    assert len(lista["itens_agregados"]) == 1
    assert lista["itens_agregados"][0]["quantidade"] == pytest.approx(5.0)


def test_itens_diferentes_nao_somados(db_isolado):
    lid = _criar_lista()["id"]
    _oc(lid, "OC-1", itens=[{"descricao": "Arroz", "quantidade": 10, "valor_total": 50.0}])
    _oc(lid, "OC-2", itens=[{"descricao": "Feijão", "quantidade": 5, "valor_total": 25.0}])
    lista = next(l for l in json.loads(repo.listar_listas_com_ocs()) if l["id"] == lid)
    assert len(lista["itens_agregados"]) == 2


def test_lista_sem_ocs_tem_agregados_vazio(db_isolado):
    lid = _criar_lista()["id"]
    lista = next(l for l in json.loads(repo.listar_listas_com_ocs()) if l["id"] == lid)
    assert lista["itens_agregados"] == []


# ── Status por lista ──────────────────────────────────────────────────────────

def test_atualizar_status_lista(db_isolado):
    lid = _criar_lista()["id"]
    repo.atualizar_status_lista(json.dumps({"id": lid, "status_entrega": "entregue"}))
    lista = next(l for l in json.loads(repo.listar_listas_com_ocs()) if l["id"] == lid)
    assert lista["status_entrega"] == "entregue"


def test_atualizar_status_lista_retorna_ok(db_isolado):
    lid = _criar_lista()["id"]
    r = json.loads(repo.atualizar_status_lista(json.dumps({"id": lid, "status_entrega": "atrasada"})))
    assert r == {"ok": True}


# ── Exclusão de lista ─────────────────────────────────────────────────────────

def test_excluir_lista_remove_da_listagem(db_isolado):
    lid = _criar_lista()["id"]
    repo.excluir_lista(lid)
    listas = json.loads(repo.listar_listas_com_ocs())
    assert all(l["id"] != lid for l in listas)


def test_excluir_lista_ocs_ficam_orfas(db_isolado):
    lid   = _criar_lista()["id"]
    oc_id = _oc(lista_id=lid)
    repo.excluir_lista(lid)
    avulsas = json.loads(repo.listar_ocs_sem_lista())
    assert any(o["id"] == oc_id for o in avulsas)


def test_excluir_lista_retorna_ok(db_isolado):
    lid = _criar_lista()["id"]
    r = json.loads(repo.excluir_lista(lid))
    assert r == {"ok": True}


# ── Múltiplas listas independentes ───────────────────────────────────────────

def test_listas_isoladas(db_isolado):
    lid1 = _criar_lista()["id"]
    lid2 = _criar_lista()["id"]
    _oc(lid1, "OC-A", itens=[{"descricao": "Item X", "quantidade": 5, "valor_total": 10.0}])
    _oc(lid2, "OC-B", itens=[{"descricao": "Item X", "quantidade": 3, "valor_total": 6.0}])
    listas = json.loads(repo.listar_listas_com_ocs())
    l1 = next(l for l in listas if l["id"] == lid1)
    l2 = next(l for l in listas if l["id"] == lid2)
    # Cada lista soma apenas seus próprios itens
    assert l1["itens_agregados"][0]["quantidade"] == pytest.approx(5.0)
    assert l2["itens_agregados"][0]["quantidade"] == pytest.approx(3.0)
