"""
Backup do banco SQLite, restauracao e lock de uso simultaneo.

Estrategia (secao 12 do CLAUDE.md):
- O banco de trabalho vive em APPDATA/TrigoBom/trigo_bom.db (nunca na pasta do usuario).
- A cada escrita relevante o app copia o banco para pasta_backup como trigo_bom.db,
  gravando um metadado trigo_bom_backup.json com timestamp e hostname.
- Ao abrir, compara o timestamp do metadado com o mtime do banco local; se o backup
  for mais novo, oferece restauracao.
- Lock: ao abrir grava trigo_bom.lock; ao fechar remove. Locks de mais de LOCK_MAX_H
  horas sao considerados expirados.
"""

import json
import shutil
import socket
from datetime import datetime
from pathlib import Path

LOCK_MAX_H = 8  # horas até um lock ser considerado expirado


# ── Caminhos ──────────────────────────────────────────────────────────────────

def _db_local() -> Path:
    from db.repositorio import _db_path
    return Path(_db_path())


def _backup_dir() -> Path | None:
    from config import pasta_valida
    p = pasta_valida("pasta_backup")
    return Path(p) if p else None


# ── Backup ────────────────────────────────────────────────────────────────────

def fazer_backup() -> bool:
    """Copia banco local para pasta_backup. Retorna True se bem-sucedido."""
    d = _backup_dir()
    if not d:
        return False
    src = _db_local()
    if not src.exists():
        return False
    try:
        shutil.copy2(src, d / "trigo_bom.db")
        meta = {
            "ts": datetime.now().isoformat(),
            "hostname": socket.gethostname(),
        }
        (d / "trigo_bom_backup.json").write_text(
            json.dumps(meta, ensure_ascii=False), encoding="utf-8"
        )
        return True
    except Exception:
        return False


def verificar_backup_mais_novo() -> dict | None:
    """
    Retorna o dict do metadado do backup se ele for mais novo que o banco local.
    Retorna None se não há backup configurado, ou se o banco local é mais recente.
    """
    d = _backup_dir()
    if not d:
        return None
    meta_path = d / "trigo_bom_backup.json"
    backup_db = d / "trigo_bom.db"
    if not meta_path.exists() or not backup_db.exists():
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        ts_backup = datetime.fromisoformat(meta["ts"])
    except Exception:
        return None

    local = _db_local()
    if not local.exists():
        return meta  # banco local não existe → sempre restaurar

    ts_local = datetime.fromtimestamp(local.stat().st_mtime)
    return meta if ts_backup > ts_local else None


def restaurar_backup() -> bool:
    """Sobrescreve o banco local com o backup. Retorna True se bem-sucedido."""
    d = _backup_dir()
    if not d:
        return False
    backup_db = d / "trigo_bom.db"
    if not backup_db.exists():
        return False
    try:
        shutil.copy2(backup_db, _db_local())
        return True
    except Exception:
        return False


# ── Lock ──────────────────────────────────────────────────────────────────────

def _lock_path() -> Path | None:
    d = _backup_dir()
    return (d / "trigo_bom.lock") if d else None


def gravar_lock() -> None:
    p = _lock_path()
    if not p:
        return
    try:
        p.write_text(
            json.dumps({"hostname": socket.gethostname(), "ts": datetime.now().isoformat()}),
            encoding="utf-8",
        )
    except Exception:
        pass


def verificar_lock() -> dict | None:
    """
    Retorna info do lock se for de outro dispositivo e não expirado.
    Retorna None se não há lock, se é deste dispositivo, ou se expirou.
    """
    p = _lock_path()
    if not p or not p.exists():
        return None
    try:
        info = json.loads(p.read_text(encoding="utf-8"))
        ts = datetime.fromisoformat(info["ts"])
    except Exception:
        return None

    horas = (datetime.now() - ts).total_seconds() / 3600
    if horas > LOCK_MAX_H:
        return None  # expirado — ignora
    if info.get("hostname") == socket.gethostname():
        return None  # é o próprio dispositivo
    return info


def remover_lock() -> None:
    p = _lock_path()
    if p:
        try:
            p.unlink(missing_ok=True)
        except Exception:
            pass
