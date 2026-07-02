import json
import os
import shutil
import time
from pathlib import Path

from PySide6.QtCore import (
    QObject, Slot, Signal, QTimer, QRunnable, QThreadPool, Qt,
    QFileSystemWatcher,
)
from PySide6.QtWidgets import QFileDialog

from extracao.nf import extrair_nf
from extracao.nf_xml import extrair_nf_xml
from extracao.ordem_compra import extrair_ordem_compra
from db import repositorio
from exportacao.ordem_compra_xlsx import exportar_itens_oc
from exportacao.lista_compra_xlsx import exportar_itens_lista
import config
import backup as bkp


def _copiar_pdf(caminho_original: str, chave_pasta: str) -> str:
    if not caminho_original:
        return caminho_original
    pasta = config.pasta_valida(chave_pasta)
    if not pasta:
        return caminho_original
    src = Path(caminho_original)
    if not src.exists():
        return caminho_original
    dest = Path(pasta) / src.name
    if dest == src:
        return caminho_original
    try:
        shutil.copy2(src, dest)
        return str(dest)
    except Exception:
        return caminho_original


# Backup com debounce + execução em worker: cada escrita reagenda um único
# backup para depois de um curto período de quietude, e o snapshot em si roda
# num worker do QThreadPool — o Connection.backup() numa unidade lenta (HD
# externo, Drive/OneDrive) bloqueava a UI quando executava no timer da thread
# principal, mesmo com o debounce reduzindo a frequência.
_BACKUP_DEBOUNCE_MS = 3000
_backup_timer: QTimer | None = None
_backup_rodando = False


class _TarefaBackup(QRunnable):
    def run(self):
        global _backup_rodando
        try:
            bkp.fazer_backup()
        except Exception:
            pass
        finally:
            _backup_rodando = False


def _executar_backup():
    global _backup_rodando
    if _backup_rodando:
        # Snapshot anterior ainda em andamento (unidade lenta) — reagenda em vez
        # de rodar duas escritas concorrentes no mesmo arquivo de destino.
        _fazer_backup()
        return
    _backup_rodando = True
    QThreadPool.globalInstance().start(_TarefaBackup())


def _fazer_backup():
    """Agenda um backup (debounced). Seguro para chamar a cada escrita."""
    global _backup_timer
    if _backup_timer is None:
        _backup_timer = QTimer()
        _backup_timer.setSingleShot(True)
        _backup_timer.timeout.connect(_executar_backup)
    # Reinicia a contagem: o backup só roda 3s após a última escrita.
    _backup_timer.start(_BACKUP_DEBOUNCE_MS)


def fazer_backup_async() -> None:
    """Dispara um backup imediato em worker, sem debounce — usado pelo timer
    periódico do main.py."""
    _executar_backup()


def aguardar_backup(timeout_ms: int = 10000) -> None:
    """Bloqueia até o backup em worker terminar (ou estourar o timeout). Usado
    no fechamento do app, antes do snapshot final síncrono, para não haver duas
    escritas concorrentes no mesmo destino."""
    fim = time.monotonic() + timeout_ms / 1000
    while _backup_rodando and time.monotonic() < fim:
        time.sleep(0.05)


# Extração assíncrona: rodar a leitura de PDF/XML diretamente no corpo de um
# @Slot bloqueia a thread da GUI (o event loop do Qt) enquanto o pdfplumber/OCR
# trabalha, congelando a janela. Aqui a extração é despachada para um worker do
# QThreadPool; o resultado volta ao JS por um sinal Qt (extracaoConcluida),
# correlacionado por request_id. A conferência manual antes de salvar é
# preservada — o JS só preenche os campos quando o sinal chega.
class _EmissorExtracao(QObject):
    pronto = Signal(str, str)  # (request_id, json_resultado)


class _TarefaExtracao(QRunnable):
    def __init__(self, func, request_id: str, caminho: str, emissor: _EmissorExtracao):
        super().__init__()
        self._func = func
        self._request_id = request_id
        self._caminho = caminho
        self._emissor = emissor

    def run(self):
        try:
            resultado = self._func(self._caminho)
        except Exception as e:  # rede de segurança; os extratores já tratam erros
            resultado = json.dumps({"_erro": str(e)})
        self._emissor.pronto.emit(self._request_id, resultado)


# Extração de PDFs detectados na pasta de entrada (watcher). Igual ao mecanismo
# acima (QThreadPool para não travar a GUI), mas o resultado é tratado no próprio
# Python — vai para a fila de revisão da Bridge, não direto ao JS por request_id.
class _EmissorRevisao(QObject):
    pronto = Signal(str, str)  # (caminho, json_resultado)


class _TarefaRevisao(QRunnable):
    def __init__(self, func, caminho: str, emissor: _EmissorRevisao):
        super().__init__()
        self._func = func
        self._caminho = caminho
        self._emissor = emissor

    def run(self):
        try:
            resultado = self._func(self._caminho)
        except Exception as e:
            resultado = json.dumps({"_erro": str(e)})
        self._emissor.pronto.emit(self._caminho, resultado)


class Bridge(QObject):

    # Sinal exposto ao JS: emitido quando uma extração assíncrona termina.
    # (request_id, json_resultado)
    extracaoConcluida = Signal(str, str)

    # Sinal exposto ao JS: emitido quando a fila de revisão (PDFs detectados na
    # pasta de entrada) muda — o JS recarrega a lista via listar_fila_revisao().
    filaRevisaoAtualizada = Signal()

    def __init__(self):
        super().__init__()
        self._pool = QThreadPool.globalInstance()
        self._emissor = _EmissorExtracao()
        # Queued: 'pronto' é emitido da thread worker, mas o re-emit de
        # extracaoConcluida (que o QWebChannel entrega ao JS) precisa acontecer
        # na thread da Bridge (GUI). A conexão sinal→sinal com QueuedConnection
        # faz essa marshalização.
        self._emissor.pronto.connect(
            self.extracaoConcluida, Qt.ConnectionType.QueuedConnection
        )

        # ── Pasta de entrada monitorada (reaproveita pasta_nfs) ───────────────
        # Fila de revisão: caminho_completo -> { caminho, nome, dados }.
        # PDFs detectados na pasta ficam aqui aguardando confirmação manual — NÃO
        # são salvos automaticamente no banco.
        self._fila_revisao: dict[str, dict] = {}
        self._revisao_em_extracao: set[str] = set()
        self._watcher = QFileSystemWatcher()
        # Debounce: no Windows, copiar um único arquivo dispara vários
        # directoryChanged em rajada, e o evento pode chegar com o PDF ainda
        # sendo gravado. A varredura só roda após um período de quietude,
        # coalescendo a rajada e reduzindo a chance de ler arquivo parcial.
        self._debounce_watcher = QTimer(self)
        self._debounce_watcher.setSingleShot(True)
        self._debounce_watcher.setInterval(750)
        self._debounce_watcher.timeout.connect(self._verificar_pasta_nfs)
        self._watcher.directoryChanged.connect(self._ao_mudar_pasta_nfs)
        self._emissor_revisao = _EmissorRevisao()
        self._emissor_revisao.pronto.connect(
            self._revisao_extracao_pronta, Qt.ConnectionType.QueuedConnection
        )
        self._iniciar_watcher_nfs()

    # ── Pasta de entrada de NFs (monitoramento em tempo real) ─────────────────

    def _iniciar_watcher_nfs(self) -> None:
        """(Re)aponta o QFileSystemWatcher para a pasta_nfs configurada.

        Chamado na inicialização e sempre que o usuário troca a pasta em
        Configurações. Zera a fila da pasta anterior e faz uma varredura inicial
        (baseline) para detectar PDFs ainda não importados."""
        dirs = self._watcher.directories()
        if dirs:
            self._watcher.removePaths(dirs)
        self._fila_revisao.clear()
        self._revisao_em_extracao.clear()
        pasta = config.pasta_valida("pasta_nfs")
        if pasta:
            self._watcher.addPath(pasta)
            self._verificar_pasta_nfs()

    def _ao_mudar_pasta_nfs(self, _path: str) -> None:
        # Reinicia o debounce a cada evento da rajada; a varredura acontece só
        # depois que a pasta "assenta".
        self._debounce_watcher.start()

    def _verificar_pasta_nfs(self) -> None:
        """Varre a pasta e enfileira extração dos PDFs novos.

        "Novo" = arquivo .pdf cujo nome NÃO consta em notas_fiscais.arquivo_pdf
        (baseline/dedup por nome — 2ª camada, por número, é feita na revisão),
        que ainda não está na fila nem sendo extraído."""
        pasta = config.pasta_valida("pasta_nfs")
        if not pasta:
            return
        try:
            registrados = repositorio.nomes_pdf_nf_registrados()
        except Exception:
            registrados = set()
        try:
            nomes = os.listdir(pasta)
        except OSError:
            return
        for nome in nomes:
            if not nome.lower().endswith(".pdf"):
                continue
            if nome in registrados:                       # já importado (dedup por nome)
                continue
            caminho = str(Path(pasta) / nome)
            if caminho in self._fila_revisao:             # já aguardando revisão
                continue
            if caminho in self._revisao_em_extracao:      # já extraindo
                continue
            self._revisao_em_extracao.add(caminho)
            self._pool.start(_TarefaRevisao(extrair_nf, caminho, self._emissor_revisao))

    def _revisao_extracao_pronta(self, caminho: str, resultado_json: str) -> None:
        self._revisao_em_extracao.discard(caminho)
        try:
            dados = json.loads(resultado_json)
        except Exception:
            dados = {"_erro": "resultado inválido"}
        # O texto integral do PDF não interessa à fila e seria re-serializado ao
        # JS (via listar_fila_revisao) a cada atualização — em PDFs OCR'd são
        # centenas de KB por item.
        dados.pop("_texto_bruto", None)
        dados.pop("_ocr_usado", None)
        self._fila_revisao[caminho] = {
            "caminho": caminho,
            "nome": Path(caminho).name,
            "dados": dados,
        }
        self.filaRevisaoAtualizada.emit()

    @Slot(result=str)
    def listar_fila_revisao(self) -> str:
        return json.dumps(list(self._fila_revisao.values()), ensure_ascii=False)

    @Slot(str, result=str)
    def descartar_revisao(self, caminho: str) -> str:
        """Dispensa um PDF da revisão atual, sem marcá-lo como ignorado.

        Como o arquivo continua sem registro em notas_fiscais.arquivo_pdf, ele
        volta a ser detectado como novo na próxima verificação do watcher — o
        descarte é apenas uma dispensa da revisão corrente (2.3)."""
        self._fila_revisao.pop(caminho, None)
        self.filaRevisaoAtualizada.emit()
        return json.dumps({"ok": True})

    # ── Extração (assíncrona) ────────────────────────────────────────────────

    def _agendar_extracao(self, func, request_id: str, caminho: str) -> None:
        self._pool.start(_TarefaExtracao(func, request_id, caminho, self._emissor))

    @Slot(str, str)
    def ler_pdf_nf(self, request_id: str, caminho: str) -> None:
        self._agendar_extracao(extrair_nf, request_id, caminho)

    @Slot(str, str)
    def ler_xml_nf(self, request_id: str, caminho: str) -> None:
        self._agendar_extracao(extrair_nf_xml, request_id, caminho)

    @Slot(str, str)
    def ler_pdf_oc(self, request_id: str, caminho: str) -> None:
        self._agendar_extracao(extrair_ordem_compra, request_id, caminho)

    # ── Notas Fiscais ─────────────────────────────────────────────────────────

    @Slot(str, result=str)
    def salvar_nf(self, dados_json: str) -> str:
        d = json.loads(dados_json)
        if d.get("origem") == "pdf":
            d["arquivo_pdf"] = _copiar_pdf(d.get("arquivo_pdf", ""), "pasta_nfs")
        resultado = repositorio.salvar_nf(json.dumps(d))
        _fazer_backup()
        return resultado

    @Slot(result=str)
    def listar_nfs(self) -> str:
        return repositorio.listar_nfs()

    @Slot(int, result=str)
    def listar_itens_nf(self, nota_fiscal_id: int) -> str:
        return repositorio.listar_itens_nf(nota_fiscal_id)

    @Slot(str, result=str)
    def numero_nf_existe(self, numero: str) -> str:
        return repositorio.numero_nf_existe(numero)

    @Slot(str, result=str)
    def atualizar_status_nf(self, dados_json: str) -> str:
        resultado = repositorio.atualizar_status_nf(dados_json)
        _fazer_backup()
        return resultado

    @Slot(str, result=str)
    def marcar_pagas_em_massa(self, dados_json: str) -> str:
        resultado = repositorio.marcar_pagas_em_massa(dados_json)
        _fazer_backup()
        return resultado

    @Slot(int, result=str)
    def excluir_nf(self, nota_fiscal_id: int) -> str:
        resultado = repositorio.excluir_nf(nota_fiscal_id)
        _fazer_backup()
        return resultado

    @Slot(str, result=str)
    def excluir_nfs_em_massa(self, dados_json: str) -> str:
        resultado = repositorio.excluir_nfs_em_massa(dados_json)
        _fazer_backup()
        return resultado

    # ── Ordens de Compra ──────────────────────────────────────────────────────

    @Slot(str, result=str)
    def salvar_ordem_compra(self, dados_json: str) -> str:
        d = json.loads(dados_json)
        d["arquivo_pdf"] = _copiar_pdf(d.get("arquivo_pdf", ""), "pasta_ordens_compra")
        resultado = repositorio.salvar_ordem_compra(json.dumps(d))
        _fazer_backup()
        return resultado

    @Slot(int, result=str)
    def listar_itens_oc(self, ordem_compra_id: int) -> str:
        return repositorio.listar_itens_oc(ordem_compra_id)

    @Slot(int, str, result=str)
    def exportar_oc_xlsx(self, ordem_compra_id: int, caminho_destino: str) -> str:
        return exportar_itens_oc(ordem_compra_id, caminho_destino)

    @Slot(int, result=str)
    def excluir_ordem_compra(self, ordem_compra_id: int) -> str:
        resultado = repositorio.excluir_ordem_compra(ordem_compra_id)
        _fazer_backup()
        return resultado

    # ── Listas de compra ──────────────────────────────────────────────────────

    @Slot(str, result=str)
    def criar_lista(self, dados_json: str) -> str:
        resultado = repositorio.criar_lista(dados_json)
        _fazer_backup()
        return resultado

    @Slot(result=str)
    def listar_listas_com_ocs(self) -> str:
        return repositorio.listar_listas_com_ocs()

    @Slot(result=str)
    def listar_ocs_sem_lista(self) -> str:
        return repositorio.listar_ocs_sem_lista()

    @Slot(str, result=str)
    def atualizar_status_lista(self, dados_json: str) -> str:
        resultado = repositorio.atualizar_status_lista(dados_json)
        _fazer_backup()
        return resultado

    @Slot(str, result=str)
    def atualizar_lista(self, dados_json: str) -> str:
        resultado = repositorio.atualizar_lista(dados_json)
        _fazer_backup()
        return resultado

    @Slot(int, result=str)
    def excluir_lista(self, lista_id: int) -> str:
        resultado = repositorio.excluir_lista(lista_id)
        _fazer_backup()
        return resultado

    @Slot(int, str, result=str)
    def exportar_lista_xlsx(self, lista_id: int, caminho_destino: str) -> str:
        return exportar_itens_lista(lista_id, caminho_destino)

    # ── Configurações ─────────────────────────────────────────────────────────

    @Slot(result=str)
    def carregar_config(self) -> str:
        return json.dumps(config.carregar_config(), ensure_ascii=False)

    @Slot(str, result=str)
    def salvar_config(self, dados_json: str) -> str:
        pasta_antes = config.pasta_valida("pasta_nfs")
        config.salvar_config(json.loads(dados_json))
        # Só reaponta o watcher se a pasta_nfs de fato mudou: reiniciar zera a
        # fila e re-extrai (com OCR) todos os PDFs pendentes — custo que uma
        # alteração só de pasta_backup/pasta_ordens_compra não pode pagar.
        if config.pasta_valida("pasta_nfs") != pasta_antes:
            self._iniciar_watcher_nfs()
            self.filaRevisaoAtualizada.emit()
        return json.dumps({"ok": True})

    # ── Diálogos ──────────────────────────────────────────────────────────────

    @Slot(str, result=str)
    def abrir_dialogo_arquivo(self, titulo: str) -> str:
        caminho, _ = QFileDialog.getOpenFileName(None, titulo, "", "PDF (*.pdf)")
        return caminho or ""

    @Slot(str, result=str)
    def abrir_dialogo_arquivo_xml(self, titulo: str) -> str:
        caminho, _ = QFileDialog.getOpenFileName(None, titulo, "", "XML NFe (*.xml)")
        return caminho or ""

    @Slot(str, str, result=str)
    def abrir_dialogo_multiplos_arquivos(self, titulo: str, filtro: str) -> str:
        """Retorna JSON array de caminhos selecionados."""
        caminhos, _ = QFileDialog.getOpenFileNames(None, titulo, "", filtro)
        return json.dumps(caminhos or [])

    @Slot(str, str, result=str)
    def abrir_dialogo_salvar(self, titulo: str, nome_sugerido: str) -> str:
        caminho, _ = QFileDialog.getSaveFileName(None, titulo, nome_sugerido, "Excel (*.xlsx)")
        return caminho or ""

    @Slot(str, result=str)
    def abrir_dialogo_pasta(self, titulo: str) -> str:
        caminho = QFileDialog.getExistingDirectory(None, titulo, "")
        return caminho or ""
