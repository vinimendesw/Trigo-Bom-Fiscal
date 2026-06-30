"""
Camada 1 — Testes de exclusão de NF (individual e em massa).
Confirma:
  - registro excluído do banco
  - itens em cascata removidos (ON DELETE CASCADE)
  - cópia gerenciada (dentro da Pasta de NFs) removida do disco
  - arquivo ORIGINAL do usuário (fora da pasta gerenciada) preservado
  - falha na remoção do arquivo não impede a exclusão do registro
"""
import json
import os
from pathlib import Path
import pytest
import config
import db.repositorio as repo


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def config_temp(tmp_path, monkeypatch):
    """Isola a config num arquivo temporário, para os testes nunca lerem a Pasta
    de NFs real do %APPDATA% da máquina de desenvolvimento."""
    monkeypatch.setattr(config, "_config_path", lambda: tmp_path / "config.json")
    return tmp_path


@pytest.fixture()
def pasta_nfs(config_temp):
    """Configura uma Pasta de NFs gerenciada (isolada) e retorna seu Path."""
    pasta = config_temp / "gerenciada_nfs"
    pasta.mkdir()
    config.salvar_config({"pasta_nfs": str(pasta)})
    return pasta


def _nf_com_arquivo(tmp_path, sufixo="01", pasta=None):
    """Cria um PDF (dentro de `pasta`, se dada; senão em tmp_path) e salva uma
    NF apontando para ele."""
    destino = Path(pasta) if pasta is not None else Path(tmp_path)
    pdf = destino / f"nf_{sufixo}.pdf"
    pdf.write_bytes(b"PDF_FAKE")
    nf_id = json.loads(repo.salvar_nf(json.dumps({
        "numero": sufixo,
        "orgao_id": 1,
        "valor": 100.0,
        "status_pagamento": "nao_pago",
        "origem": "pdf",
        "arquivo_pdf": str(pdf),
        "itens": [
            {"descricao": "Item A", "quantidade": 1, "valor_unitario": 50.0, "valor_total": 50.0},
            {"descricao": "Item B", "quantidade": 2, "valor_unitario": 25.0, "valor_total": 50.0},
        ],
    })))["id"]
    return nf_id, pdf


# ── Exclusão individual ───────────────────────────────────────────────────────

def test_excluir_nf_remove_registro(db_isolado, tmp_path):
    nf_id, _ = _nf_com_arquivo(tmp_path)
    repo.excluir_nf(nf_id)
    nfs = json.loads(repo.listar_nfs())
    assert all(nf["id"] != nf_id for nf in nfs)


def test_excluir_nf_retorna_ok(db_isolado, tmp_path):
    nf_id, _ = _nf_com_arquivo(tmp_path)
    r = json.loads(repo.excluir_nf(nf_id))
    assert r == {"ok": True}


def test_excluir_nf_remove_itens_em_cascata(db_isolado, tmp_path):
    nf_id, _ = _nf_com_arquivo(tmp_path)
    repo.excluir_nf(nf_id)
    itens = json.loads(repo.listar_itens_nf(nf_id))
    assert itens == []


def test_excluir_nf_remove_copia_gerenciada(db_isolado, tmp_path, pasta_nfs):
    # Arquivo DENTRO da Pasta de NFs configurada → é a cópia gerenciada, apagável.
    nf_id, pdf = _nf_com_arquivo(tmp_path, pasta=pasta_nfs)
    assert pdf.exists()
    repo.excluir_nf(nf_id)
    assert not pdf.exists()


def test_excluir_nf_preserva_original_fora_da_pasta(db_isolado, tmp_path, pasta_nfs):
    # Arquivo FORA da Pasta de NFs (original do usuário) → nunca é apagado, mesmo
    # com a pasta configurada.
    nf_id, pdf = _nf_com_arquivo(tmp_path)  # em tmp_path, fora de pasta_nfs
    assert pdf.exists()
    repo.excluir_nf(nf_id)
    assert pdf.exists()


def test_excluir_nf_sem_pasta_configurada_preserva_original(db_isolado, tmp_path, config_temp):
    # Sem Pasta de NFs configurada, arquivo_pdf aponta para o original → preservar.
    nf_id, pdf = _nf_com_arquivo(tmp_path)
    assert pdf.exists()
    repo.excluir_nf(nf_id)
    assert pdf.exists()


def test_excluir_nf_sem_arquivo_nao_falha(db_isolado, tmp_path):
    nf_id = json.loads(repo.salvar_nf(json.dumps({
        "numero": "X", "valor": 50.0, "status_pagamento": "nao_pago",
        "arquivo_pdf": "",
    })))["id"]
    r = json.loads(repo.excluir_nf(nf_id))
    assert r == {"ok": True}


def test_excluir_nf_arquivo_ja_removido_nao_falha(db_isolado, tmp_path):
    nf_id, pdf = _nf_com_arquivo(tmp_path)
    pdf.unlink()  # remove antes de excluir a NF
    r = json.loads(repo.excluir_nf(nf_id))
    assert r == {"ok": True}


def test_excluir_nf_nao_afeta_outras_nfs(db_isolado, tmp_path):
    id1, _ = _nf_com_arquivo(tmp_path, "01")
    id2, _ = _nf_com_arquivo(tmp_path, "02")
    repo.excluir_nf(id1)
    nfs = json.loads(repo.listar_nfs())
    assert any(nf["id"] == id2 for nf in nfs)


# ── Exclusão em massa ─────────────────────────────────────────────────────────

def test_excluir_em_massa_remove_registros(db_isolado, tmp_path):
    ids = [_nf_com_arquivo(tmp_path, str(i))[0] for i in range(3)]
    repo.excluir_nfs_em_massa(json.dumps({"ids": ids}))
    nfs = json.loads(repo.listar_nfs())
    assert all(nf["id"] not in ids for nf in nfs)


def test_excluir_em_massa_retorna_quantidade(db_isolado, tmp_path):
    ids = [_nf_com_arquivo(tmp_path, str(i))[0] for i in range(3)]
    r = json.loads(repo.excluir_nfs_em_massa(json.dumps({"ids": ids})))
    assert r["ok"] is True
    assert r["excluidas"] == 3


def test_excluir_em_massa_remove_copias_gerenciadas(db_isolado, tmp_path, pasta_nfs):
    pares = [_nf_com_arquivo(tmp_path, str(i), pasta=pasta_nfs) for i in range(2)]
    ids  = [p[0] for p in pares]
    pdfs = [p[1] for p in pares]
    assert all(p.exists() for p in pdfs)
    repo.excluir_nfs_em_massa(json.dumps({"ids": ids}))
    assert all(not p.exists() for p in pdfs)


def test_excluir_em_massa_preserva_originais_fora_da_pasta(db_isolado, tmp_path, pasta_nfs):
    pares = [_nf_com_arquivo(tmp_path, str(i)) for i in range(2)]  # fora da pasta
    ids  = [p[0] for p in pares]
    pdfs = [p[1] for p in pares]
    repo.excluir_nfs_em_massa(json.dumps({"ids": ids}))
    assert all(p.exists() for p in pdfs)


def test_excluir_em_massa_remove_itens_em_cascata(db_isolado, tmp_path):
    ids = [_nf_com_arquivo(tmp_path, str(i))[0] for i in range(2)]
    repo.excluir_nfs_em_massa(json.dumps({"ids": ids}))
    for nf_id in ids:
        assert json.loads(repo.listar_itens_nf(nf_id)) == []


def test_excluir_em_massa_lista_vazia_ok(db_isolado):
    r = json.loads(repo.excluir_nfs_em_massa(json.dumps({"ids": []})))
    assert r["ok"] is True
    assert r["excluidas"] == 0


def test_excluir_em_massa_nao_afeta_nao_selecionadas(db_isolado, tmp_path):
    id1, _ = _nf_com_arquivo(tmp_path, "01")
    id2, _ = _nf_com_arquivo(tmp_path, "02")
    repo.excluir_nfs_em_massa(json.dumps({"ids": [id1]}))
    nfs = json.loads(repo.listar_nfs())
    assert any(nf["id"] == id2 for nf in nfs)
