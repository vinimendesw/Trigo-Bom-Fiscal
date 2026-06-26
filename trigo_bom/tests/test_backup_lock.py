"""
Camada 1 — Testes de backup, restauração, lock e comparação de timestamps.
Todos os testes são isolados: nunca tocam %APPDATA% nem o banco real.
"""
import json
import shutil
import socket
from datetime import datetime, timedelta
from pathlib import Path
import pytest

import config as cfg
import backup as bkp


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def ambiente(tmp_path, monkeypatch):
    """
    Monta ambiente completamente isolado:
    - banco local em tmp_path/local/trigo_bom.db
    - pasta_backup em tmp_path/backup/
    - config apontando para essa pasta
    """
    local_dir = tmp_path / "local"
    local_dir.mkdir()
    db_local = local_dir / "trigo_bom.db"
    db_local.write_bytes(b"SQLITE_FAKE_LOCAL")

    backup_dir = tmp_path / "backup"
    backup_dir.mkdir()

    monkeypatch.setattr(cfg, "_config_path", lambda: tmp_path / "config.json")
    cfg.salvar_config({"pasta_backup": str(backup_dir)})
    monkeypatch.setattr(bkp, "_db_local", lambda: db_local)

    return {"db": db_local, "backup_dir": backup_dir}


# ── Backup ────────────────────────────────────────────────────────────────────

def test_fazer_backup_cria_arquivos(ambiente):
    ok = bkp.fazer_backup()
    assert ok is True
    assert (ambiente["backup_dir"] / "trigo_bom.db").exists()
    assert (ambiente["backup_dir"] / "trigo_bom_backup.json").exists()


def test_fazer_backup_copia_conteudo(ambiente):
    bkp.fazer_backup()
    conteudo = (ambiente["backup_dir"] / "trigo_bom.db").read_bytes()
    assert conteudo == b"SQLITE_FAKE_LOCAL"


def test_fazer_backup_grava_timestamp_no_meta(ambiente):
    antes = datetime.now()
    bkp.fazer_backup()
    meta = json.loads((ambiente["backup_dir"] / "trigo_bom_backup.json").read_text())
    ts = datetime.fromisoformat(meta["ts"])
    assert ts >= antes


def test_fazer_backup_retorna_false_sem_pasta_configurada(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "_config_path", lambda: tmp_path / "config.json")
    monkeypatch.setattr(bkp, "_db_local", lambda: tmp_path / "trigo_bom.db")
    (tmp_path / "trigo_bom.db").write_bytes(b"x")
    assert bkp.fazer_backup() is False


# ── Verificação de backup mais novo ──────────────────────────────────────────

def test_verificar_backup_retorna_none_sem_meta(ambiente):
    assert bkp.verificar_backup_mais_novo() is None


def test_verificar_backup_retorna_meta_quando_backup_e_mais_novo(ambiente):
    bkp.fazer_backup()

    # Faz o banco local parecer mais antigo manipulando mtime
    import os, time
    os.utime(ambiente["db"], (time.time() - 120, time.time() - 120))

    meta = bkp.verificar_backup_mais_novo()
    assert meta is not None
    assert "ts" in meta


def test_verificar_backup_retorna_none_quando_local_e_mais_novo(ambiente):
    bkp.fazer_backup()

    # Grava meta com timestamp antigo
    meta_antigo = {"ts": (datetime.now() - timedelta(hours=2)).isoformat(), "hostname": "outro"}
    (ambiente["backup_dir"] / "trigo_bom_backup.json").write_text(
        json.dumps(meta_antigo), encoding="utf-8"
    )

    assert bkp.verificar_backup_mais_novo() is None


# ── Restauração ───────────────────────────────────────────────────────────────

def test_restaurar_backup_sobrescreve_banco_local(ambiente):
    # Grava backup diferente
    (ambiente["backup_dir"] / "trigo_bom.db").write_bytes(b"SQLITE_BACKUP")
    meta = {"ts": datetime.now().isoformat(), "hostname": socket.gethostname()}
    (ambiente["backup_dir"] / "trigo_bom_backup.json").write_text(json.dumps(meta))

    ok = bkp.restaurar_backup()
    assert ok is True
    assert ambiente["db"].read_bytes() == b"SQLITE_BACKUP"


# ── Lock ──────────────────────────────────────────────────────────────────────

def test_gravar_lock_cria_arquivo(ambiente):
    bkp.gravar_lock()
    assert (ambiente["backup_dir"] / "trigo_bom.lock").exists()


def test_lock_contem_hostname_e_timestamp(ambiente):
    bkp.gravar_lock()
    info = json.loads((ambiente["backup_dir"] / "trigo_bom.lock").read_text())
    assert info["hostname"] == socket.gethostname()
    assert "ts" in info


def test_verificar_lock_retorna_none_para_proprio_host(ambiente):
    bkp.gravar_lock()
    assert bkp.verificar_lock() is None  # mesmo hostname → não bloqueia


def test_verificar_lock_detecta_outro_host(ambiente):
    lock_info = {"hostname": "outro-computador", "ts": datetime.now().isoformat()}
    (ambiente["backup_dir"] / "trigo_bom.lock").write_text(json.dumps(lock_info))
    resultado = bkp.verificar_lock()
    assert resultado is not None
    assert resultado["hostname"] == "outro-computador"


def test_verificar_lock_ignora_lock_expirado(ambiente):
    ts_antigo = (datetime.now() - timedelta(hours=bkp.LOCK_MAX_H + 1)).isoformat()
    lock_info = {"hostname": "outro-computador", "ts": ts_antigo}
    (ambiente["backup_dir"] / "trigo_bom.lock").write_text(json.dumps(lock_info))
    assert bkp.verificar_lock() is None


def test_remover_lock_apaga_arquivo(ambiente):
    bkp.gravar_lock()
    bkp.remover_lock()
    assert not (ambiente["backup_dir"] / "trigo_bom.lock").exists()


def test_remover_lock_sem_arquivo_nao_falha(ambiente):
    bkp.remover_lock()  # não deve lançar exceção
