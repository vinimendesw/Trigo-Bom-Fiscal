import json
import os
import sqlite3
import unicodedata
from contextlib import closing
from pathlib import Path

import config


def _db_path() -> str:
    data_dir = Path(os.environ.get("APPDATA", Path.home())) / "TrigoBom"
    data_dir.mkdir(parents=True, exist_ok=True)
    return str(data_dir / "trigo_bom.db")


def _conectar() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _arquivo_em_pasta_gerenciada(arquivo: str, chave: str = "pasta_nfs") -> bool:
    """True somente se `arquivo` estiver fisicamente DENTRO da pasta gerenciada
    pelo app (a configurada em `chave`). Usado pela exclusão de NF para nunca
    apagar o PDF original do usuário: a cópia gerenciada é apagável, mas se a
    pasta não estiver configurada (ou a cópia tiver falhado), `arquivo_pdf`
    aponta para o arquivo de origem — que jamais deve ser removido."""
    if not arquivo:
        return False
    pasta = config.pasta_valida(chave)
    if not pasta:
        return False
    try:
        return Path(arquivo).resolve().is_relative_to(Path(pasta).resolve())
    except (ValueError, OSError):
        return False


def _inicializar():
    schema = Path(__file__).parent / "schema.sql"
    with closing(_conectar()) as conn, conn:
        conn.executescript(schema.read_text(encoding="utf-8"))


def _migrar():
    """Aplica migrações incrementais sem quebrar bancos já existentes."""
    with closing(_conectar()) as conn, conn:
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

        # Adiciona coluna unidade em itens_ordem_compra se não existir
        colunas_oc = [r[1] for r in conn.execute("PRAGMA table_info(itens_ordem_compra)").fetchall()]
        if "unidade" not in colunas_oc:
            conn.execute("ALTER TABLE itens_ordem_compra ADD COLUMN unidade TEXT")

        # Cria listas_compra se não existir
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS listas_compra (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                nome            TEXT NOT NULL,
                data_prevista   TEXT,
                status_entrega  TEXT DEFAULT 'pendente',
                criado_em       TEXT DEFAULT (datetime('now', 'localtime'))
            );
        """)

        # Adiciona lista_id em ordens_compra se não existir
        colunas_oc2 = [r[1] for r in conn.execute("PRAGMA table_info(ordens_compra)").fetchall()]
        if "lista_id" not in colunas_oc2:
            conn.execute(
                "ALTER TABLE ordens_compra ADD COLUMN lista_id INTEGER REFERENCES listas_compra(id)"
            )

        # Índices (2026-07-02): SQLite não indexa FKs automaticamente — sem
        # eles, cada ON DELETE CASCADE varre a tabela de itens inteira, e os
        # lookups de dedup (numero_nf_existe, nomes_pdf_nf_registrados) fazem
        # full scan de notas_fiscais a cada verificação do watcher.
        conn.executescript("""
            CREATE INDEX IF NOT EXISTS idx_itens_nf_nota  ON itens_nota_fiscal(nota_fiscal_id);
            CREATE INDEX IF NOT EXISTS idx_itens_oc_ordem ON itens_ordem_compra(ordem_compra_id);
            CREATE INDEX IF NOT EXISTS idx_oc_lista       ON ordens_compra(lista_id);
            CREATE INDEX IF NOT EXISTS idx_nf_numero      ON notas_fiscais(numero);
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
    with closing(_conectar()) as conn, conn:
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


def numero_nf_existe(numero: str) -> str:
    """{"existe": bool} — True se já houver alguma NF com este número no banco.

    Consulta direta ao banco (não depende da lista em memória do front-end),
    usada como 2ª camada de dedup na revisão de PDFs detectados na pasta de
    entrada. Número vazio nunca é considerado duplicado."""
    numero = (numero or "").strip()
    if not numero:
        return json.dumps({"existe": False})
    with closing(_conectar()) as conn, conn:
        row = conn.execute(
            "SELECT 1 FROM notas_fiscais WHERE numero = ? LIMIT 1", (numero,)
        ).fetchone()
    return json.dumps({"existe": row is not None})


def nomes_pdf_nf_registrados() -> set:
    """Nomes de arquivo (basename) de todos os PDFs já vinculados a alguma NF.

    Usado pelo watcher da pasta de entrada como baseline: um PDF na pasta só é
    considerado "novo" se seu nome NÃO estiver neste conjunto. Cobre tanto os
    anos de PDFs históricos já importados quanto a prevenção de reprocessar um
    arquivo já salvo. Compara por basename para não depender do formato exato do
    caminho gravado em arquivo_pdf."""
    with closing(_conectar()) as conn, conn:
        rows = conn.execute(
            "SELECT arquivo_pdf FROM notas_fiscais "
            "WHERE arquivo_pdf IS NOT NULL AND arquivo_pdf <> ''"
        ).fetchall()
    return {Path(r["arquivo_pdf"]).name for r in rows}


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

    with closing(_conectar()) as conn, conn:
        rows = conn.execute(sql, params).fetchall()
        return json.dumps([dict(r) for r in rows], ensure_ascii=False)


def listar_itens_nf(nota_fiscal_id: int) -> str:
    with closing(_conectar()) as conn, conn:
        rows = conn.execute(
            "SELECT * FROM itens_nota_fiscal WHERE nota_fiscal_id=?",
            (nota_fiscal_id,),
        ).fetchall()
        return json.dumps([dict(r) for r in rows], ensure_ascii=False)


def atualizar_status_nf(dados_json: str) -> str:
    d = json.loads(dados_json)
    with closing(_conectar()) as conn, conn:
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
    with closing(_conectar()) as conn, conn:
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
    with closing(_conectar()) as conn, conn:
        rows = conn.execute(
            """SELECT o.id AS orgao_id, o.nome AS orgao_nome,
                      COALESCE(SUM(nf.valor), 0) AS total
               FROM orgaos o
               LEFT JOIN notas_fiscais nf
                 ON nf.orgao_id = o.id
                 AND nf.status_pagamento = 'pago'
                 AND strftime('%Y-%m', nf.data_pagamento) = ?
               GROUP BY o.id, o.nome
               ORDER BY o.id""",
            (periodo,),
        ).fetchall()
        return json.dumps([dict(r) for r in rows], ensure_ascii=False)


# ── Ordens de Compra ─────────────────────────────────────────────────────────

def salvar_ordem_compra(dados_json: str) -> str:
    d = json.loads(dados_json)
    with closing(_conectar()) as conn, conn:
        cur = conn.execute(
            """INSERT INTO ordens_compra
               (numero, fornecedor, data_emissao, data_entrega_prevista, arquivo_pdf, lista_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (d.get("numero"), d.get("fornecedor"), d.get("data_emissao"),
             d.get("data_entrega_prevista"), d.get("arquivo_pdf"), d.get("lista_id")),
        )
        oc_id = cur.lastrowid
        for item in d.get("itens", []):
            conn.execute(
                """INSERT INTO itens_ordem_compra
                   (ordem_compra_id, descricao, unidade, quantidade, valor_unitario, valor_total)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (oc_id, item.get("descricao"), item.get("unidade"), item.get("quantidade"),
                 item.get("valor_unitario"), item.get("valor_total")),
            )
        return json.dumps({"id": oc_id})


def listar_ordens_compra_com_itens() -> str:
    """Retorna OCs com seus itens aninhados num único payload."""
    with closing(_conectar()) as conn, conn:
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
    with closing(_conectar()) as conn, conn:
        rows = conn.execute(
            "SELECT * FROM ordens_compra ORDER BY data_entrega_prevista"
        ).fetchall()
        return json.dumps([dict(r) for r in rows], ensure_ascii=False)


def listar_itens_oc(ordem_compra_id: int) -> str:
    with closing(_conectar()) as conn, conn:
        rows = conn.execute(
            "SELECT * FROM itens_ordem_compra WHERE ordem_compra_id=?",
            (ordem_compra_id,),
        ).fetchall()
        return json.dumps([dict(r) for r in rows], ensure_ascii=False)


def atualizar_status_entrega_oc(dados_json: str) -> str:
    d = json.loads(dados_json)
    with closing(_conectar()) as conn, conn:
        conn.execute(
            "UPDATE ordens_compra SET status_entrega=? WHERE id=?",
            (d["status_entrega"], d["id"]),
        )
        return json.dumps({"ok": True})


def excluir_nf(nota_fiscal_id: int) -> str:
    """
    Exclui uma NF. Os itens em itens_nota_fiscal são removidos em cascata.
    O PDF só é removido do disco se for a cópia gerenciada (dentro da Pasta de
    NFs configurada) — o arquivo original do usuário nunca é apagado, mesmo que
    arquivo_pdf aponte para ele (pasta não configurada / cópia falhou). Ver
    `_arquivo_em_pasta_gerenciada`. A exclusão do registro sempre ocorre; falha
    na remoção do arquivo é ignorada.
    """
    with closing(_conectar()) as conn, conn:
        row = conn.execute(
            "SELECT arquivo_pdf FROM notas_fiscais WHERE id=?", (nota_fiscal_id,)
        ).fetchone()
        arquivo_pdf = row["arquivo_pdf"] if row else None
        conn.execute("DELETE FROM notas_fiscais WHERE id=?", (nota_fiscal_id,))

    if arquivo_pdf and _arquivo_em_pasta_gerenciada(arquivo_pdf):
        try:
            if os.path.exists(arquivo_pdf):
                os.remove(arquivo_pdf)
        except Exception:
            pass

    return json.dumps({"ok": True})


def excluir_nfs_em_massa(dados_json: str) -> str:
    """
    Exclui uma lista de NFs em transação única.
    dados: { ids: [int, ...] }
    """
    d = json.loads(dados_json)
    ids = d.get("ids", [])
    if not ids:
        return json.dumps({"ok": True, "excluidas": 0})

    with closing(_conectar()) as conn, conn:
        placeholders = ",".join("?" * len(ids))
        rows = conn.execute(
            f"SELECT arquivo_pdf FROM notas_fiscais WHERE id IN ({placeholders})", list(ids)
        ).fetchall()
        # Só apaga as cópias gerenciadas; originais do usuário ficam intactos.
        arquivos = [
            r["arquivo_pdf"] for r in rows
            if r["arquivo_pdf"] and _arquivo_em_pasta_gerenciada(r["arquivo_pdf"])
        ]
        conn.execute(f"DELETE FROM notas_fiscais WHERE id IN ({placeholders})", list(ids))

    for arquivo in arquivos:
        try:
            if os.path.exists(arquivo):
                os.remove(arquivo)
        except Exception:
            pass

    return json.dumps({"ok": True, "excluidas": len(ids)})


# ── Listas de compra ─────────────────────────────────────────────────────────

def _normalizar(s: str) -> str:
    """Lowercase + remove acentos para comparação de descrições."""
    s = (s or "").lower().strip()
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


def _agregar_itens(itens: list) -> list:
    """Agrupa itens por descrição normalizada, somando quantidades e totais."""
    agregados: dict = {}
    for item in itens:
        key = _normalizar(item.get("descricao", ""))
        if not key:
            continue
        if key not in agregados:
            agregados[key] = {
                "descricao":     item.get("descricao", ""),
                "unidade":       item.get("unidade", ""),
                "quantidade":    item.get("quantidade") or 0,
                "valor_unitario":item.get("valor_unitario"),
                "valor_total":   item.get("valor_total") or 0,
            }
        else:
            agregados[key]["quantidade"] = (
                (agregados[key]["quantidade"] or 0) + (item.get("quantidade") or 0)
            )
            agregados[key]["valor_total"] = (
                (agregados[key]["valor_total"] or 0) + (item.get("valor_total") or 0)
            )
            if agregados[key]["valor_unitario"] is None:
                agregados[key]["valor_unitario"] = item.get("valor_unitario")
    return list(agregados.values())


def criar_lista(dados_json: str = "{}") -> str:
    """
    Cria uma nova lista de compras com nome auto-gerado.
    dados: { data_prevista: str | null }

    O número do nome é derivado do id atribuído (cur.lastrowid), não de
    COUNT(*). Como a coluna é AUTOINCREMENT, o id nunca é reutilizado após uma
    exclusão — então o nome "Lista NN" é sempre único, sem o risco do COUNT(*),
    que reusava números já existentes depois de excluir uma lista (ex.: excluir
    a Lista 02 de 3 fazia a próxima virar "Lista 03", colidindo com a existente).
    """
    d = json.loads(dados_json) if dados_json else {}
    with closing(_conectar()) as conn, conn:
        cur = conn.execute(
            "INSERT INTO listas_compra (nome, data_prevista) VALUES (?, ?)",
            ("", d.get("data_prevista")),
        )
        lid = cur.lastrowid
        nome = f"Lista {lid:02d}"
        conn.execute("UPDATE listas_compra SET nome=? WHERE id=?", (nome, lid))
        return json.dumps({"id": lid, "nome": nome})


def listar_listas_com_ocs() -> str:
    """
    Retorna todas as listas com OCs aninhadas e itens agregados por lista.
    """
    with closing(_conectar()) as conn, conn:
        listas = {
            r["id"]: dict(r) | {"ocs": []}
            for r in conn.execute(
                "SELECT * FROM listas_compra ORDER BY criado_em DESC"
            ).fetchall()
        }

        ocs_rows = conn.execute(
            "SELECT * FROM ordens_compra WHERE lista_id IS NOT NULL ORDER BY lista_id, id"
        ).fetchall()
        ocs = {r["id"]: dict(r) | {"itens": []} for r in ocs_rows}

        for r in conn.execute(
            "SELECT * FROM itens_ordem_compra ORDER BY ordem_compra_id, id"
        ).fetchall():
            row = dict(r)
            oc_id = row["ordem_compra_id"]
            if oc_id in ocs:
                ocs[oc_id]["itens"].append(row)

        for oc in ocs.values():
            lid = oc.get("lista_id")
            if lid and lid in listas:
                listas[lid]["ocs"].append(oc)

        # Agrega itens por lista
        resultado = []
        for lista in listas.values():
            todos_itens = [it for oc in lista["ocs"] for it in oc["itens"]]
            lista["itens_agregados"] = _agregar_itens(todos_itens)
            resultado.append(lista)

        return json.dumps(resultado, ensure_ascii=False)


def listar_ocs_sem_lista() -> str:
    """Retorna OCs sem lista_id, com seus itens."""
    with closing(_conectar()) as conn, conn:
        ocs = {
            r["id"]: dict(r) | {"itens": []}
            for r in conn.execute(
                "SELECT * FROM ordens_compra WHERE lista_id IS NULL ORDER BY id"
            ).fetchall()
        }
        for r in conn.execute(
            "SELECT * FROM itens_ordem_compra ORDER BY ordem_compra_id, id"
        ).fetchall():
            row = dict(r)
            if row["ordem_compra_id"] in ocs:
                ocs[row["ordem_compra_id"]]["itens"].append(row)
        return json.dumps(list(ocs.values()), ensure_ascii=False)


def atualizar_status_lista(dados_json: str) -> str:
    d = json.loads(dados_json)
    with closing(_conectar()) as conn, conn:
        conn.execute(
            "UPDATE listas_compra SET status_entrega=? WHERE id=?",
            (d["status_entrega"], d["id"]),
        )
        return json.dumps({"ok": True})


def atualizar_lista(dados_json: str) -> str:
    """Atualiza nome e/ou data_prevista de uma lista."""
    d = json.loads(dados_json)
    with closing(_conectar()) as conn, conn:
        conn.execute(
            "UPDATE listas_compra SET nome=?, data_prevista=? WHERE id=?",
            (d.get("nome"), d.get("data_prevista"), d["id"]),
        )
        return json.dumps({"ok": True})


def excluir_lista(lista_id: int) -> str:
    """
    Exclui uma lista. As OCs que pertencem a ela ficam órfãs (lista_id = NULL),
    não são excluídas — o usuário pode decidir o que fazer com elas.
    """
    with closing(_conectar()) as conn, conn:
        conn.execute("UPDATE ordens_compra SET lista_id=NULL WHERE lista_id=?", (lista_id,))
        conn.execute("DELETE FROM listas_compra WHERE id=?", (lista_id,))
        return json.dumps({"ok": True})


def excluir_ordem_compra(ordem_compra_id: int) -> str:
    """Exclui uma OC. Os itens são removidos em cascata (ON DELETE CASCADE)."""
    with closing(_conectar()) as conn, conn:
        conn.execute("DELETE FROM ordens_compra WHERE id=?", (ordem_compra_id,))
        return json.dumps({"ok": True})


def excluir_ordens_compra_em_massa(dados_json: str) -> str:
    """
    Exclui uma lista de OCs em transação única. Itens removidos em cascata.
    dados: { ids: [int, ...] }
    """
    d = json.loads(dados_json)
    ids = d.get("ids", [])
    if not ids:
        return json.dumps({"ok": True, "excluidas": 0})
    with closing(_conectar()) as conn, conn:
        placeholders = ",".join("?" * len(ids))
        conn.execute(f"DELETE FROM ordens_compra WHERE id IN ({placeholders})", list(ids))
        return json.dumps({"ok": True, "excluidas": len(ids)})
