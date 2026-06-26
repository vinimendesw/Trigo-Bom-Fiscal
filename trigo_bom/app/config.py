import json
import os
from pathlib import Path

CHAVES = ["pasta_nfs", "pasta_ordens_compra", "pasta_backup"]


def _config_path() -> Path:
    data_dir = Path(os.environ.get("APPDATA", Path.home())) / "TrigoBom"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "config.json"


def carregar_config() -> dict:
    p = _config_path()
    if p.exists():
        try:
            dados = json.loads(p.read_text(encoding="utf-8"))
            return {k: dados.get(k, "") for k in CHAVES}
        except Exception:
            pass
    return {k: "" for k in CHAVES}


def salvar_config(dados: dict) -> None:
    p = _config_path()
    atual = carregar_config()
    for k in CHAVES:
        if k in dados:
            atual[k] = dados[k]
    p.write_text(json.dumps(atual, ensure_ascii=False, indent=2), encoding="utf-8")


def pasta_valida(chave: str) -> str | None:
    """Retorna o caminho da pasta se estiver configurada e existir, senão None."""
    cfg = carregar_config()
    p = cfg.get(chave, "")
    if p and Path(p).is_dir():
        return p
    return None
