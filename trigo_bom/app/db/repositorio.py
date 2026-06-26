import json
import os
import sqlite3
from pathlib import Path


def _db_path() -> str:
    data_dir = Path(os.environ.get("APPDATA", Path.home())) / "TrigoBom"
    data_dir.mkdir(parents=True, exist_ok=True)
    return str(data_dir / "trigo_bom.db")


def _conectar() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _inicializar():
    schema = Path(__file__).parent / "schema.sql"
    with _conectar() as conn:
        conn.executescript(schema.read_text(encoding="utf-8"))


def _migrar():
    """Aplica migrações incrementais sem quebrar bancos já existentes."""
    with _conectar() as conn:
        # Remove tabelas de licitação (funcionalidade removida em 2026-06-26)
        conn.executescript("""
            DROP TABLE IF EXISTS movimentos_licitacao;
            DROP TABLE IF EXISTS itens_licitacao;
            DROP TABLE IF EXISTS licitacoes;
        """)

        # Adiciona coluna origem em notas_fiscais se não existir
        colunas = [r[1] for r in conn.execute("PRAGMA table_info(notas_fiscais)").fetchall()]
        if "origem" not in colunas:
            conn.execute("ALTER TABLE notas_fiscais ADD COLUMN origem TEXT")

        # Cria itens_nota_fiscal se não existir
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS itens_nota_fiscal (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                nota_fiscal_id  INTEGER REFERENCES notas_fiscais(id) ON DELETE CASCADE,
                descricao       TEXT,
                quantidade      REAL,
                valor_unitario  REAL,
                valor_total     REAL,
                ncm             TEXT,
                cfop            TEXT
            );
        """)


_inicializar()
_migrar()


# ── Notas Fiscais ────────────────────────────────────────────────────────────

def salvar_nf(dados_json: str) -> str:
    """
    Salva NF e seus itens em transação única.
    Campos: numero, orgao_id, data_emissao, valor, categoria, status_pagamento,
    data_vencimento, data_pagamento, arquivo_pdf, origem,
    itens (lista opcional: descricao, quantidade, valor_unitario, valor_total, ncm, cfop).
    """
    d = json.loads(dados_json)
    with _conectar() as conn:
        cur = conn.execute(
            """INSERT INTO notas_fiscais
               (numero, orgao_id, data_emissao, valor, categoria,
                status_pagamento, data_vencimento, data_pagamento, arquivo_pdf, origem)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (d.get("numero"), d.get("orgao_id"), d.get("data_emissao"),
             d.get("valor"), d.get("categoria"), d.get("status_pagamento", "nao_pago"),
             d.get("data_vencimento"), d.get("data_pagamento"),
             d.get("arquivo_pdf"), d.get("origem")),
        )
        nf_id = cur.lastrowid
        for item in d.get("itens", []):
            conn.execute(
                """INSERT INTO itens_nota_fiscal
                   (nota_fiscal_id, descricao, quantidade, valor_unitario,
                    valor_total, ncm, cfop)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (nf_id, item.get("descricao"), item.get("quantidade"),
                 item.get("valor_unitario"), item.get("valor_total"),
                 item.get("ncm"), item.get("cfop")),
            )
        return json.dumps({"id": nf_id})


def listar_nfs(filtros_json: str = "{}") -> str:
    """
    Retorna todas as NFs com JOIN de órgão.
    filtros: { orgao_id, categoria, status, mes, ano } — todos opcionais.
    """
    f = json.loads(filtros_json) if filtros_json else {}
    where, params = [], []

    if f.get("orgao_id"):
        where.append("nf.orgao_id = ?")
        params.append(int(f["orgao_id"]))
    if f.get("categoria"):
        where.append("nf.categoria = ?")
        params.append(f["categoria"])
    if f.get("status"):
        where.append("nf.status_pagamento = ?")
        params.append(f["status"])
    if f.get("mes") and f.get("ano"):
        where.append("strftime('%Y-%m', nf.data_emissao) = ?")
        params.append(f"{int(f['ano']):04d}-{int(f['mes']):02d}")

    sql = (
        "SELECT nf.*, o.nome AS orgao_nome FROM notas_fiscais nf "
        "LEFT JOIN orgaos o ON o.id = nf.orgao_id"
    )
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY nf.data_emissao DESC"

    with _conectar() as conn:
        rows = conn.execute(sql, params).fetchall()
        return json.dumps([dict(r) for r in rows], ensure_ascii=False)


def listar_itens_nf(nota_fiscal_id: int) -> str:
    with _conectar() as conn:
        rows = conn.execute(
            "SELECT * FROM itens_nota_fiscal WHERE nota_fiscal_id=?",
            (nota_fiscal_id,),
        ).fetchall()
        return json.dumps([dict(r) for r in rows], ensure_ascii=False)


def atualizar_status_nf(dados_json: str) -> str:
    d = json.loads(dados_json)
    with _conectar() as conn:
        conn.execute(
            "UPDATE notas_fiscais SET status_pagamento=?, data_pagamento=? WHERE id=?",
            (d["status_pagamento"], d.get("data_pagamento"), d["id"]),
        )
        return json.dumps({"ok": True})


def marcar_pagas_em_massa(dados_json: str) -> str:
    """
    Marca uma lista de NFs como pagas em transação única.
    dados: { ids: [int, ...], data_pagamento: str }
    """
    d = json.loads(dados_json)
    ids = d.get("ids", [])
    data = d.get("data_pagamento", "")
    if not ids:
        return json.dumps({"ok": True, "atualizadas": 0})
    with _conectar() as conn:
        placeholders = ",".join("?" * len(ids))
        conn.execute(
            f"UPDATE notas_fiscais SET status_pagamento='pago', data_pagamento=? "
            f"WHERE id IN ({placeholders})",
            [data] + list(ids),
        )
        return json.dumps({"ok": True, "atualizadas": len(ids)})


def totais_nf_por_orgao(mes: int, ano: int) -> str:
    """
    Retorna o total de valor de NFs por órgão para o mês/ano indicados.
    Resultado: [{ orgao_id, orgao_nome, total }]
    """
    periodo = f"{ano:04d}-{mes:02d}"
    with _conectar() as conn:
        rows = conn.execute(
            """SELECT o.id AS orgao_id, o.nome AS orgao_nome,
                      COALESCE(SUM(nf.valor), 0) AS total
               FROM orgaos o
               LEFT JOIN notas_fiscais nf
                 ON nf.orgao_id = o.id
                 AND strftime('%Y-%m', nf.data_emissao) = ?
               GROUP BY o.id, o.nome
               ORDER BY o.id""",
            (periodo,),
        ).fetchall()
        return json.dumps([dict(r) for r in rows], ensure_ascii=False)


# ── Ordens de Compra ─────────────────────────────────────────────────────────

def salvar_ordem_compra(dados_json: str) -> str:
    d = json.loads(dados_json)
    with _conectar() as conn:
        cur = conn.execute(
            """INSERT INTO ordens_compra
               (numero, fornecedor, data_emissao, data_entrega_prevista, arquivo_pdf)
               VALUES (?, ?, ?, ?, ?)""",
            (d.get("numero"), d.get("fornecedor"), d.get("data_emissao"),
             d.get("data_entrega_prevista"), d.get("arquivo_pdf")),
        )
        oc_id = cur.lastrowid
        for item in d.get("itens", []):
            conn.execute(
                """INSERT INTO itens_ordem_compra
                   (ordem_compra_id, descricao, quantidade, valor_unitario, valor_total)
                   VALUES (?, ?, ?, ?, ?)""",
                (oc_id, item.get("descricao"), item.get("quantidade"),
                 item.get("valor_unitario"), item.get("valor_total")),
            )
        return json.dumps({"id": oc_id})


def listar_ordens_compra_com_itens() -> str:
    """Retorna OCs com seus itens aninhados num único payload."""
    with _conectar() as conn:
        ocs = {r["id"]: dict(r) | {"itens": []}
               for r in conn.execute("SELECT * FROM ordens_compra ORDER BY data_entrega_prevista").fetchall()}
        for r in conn.execute(
            "SELECT * FROM itens_ordem_compra ORDER BY ordem_compra_id, id"
        ).fetchall():
            row = dict(r)
            if row["ordem_compra_id"] in ocs:
                ocs[row["ordem_compra_id"]]["itens"].append(row)
        return json.dumps(list(ocs.values()), ensure_ascii=False)


def listar_ordens_compra() -> str:
    with _conectar() as conn:
        rows = conn.execute(
            "SELECT * FROM ordens_compra ORDER BY data_entrega_prevista"
        ).fetchall()
        return json.dumps([dict(r) for r in rows], ensure_ascii=False)


def listar_itens_oc(ordem_compra_id: int) -> str:
    with _conectar() as conn:
        rows = conn.execute(
            "SELECT * FROM itens_ordem_compra WHERE ordem_compra_id=?",
            (ordem_compra_id,),
        ).fetchall()
        return json.dumps([dict(r) for r in rows], ensure_ascii=False)


def atualizar_status_entrega_oc(dados_json: str) -> str:
    d = json.loads(dados_json)
    with _conectar() as conn:
        conn.execute(
            "UPDATE ordens_compra SET status_entrega=? WHERE id=?",
            (d["status_entrega"], d["id"]),
        )
        return json.dumps({"ok": True})
