"""
Camada 1 — Testes das novas funcionalidades:
  - Filtros de NF (listar_nfs com filtros)
  - Marcação em massa como paga
  - Totais de NF por órgão (para o gráfico de pizza do dashboard)
  - OCs com itens aninhados (listar_ordens_compra_com_itens)
  - Migração: remoção das tabelas de licitação
"""
import json
import sqlite3
import pytest
import db.repositorio as repo


# ─── Fixtures auxiliares ──────────────────────────────────────────────────────

def _nf(orgao_id=1, categoria="Alimentícios", status="nao_pago",
        data="2026-06-15", valor=100.0):
    return json.dumps({
        "orgao_id": orgao_id, "categoria": categoria,
        "status_pagamento": status, "data_emissao": data,
        "valor": valor,
    })


# ─── Filtros de NF ────────────────────────────────────────────────────────────

def test_filtro_por_orgao(db_isolado):
    repo.salvar_nf(_nf(orgao_id=1))
    repo.salvar_nf(_nf(orgao_id=2))
    r = json.loads(repo.listar_nfs(json.dumps({"orgao_id": 1})))
    assert len(r) == 1
    assert r[0]["orgao_id"] == 1


def test_filtro_por_categoria(db_isolado):
    repo.salvar_nf(_nf(categoria="Limpeza"))
    repo.salvar_nf(_nf(categoria="Alimentícios"))
    r = json.loads(repo.listar_nfs(json.dumps({"categoria": "Limpeza"})))
    assert len(r) == 1
    assert r[0]["categoria"] == "Limpeza"


def test_filtro_por_status_pago(db_isolado):
    repo.salvar_nf(_nf(status="pago"))
    repo.salvar_nf(_nf(status="nao_pago"))
    r = json.loads(repo.listar_nfs(json.dumps({"status": "pago"})))
    assert len(r) == 1
    assert r[0]["status_pagamento"] == "pago"


def test_filtro_por_mes_ano(db_isolado):
    repo.salvar_nf(_nf(data="2026-06-10"))
    repo.salvar_nf(_nf(data="2026-05-10"))
    r = json.loads(repo.listar_nfs(json.dumps({"mes": 6, "ano": 2026})))
    assert len(r) == 1
    assert r[0]["data_emissao"] == "2026-06-10"


def test_filtro_combinado(db_isolado):
    repo.salvar_nf(_nf(orgao_id=1, categoria="Limpeza", data="2026-06-01"))
    repo.salvar_nf(_nf(orgao_id=2, categoria="Limpeza", data="2026-06-01"))
    repo.salvar_nf(_nf(orgao_id=1, categoria="Alimentícios", data="2026-06-01"))
    r = json.loads(repo.listar_nfs(json.dumps({"orgao_id": 1, "categoria": "Limpeza"})))
    assert len(r) == 1


def test_filtro_vazio_retorna_tudo(db_isolado):
    for _ in range(3):
        repo.salvar_nf(_nf())
    r = json.loads(repo.listar_nfs("{}"))
    assert len(r) == 3


# ─── Marcação em massa ────────────────────────────────────────────────────────

def test_marcar_pagas_em_massa_atualiza_status(db_isolado):
    ids = [json.loads(repo.salvar_nf(_nf(status="nao_pago")))["id"] for _ in range(3)]
    repo.marcar_pagas_em_massa(json.dumps({"ids": ids, "data_pagamento": "2026-06-26"}))
    nfs = json.loads(repo.listar_nfs())
    assert all(nf["status_pagamento"] == "pago" for nf in nfs)


def test_marcar_pagas_em_massa_preenche_data(db_isolado):
    id1 = json.loads(repo.salvar_nf(_nf()))["id"]
    repo.marcar_pagas_em_massa(json.dumps({"ids": [id1], "data_pagamento": "2026-06-26"}))
    nf = json.loads(repo.listar_nfs())[0]
    assert nf["data_pagamento"] == "2026-06-26"


def test_marcar_pagas_em_massa_nao_afeta_nao_selecionadas(db_isolado):
    id1 = json.loads(repo.salvar_nf(_nf()))["id"]
    id2 = json.loads(repo.salvar_nf(_nf()))["id"]
    repo.marcar_pagas_em_massa(json.dumps({"ids": [id1], "data_pagamento": "2026-06-26"}))
    nfs = json.loads(repo.listar_nfs())
    por_id = {n["id"]: n for n in nfs}
    assert por_id[id1]["status_pagamento"] == "pago"
    assert por_id[id2]["status_pagamento"] == "nao_pago"


def test_marcar_pagas_em_massa_lista_vazia_ok(db_isolado):
    r = json.loads(repo.marcar_pagas_em_massa(json.dumps({"ids": [], "data_pagamento": "2026-06-26"})))
    assert r["ok"] is True
    assert r["atualizadas"] == 0


def test_marcar_pagas_em_massa_retorna_contagem(db_isolado):
    ids = [json.loads(repo.salvar_nf(_nf()))["id"] for _ in range(5)]
    r = json.loads(repo.marcar_pagas_em_massa(json.dumps({"ids": ids, "data_pagamento": "2026-06-26"})))
    assert r["atualizadas"] == 5


# ─── Totais por órgão (dashboard — gráfico de pizza) ─────────────────────────

def test_totais_por_orgao_retorna_4_orgaos(db_isolado):
    r = json.loads(repo.totais_nf_por_orgao(6, 2026))
    assert len(r) == 4


def test_totais_por_orgao_zero_sem_nfs(db_isolado):
    r = json.loads(repo.totais_nf_por_orgao(6, 2026))
    assert all(row["total"] == 0 for row in r)


def test_totais_por_orgao_soma_correta(db_isolado):
    repo.salvar_nf(_nf(orgao_id=1, valor=200.0, data="2026-06-10"))
    repo.salvar_nf(_nf(orgao_id=1, valor=300.0, data="2026-06-15"))
    repo.salvar_nf(_nf(orgao_id=2, valor=150.0, data="2026-06-20"))
    r = json.loads(repo.totais_nf_por_orgao(6, 2026))
    por_id = {row["orgao_id"]: row["total"] for row in r}
    assert por_id[1] == pytest.approx(500.0)
    assert por_id[2] == pytest.approx(150.0)
    assert por_id[3] == pytest.approx(0.0)


def test_totais_por_orgao_filtra_por_mes(db_isolado):
    repo.salvar_nf(_nf(orgao_id=1, valor=100.0, data="2026-06-10"))
    repo.salvar_nf(_nf(orgao_id=1, valor=999.0, data="2026-05-10"))  # mês errado
    r = json.loads(repo.totais_nf_por_orgao(6, 2026))
    por_id = {row["orgao_id"]: row["total"] for row in r}
    assert por_id[1] == pytest.approx(100.0)


def test_totais_por_orgao_tem_nome_do_orgao(db_isolado):
    r = json.loads(repo.totais_nf_por_orgao(6, 2026))
    nomes = {row["orgao_nome"] for row in r}
    assert "Administração" in nomes
    assert "Saúde" in nomes


# ─── OCs com itens aninhados ─────────────────────────────────────────────────

def test_listar_ocs_com_itens_retorna_lista(db_isolado):
    assert isinstance(json.loads(repo.listar_ordens_compra_com_itens()), list)


def test_ocs_com_itens_aninha_corretamente(db_isolado):
    repo.salvar_ordem_compra(json.dumps({
        "numero": "OC-1",
        "itens": [
            {"descricao": "Arroz", "quantidade": 10, "valor_unitario": 5.0, "valor_total": 50.0},
            {"descricao": "Feijão", "quantidade": 5, "valor_unitario": 8.0, "valor_total": 40.0},
        ]
    }))
    ocs = json.loads(repo.listar_ordens_compra_com_itens())
    assert len(ocs) == 1
    assert len(ocs[0]["itens"]) == 2
    assert ocs[0]["itens"][0]["descricao"] == "Arroz"


def test_ocs_com_itens_sem_itens_retorna_lista_vazia(db_isolado):
    repo.salvar_ordem_compra(json.dumps({"numero": "OC-vazia", "itens": []}))
    ocs = json.loads(repo.listar_ordens_compra_com_itens())
    assert ocs[0]["itens"] == []


def test_ocs_com_itens_multiplas_ocs_isoladas(db_isolado):
    repo.salvar_ordem_compra(json.dumps({
        "numero": "OC-A",
        "itens": [{"descricao": "Item A1"}]
    }))
    repo.salvar_ordem_compra(json.dumps({
        "numero": "OC-B",
        "itens": [{"descricao": "Item B1"}, {"descricao": "Item B2"}]
    }))
    ocs = json.loads(repo.listar_ordens_compra_com_itens())
    por_num = {o["numero"]: o for o in ocs}
    assert len(por_num["OC-A"]["itens"]) == 1
    assert len(por_num["OC-B"]["itens"]) == 2


# ─── Migração: tabelas de licitação removidas ─────────────────────────────────

def test_migracao_remove_tabela_licitacoes(db_isolado):
    with sqlite3.connect(db_isolado) as conn:
        tabelas = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
    assert "licitacoes" not in tabelas
    assert "itens_licitacao" not in tabelas
    assert "movimentos_licitacao" not in tabelas


def test_migracao_idempotente(db_isolado):
    repo._migrar()
    repo._migrar()  # segunda chamada não deve lançar exceção
