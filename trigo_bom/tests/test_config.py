"""Camada 1 — Testes de leitura/escrita de configuração de pastas."""
import json
import pytest
import config as cfg


@pytest.fixture()
def config_isolado(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "_config_path", lambda: tmp_path / "config.json")
    yield tmp_path / "config.json"


def test_config_padrao_retorna_chaves_vazias(config_isolado):
    c = cfg.carregar_config()
    assert set(c.keys()) == set(cfg.CHAVES)
    assert all(v == "" for v in c.values())


def test_pasta_licitacoes_nao_existe_mais(config_isolado):
    assert "pasta_licitacoes" not in cfg.CHAVES


def test_salvar_e_recarregar_config(config_isolado):
    cfg.salvar_config({"pasta_nfs": "/tmp/nfs", "pasta_backup": "/tmp/bkp"})
    c = cfg.carregar_config()
    assert c["pasta_nfs"] == "/tmp/nfs"
    assert c["pasta_backup"] == "/tmp/bkp"
    assert c["pasta_ordens_compra"] == ""


def test_salvar_config_atualiza_parcialmente(config_isolado):
    cfg.salvar_config({"pasta_nfs": "/a"})
    cfg.salvar_config({"pasta_backup": "/b"})
    c = cfg.carregar_config()
    assert c["pasta_nfs"] == "/a"
    assert c["pasta_backup"] == "/b"


def test_config_json_bem_formado(config_isolado):
    cfg.salvar_config({"pasta_backup": "/bkp"})
    parsed = json.loads(config_isolado.read_text(encoding="utf-8"))
    assert parsed["pasta_backup"] == "/bkp"


def test_config_ignora_chaves_desconhecidas(config_isolado):
    cfg.salvar_config({"chave_invalida": "x", "pasta_nfs": "/nfs"})
    c = cfg.carregar_config()
    assert "chave_invalida" not in c
    assert c["pasta_nfs"] == "/nfs"


def test_pasta_valida_retorna_none_se_vazia(config_isolado):
    assert cfg.pasta_valida("pasta_nfs") is None


def test_pasta_valida_retorna_none_se_nao_existe(config_isolado, tmp_path):
    cfg.salvar_config({"pasta_nfs": str(tmp_path / "inexistente")})
    assert cfg.pasta_valida("pasta_nfs") is None


def test_pasta_valida_retorna_caminho_se_existe(config_isolado, tmp_path):
    pasta = tmp_path / "nfs"
    pasta.mkdir()
    cfg.salvar_config({"pasta_nfs": str(pasta)})
    assert cfg.pasta_valida("pasta_nfs") == str(pasta)
