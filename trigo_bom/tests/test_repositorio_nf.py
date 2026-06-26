"""
Camada 1 — Testes unitários do repositório: Notas Fiscais.
"""
import json
import pytest
import db.repositorio as repo


def test_listar_nfs_vazio(db_isolado):
    assert json.loads(repo.listar_nfs()) == []


def test_salvar_e_listar_nf(db_isolado):
    dados = {
        "numero": "001",
        "orgao_id": 1,
        "data_emissao": "2026-01-15",
        "valor": 1500.00,
        "categoria": "Alimentícios",
        "status_pagamento": "nao_pago",
        "data_vencimento": "2026-02-15",
        "data_pagamento": None,
        "arquivo_pdf": "/tmp/nf001.pdf",
    }
    resultado = json.loads(repo.salvar_nf(json.dumps(dados)))
    assert "id" in resultado
    assert resultado["id"] == 1

    nfs = json.loads(repo.listar_nfs())
    assert len(nfs) == 1
    assert nfs[0]["numero"] == "001"
    assert nfs[0]["valor"] == pytest.approx(1500.00)
    assert nfs[0]["orgao_nome"] == "Administração"


def test_salvar_multiplas_nfs(db_isolado):
    for i in range(1, 4):
        repo.salvar_nf(json.dumps({
            "numero": str(i),
            "orgao_id": i,
            "valor": float(i * 100),
            "status_pagamento": "nao_pago",
        }))
    nfs = json.loads(repo.listar_nfs())
    assert len(nfs) == 3


def test_atualizar_status_nf_para_pago(db_isolado):
    id_nf = json.loads(repo.salvar_nf(json.dumps({
        "numero": "002",
        "orgao_id": 2,
        "valor": 200.0,
        "status_pagamento": "nao_pago",
    })))["id"]

    repo.atualizar_status_nf(json.dumps({
        "id": id_nf,
        "status_pagamento": "pago",
        "data_pagamento": "2026-02-01",
    }))

    nfs = json.loads(repo.listar_nfs())
    assert nfs[0]["status_pagamento"] == "pago"
    assert nfs[0]["data_pagamento"] == "2026-02-01"


def test_nf_campos_opcionais_aceitos_como_none(db_isolado):
    resultado = json.loads(repo.salvar_nf(json.dumps({
        "numero": None,
        "orgao_id": None,
        "valor": None,
        "status_pagamento": "nao_pago",
    })))
    assert "id" in resultado
