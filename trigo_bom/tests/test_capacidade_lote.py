"""
Teste de capacidade — inclusão em lote de OCs e NFs.

O que este arquivo mede e por que importa
------------------------------------------
O fluxo de inclusão em lote tem quatro camadas, cada uma com um limite diferente:

  Camada 1 — EXTRAÇÃO (pdfplumber/fitz → CPU, 1 arquivo por vez)
    Responsável pela maior parte do tempo percebido pelo usuário.
    Não é testada aqui com PDFs reais (dependeria de arquivos externos),
    mas os thresholds de referência estão documentados em
    `_THRESHOLDS_EXTRACAO_REFERENCIA` para orientar decisões futuras.

  Camada 2 — PERSISTÊNCIA (SQLite, por save: ~1 conexão + 1-N INSERTs)
    Testada com INSERT sintético de NFs e OCs em escala crescente.
    Cada save abre e fecha uma conexão — padrão atual do repositório.

  Camada 3 — LEITURA/AGREGAÇÃO (listar_listas_com_ocs, listar_nfs)
    Chamada automaticamente após cada lote salvo (ou ao recarregar a tela).
    O payload cresce com N×M (N listas × M itens/OC); testada em escala.

  Camada 4 — BACKUP DEBOUNCE (3 s após o último save)
    Não testada diretamente aqui (depende de QTimer); está coberta em
    test_backup_lock.py. O ponto a observar é que o backup final de um
    lote grande (~100 OCs, banco de ~5 MB) deve caber em < 1 s via
    `Connection.backup()` — muito abaixo do debounce de 3 s.

Como executar
-------------
    cd trigo_bom
    pytest tests/test_capacidade_lote.py -v --tb=short

Os testes NÃO dependem de PDFs reais nem de UI. Eles injetam dados
sintéticos diretamente no repositório (via db_isolado) e medem o tempo
de cada operação com `time.perf_counter`.

Thresholds
----------
Os limites (LIMITE_*) são conservadores para uma máquina de escritório
típica (HD mecânico, Python 3.11, sem índices extras). Ajuste conforme
o ambiente real do cliente se os testes falharem por hardware lento.
"""

import json
import time
import pytest
import db.repositorio as repo

# ── Thresholds de tempo (segundos) ───────────────────────────────────────────

# Persistência: tempo máximo aceitável para salvar 1 NF/OC (sem itens)
LIMITE_SAVE_UNITARIO_S = 0.05  # 50 ms por registro

# Persistência: tempo máximo aceitável para salvar N registros sequencialmente
# (os saves são sequenciais no fluxo atual — um por vez, confirmação manual)
LIMITES_LOTE = {
    10:  0.5,    # 10 docs  → < 500 ms total
    50:  2.5,    # 50 docs  → < 2,5 s total
    100: 5.0,    # 100 docs → < 5 s total (limite prático da paciência do usuário)
    200: 10.0,   # 200 docs → < 10 s (beyond normal use, mas não deve travar)
}

# Leitura: tempo máximo aceitável para listar_listas_com_ocs com N OCs no banco
LIMITES_LEITURA_OC = {
    50:  0.1,    # 50 OCs   → < 100 ms
    200: 0.3,    # 200 OCs  → < 300 ms
    500: 1.0,    # 500 OCs  → < 1 s
}

# Leitura: tempo máximo aceitável para listar_nfs com N NFs no banco
LIMITES_LEITURA_NF = {
    100: 0.1,    # 100 NFs  → < 100 ms
    500: 0.3,    # 500 NFs  → < 300 ms
    1000: 1.0,   # 1000 NFs → < 1 s
}

# ── Referência de extração (documentados, não executados aqui) ────────────────
# Esses valores são estimativas baseadas nos mecanismos de extração:
#
# pdfplumber (PDF com camada de texto normal, 1-3 páginas):  0.2 – 1.5 s
# fitz fallback (mesmo PDF, texto corrupto detectado):       0.3 – 2.0 s
# OCR via pytesseract (300 DPI, 1 página, idioma "por"):     5 – 30 s
# XML NFe (arquivo típico de 50-200 KB):                     0.01 – 0.05 s
#
# Consequência prática:
# - Lote de 20 PDFs sem OCR  → ~10-30 s de extração total (aceitável)
# - Lote de 20 PDFs com OCR  → ~2-10 min de extração total (lento mas funciona)
# - Lote de 20 XMLs           → ~0.2-1 s de extração total (instantâneo)
# - O gargalo real para PDF com OCR é o Tesseract (externo, não paralelizável
#   sem múltiplos processos). O fluxo atual é sequencial (1 arquivo por vez
#   em QThreadPool), então OCR em lote grande (50+ PDFs) pode levar horas.


# ── Dados sintéticos ─────────────────────────────────────────────────────────

def _nf(idx: int, n_itens: int = 0) -> dict:
    """NF sintética com `n_itens` itens."""
    nf = {
        "numero": f"{idx:06d}",
        "orgao_id": (idx % 4) + 1,
        "data_emissao": "2026-01-15",
        "valor": round(100.0 + idx * 1.5, 2),
        "categoria": "Alimentícios",
        "status_pagamento": "nao_pago",
        "data_vencimento": "2026-02-15",
        "data_pagamento": None,
        "arquivo_pdf": "",
        "origem": "pdf",
        "itens": [
            {
                "descricao": f"Item {j+1} da NF {idx}",
                "quantidade": float(j + 1),
                "valor_unitario": 10.0,
                "valor_total": 10.0 * (j + 1),
                "ncm": "17019900",
                "cfop": "5102",
            }
            for j in range(n_itens)
        ],
    }
    return nf


def _oc(idx: int, n_itens: int = 5) -> dict:
    """OC sintética com `n_itens` itens."""
    return {
        "numero": f"OC-{idx:04d}",
        "fornecedor": f"Fornecedor {idx % 10 + 1}",
        "data_emissao": "2026-01-10",
        "data_entrega_prevista": "2026-02-10",
        "arquivo_pdf": "",
        "lista_id": None,
        "itens": [
            {
                "descricao": f"Produto {j+1}",
                "unidade": "UN",
                "quantidade": float(j + 1),
                "valor_unitario": 15.0,
                "valor_total": 15.0 * (j + 1),
            }
            for j in range(n_itens)
        ],
    }


# ── Testes de persistência: NFs ───────────────────────────────────────────────

class TestPersistenciaNF:

    def test_save_unitario_nf_sem_itens(self, db_isolado):
        """Um único save de NF (sem itens) deve completar em < LIMITE_SAVE_UNITARIO_S."""
        t0 = time.perf_counter()
        repo.salvar_nf(json.dumps(_nf(1, n_itens=0)))
        elapsed = time.perf_counter() - t0
        print(f"\n  save NF (0 itens): {elapsed*1000:.1f} ms")
        assert elapsed < LIMITE_SAVE_UNITARIO_S, (
            f"Save de NF unitária levou {elapsed:.3f}s (limite: {LIMITE_SAVE_UNITARIO_S}s)"
        )

    def test_save_unitario_nf_com_itens(self, db_isolado):
        """Um único save de NF com 30 itens (XML) deve completar em < LIMITE_SAVE_UNITARIO_S * 3."""
        t0 = time.perf_counter()
        repo.salvar_nf(json.dumps(_nf(1, n_itens=30)))
        elapsed = time.perf_counter() - t0
        print(f"\n  save NF (30 itens): {elapsed*1000:.1f} ms")
        assert elapsed < LIMITE_SAVE_UNITARIO_S * 3, (
            f"Save de NF com 30 itens levou {elapsed:.3f}s"
        )

    @pytest.mark.parametrize("n", [10, 50, 100, 200])
    def test_lote_nf_sequencial(self, db_isolado, n):
        """
        Simula o fluxo de lote: N saves sequenciais de NF (sem itens),
        um por vez como acontece no JS (salvar → avançar → próxima extração → salvar...).
        """
        t0 = time.perf_counter()
        for i in range(n):
            repo.salvar_nf(json.dumps(_nf(i)))
        elapsed = time.perf_counter() - t0
        por_registro = elapsed / n * 1000

        print(f"\n  lote {n} NFs: {elapsed:.3f}s total | {por_registro:.1f} ms/NF")
        assert elapsed < LIMITES_LOTE[n], (
            f"Lote de {n} NFs levou {elapsed:.3f}s (limite: {LIMITES_LOTE[n]}s)"
        )


# ── Testes de persistência: OCs ───────────────────────────────────────────────

class TestPersistenciaOC:

    def test_save_unitario_oc(self, db_isolado):
        """Um único save de OC com 5 itens deve completar em < LIMITE_SAVE_UNITARIO_S."""
        t0 = time.perf_counter()
        repo.salvar_ordem_compra(json.dumps(_oc(1, n_itens=5)))
        elapsed = time.perf_counter() - t0
        print(f"\n  save OC (5 itens): {elapsed*1000:.1f} ms")
        assert elapsed < LIMITE_SAVE_UNITARIO_S, (
            f"Save de OC levou {elapsed:.3f}s (limite: {LIMITE_SAVE_UNITARIO_S}s)"
        )

    def test_save_oc_muitos_itens(self, db_isolado):
        """OC com 50 itens (caso extremo de tabela grande no PDF)."""
        t0 = time.perf_counter()
        repo.salvar_ordem_compra(json.dumps(_oc(1, n_itens=50)))
        elapsed = time.perf_counter() - t0
        print(f"\n  save OC (50 itens): {elapsed*1000:.1f} ms")
        assert elapsed < LIMITE_SAVE_UNITARIO_S * 5, (
            f"Save de OC com 50 itens levou {elapsed:.3f}s"
        )

    @pytest.mark.parametrize("n", [10, 50, 100, 200])
    def test_lote_oc_sequencial(self, db_isolado, n):
        """
        N saves sequenciais de OC (5 itens cada), sem lista.
        Simula lote de PDFs de OC — mesmo fluxo, 1 por vez.
        """
        t0 = time.perf_counter()
        for i in range(n):
            repo.salvar_ordem_compra(json.dumps(_oc(i, n_itens=5)))
        elapsed = time.perf_counter() - t0
        por_registro = elapsed / n * 1000

        print(f"\n  lote {n} OCs (5 itens cada): {elapsed:.3f}s total | {por_registro:.1f} ms/OC")
        assert elapsed < LIMITES_LOTE[n], (
            f"Lote de {n} OCs levou {elapsed:.3f}s (limite: {LIMITES_LOTE[n]}s)"
        )


# ── Testes de leitura: listar_listas_com_ocs ─────────────────────────────────

class TestLeituraListasOC:

    def _popular_listas(self, n_ocs: int, n_itens_por_oc: int = 5):
        """Cria 1 lista com n_ocs OCs, cada uma com n_itens_por_oc itens."""
        lista_raw = repo.criar_lista(json.dumps({"data_prevista": "2026-02-01"}))
        lista_id = json.loads(lista_raw)["id"]
        for i in range(n_ocs):
            oc = _oc(i, n_itens=n_itens_por_oc)
            oc["lista_id"] = lista_id
            repo.salvar_ordem_compra(json.dumps(oc))

    @pytest.mark.parametrize("n_ocs", [50, 200, 500])
    def test_listar_listas_com_ocs(self, db_isolado, n_ocs):
        """
        Mede o tempo de listar_listas_com_ocs com N OCs de 5 itens cada.
        Essa função é chamada toda vez que o usuário termina um lote de OCs
        (recarregarListas) e também no carregamento inicial.
        """
        self._popular_listas(n_ocs, n_itens_por_oc=5)

        t0 = time.perf_counter()
        resultado = json.loads(repo.listar_listas_com_ocs())
        elapsed = time.perf_counter() - t0

        total_ocs = sum(len(l["ocs"]) for l in resultado)
        total_itens = sum(
            sum(len(oc["itens"]) for oc in l["ocs"]) for l in resultado
        )
        print(
            f"\n  listar_listas_com_ocs ({n_ocs} OCs, {total_itens} itens): "
            f"{elapsed*1000:.1f} ms"
        )
        assert elapsed < LIMITES_LEITURA_OC[n_ocs], (
            f"listar_listas_com_ocs ({n_ocs} OCs) levou {elapsed:.3f}s "
            f"(limite: {LIMITES_LEITURA_OC[n_ocs]}s)"
        )
        assert total_ocs == n_ocs

    @pytest.mark.parametrize("n_ocs", [50, 200, 500])
    def test_listar_listas_itens_agregados(self, db_isolado, n_ocs):
        """
        A agregação de itens por lista (_agregar_itens) acontece em Python
        após a leitura do banco. Com muitos itens únicos (sem duplicatas para
        agregar), ela é O(N) — mas importa verificar que não há regressão.
        """
        self._popular_listas(n_ocs, n_itens_por_oc=10)

        t0 = time.perf_counter()
        resultado = json.loads(repo.listar_listas_com_ocs())
        elapsed = time.perf_counter() - t0

        # Com 10 itens por OC e descrições únicas (Produto 1..10), a lista
        # agregada deve ter exatamente 10 tipos distintos.
        for lista in resultado:
            assert len(lista["itens_agregados"]) == 10, (
                f"Esperado 10 tipos agregados, obteve {len(lista['itens_agregados'])}"
            )
        print(
            f"\n  listar_listas_com_ocs + agregação ({n_ocs} OCs × 10 itens): "
            f"{elapsed*1000:.1f} ms"
        )
        assert elapsed < LIMITES_LEITURA_OC[n_ocs] * 2, (
            f"Com agregação ({n_ocs} OCs × 10 itens) levou {elapsed:.3f}s"
        )


# ── Testes de leitura: listar_nfs ────────────────────────────────────────────

class TestLeituraNFs:

    def _popular_nfs(self, n: int):
        for i in range(n):
            repo.salvar_nf(json.dumps(_nf(i)))

    @pytest.mark.parametrize("n", [100, 500, 1000])
    def test_listar_nfs(self, db_isolado, n):
        """
        Mede listar_nfs com N notas no banco.
        Essa função é chamada a cada renderNFs() e renderDashboard() — ou seja,
        sempre que qualquer NF é salva ou o status muda.
        """
        self._popular_nfs(n)

        t0 = time.perf_counter()
        resultado = json.loads(repo.listar_nfs())
        elapsed = time.perf_counter() - t0

        print(f"\n  listar_nfs ({n} NFs): {elapsed*1000:.1f} ms")
        assert len(resultado) == n
        assert elapsed < LIMITES_LEITURA_NF[n], (
            f"listar_nfs ({n} NFs) levou {elapsed:.3f}s "
            f"(limite: {LIMITES_LEITURA_NF[n]}s)"
        )


# ── Testes de gargalo identificado: save abre nova conexão a cada chamada ────

class TestConexaoPorSave:
    """
    O repositório abre e fecha uma nova conexão SQLite a cada save.
    Para N saves sequenciais, isso significa N aberturas de arquivo.
    Esse teste documenta o custo real do padrão atual vs. uma transação única.
    """

    def test_custo_conexao_individual_vs_bulk(self, db_isolado):
        """
        Compara 100 saves individuais (padrão atual) vs. 100 INSERTs
        em uma única conexão/transação (não disponível na UI hoje).
        O resultado documenta o overhead do padrão atual e serve de
        referência para uma futura otimização de 'salvar lote inteiro
        de uma vez' se o volume do cliente crescer.
        """
        import sqlite3
        from contextlib import closing

        # Padrão atual: 100 saves, cada um abre e fecha conexão
        t0 = time.perf_counter()
        for i in range(100):
            repo.salvar_nf(json.dumps(_nf(i)))
        t_individual = time.perf_counter() - t0

        # Reset
        import os
        os.remove(db_isolado)
        repo._inicializar()
        repo._migrar()

        # Bulk: 100 INSERTs em 1 conexão/transação
        t0 = time.perf_counter()
        with closing(sqlite3.connect(db_isolado)) as conn, conn:
            for i in range(100):
                d = _nf(i)
                conn.execute(
                    "INSERT INTO notas_fiscais "
                    "(numero, orgao_id, data_emissao, valor, categoria, "
                    "status_pagamento, data_vencimento, data_pagamento, arquivo_pdf, origem) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (d["numero"], d["orgao_id"], d["data_emissao"], d["valor"],
                     d["categoria"], d["status_pagamento"], d["data_vencimento"],
                     d["data_pagamento"], d["arquivo_pdf"], d["origem"]),
                )
        t_bulk = time.perf_counter() - t0

        razao = t_individual / t_bulk if t_bulk > 0 else float("inf")
        print(
            f"\n  100 saves individuais: {t_individual*1000:.1f} ms\n"
            f"  100 INSERTs bulk:      {t_bulk*1000:.1f} ms\n"
            f"  Overhead do padrão atual: {razao:.1f}×"
        )
        # No Windows, SQLite paga ~5-8 ms por abertura de conexão (system calls
        # de CreateFile + flock). Um overhead de 50-80× é normal; > 200× indica
        # FS muito lento (HD mecânico externo, drive de rede, antivírus pesado).
        assert razao < 200, (
            f"Overhead de {razao:.1f}× indica FS extremamente lento (HD antigo / drive de rede?)"
        )


# ── Relatório consolidado de limites práticos ─────────────────────────────────

class TestRelatorioCapacidade:
    """
    Testa os cenários de uso real descrito no CLAUDE.md (~30 docs/mês)
    e cenários de pico (mês de alta demanda, importação retroativa).
    """

    def test_cenario_uso_normal_mensal(self, db_isolado):
        """
        Cenário: cliente inclui 30 NFs + 15 OCs (5 itens cada) no mês.
        Espera: persistência total em < 3 s.
        """
        t0 = time.perf_counter()
        for i in range(30):
            repo.salvar_nf(json.dumps(_nf(i)))
        for i in range(15):
            repo.salvar_ordem_compra(json.dumps(_oc(i, n_itens=5)))
        elapsed = time.perf_counter() - t0
        print(f"\n  Uso normal mensal (30 NFs + 15 OCs): {elapsed*1000:.0f} ms")
        assert elapsed < 3.0, f"Uso normal mensal levou {elapsed:.3f}s"

    def test_cenario_pico_retroativo(self, db_isolado):
        """
        Cenário: importação retroativa de 6 meses de dados (180 NFs + 90 OCs).
        Espera: persistência total em < 15 s.
        Nota: o tempo percebido pelo usuário será maior, pois cada arquivo
        passa pela extração (pdfplumber/OCR) antes de chegar ao save.
        """
        t0 = time.perf_counter()
        for i in range(180):
            repo.salvar_nf(json.dumps(_nf(i)))
        for i in range(90):
            repo.salvar_ordem_compra(json.dumps(_oc(i, n_itens=5)))
        elapsed = time.perf_counter() - t0
        print(f"\n  Pico retroativo (180 NFs + 90 OCs): {elapsed*1000:.0f} ms")
        assert elapsed < 15.0, f"Cenário de pico retroativo levou {elapsed:.3f}s"

    def test_cenario_leitura_apos_pico(self, db_isolado):
        """
        Após o pico, a tela principal deve carregar sem lentidão perceptível.
        Mede o carregamento simultâneo de NFs + Listas após banco populado.
        """
        for i in range(180):
            repo.salvar_nf(json.dumps(_nf(i)))
        lista_id = json.loads(
            repo.criar_lista(json.dumps({"data_prevista": "2026-07-01"}))
        )["id"]
        for i in range(90):
            oc = _oc(i, n_itens=5)
            oc["lista_id"] = lista_id
            repo.salvar_ordem_compra(json.dumps(oc))

        t0 = time.perf_counter()
        nfs = json.loads(repo.listar_nfs())
        listas = json.loads(repo.listar_listas_com_ocs())
        elapsed = time.perf_counter() - t0

        print(
            f"\n  Leitura pós-pico ({len(nfs)} NFs + {sum(len(l['ocs']) for l in listas)} OCs): "
            f"{elapsed*1000:.1f} ms"
        )
        assert elapsed < 1.0, (
            f"Carregamento inicial após pico levou {elapsed:.3f}s "
            f"(UI parecerá lenta se > 1 s)"
        )
