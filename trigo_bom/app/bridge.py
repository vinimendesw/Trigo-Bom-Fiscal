import json
import shutil
from pathlib import Path

from PySide6.QtCore import (
    QObject, Slot, Signal, QTimer, QRunnable, QThreadPool, Qt,
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


# Backup com debounce: cada escrita reagenda um único backup para depois de um
# curto período de quietude, em vez de copiar o banco inteiro (shutil.copy2)
# sincronamente na thread principal a cada operação — o que congelava a UI quando
# a pasta de backup é uma unidade lenta (HD externo) ou sincronizada (Drive/OneDrive).
_BACKUP_DEBOUNCE_MS = 3000
_backup_timer: QTimer | None = None


def _executar_backup():
    try:
        bkp.fazer_backup()
    except Exception:
        pass


def _fazer_backup():
    """Agenda um backup (debounced). Seguro para chamar a cada escrita."""
    global _backup_timer
    if _backup_timer is None:
        _backup_timer = QTimer()
        _backup_timer.setSingleShot(True)
        _backup_timer.timeout.connect(_executar_backup)
    # Reinicia a contagem: o backup só roda 3s após a última escrita.
    _backup_timer.start(_BACKUP_DEBOUNCE_MS)


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


class Bridge(QObject):

    # Sinal exposto ao JS: emitido quando uma extração assíncrona termina.
    # (request_id, json_resultado)
    extracaoConcluida = Signal(str, str)

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
        config.salvar_config(json.loads(dados_json))
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
