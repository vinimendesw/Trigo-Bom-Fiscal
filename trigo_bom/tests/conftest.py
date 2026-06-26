"""
Camada 0 — Isolamento de estado.
Cada teste recebe um banco SQLite em diretório temporário único,
descartado automaticamente ao final. O banco real em %APPDATA% nunca é tocado.
"""
import os
import sys
import tempfile
import pytest

# Garante que `app/` está no path para todos os testes
APP_DIR = os.path.join(os.path.dirname(__file__), "..", "app")
sys.path.insert(0, os.path.abspath(APP_DIR))


@pytest.fixture()
def db_isolado(tmp_path, monkeypatch):
    """
    Redireciona o repositório para um banco temporário exclusivo deste teste.
    Usa monkeypatch para substituir _db_path sem alterar código de produção.
    """
    db_file = str(tmp_path / "trigo_bom_test.db")

    import db.repositorio as repo
    monkeypatch.setattr(repo, "_db_path", lambda: db_file)

    # Re-inicializa o schema e aplica migrações no banco temporário
    repo._inicializar()
    repo._migrar()

    yield db_file
