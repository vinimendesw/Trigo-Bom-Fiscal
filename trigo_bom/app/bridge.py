import json
import shutil
from pathlib import Path

from PySide6.QtCore import QObject, Slot
from PySide6.QtWidgets import QFileDialog

from extracao.nf import extrair_nf
from extracao.nf_xml import extrair_nf_xml
from extracao.ordem_compra import extrair_ordem_compra
from db import repositorio
from exportacao.ordem_compra_xlsx import exportar_itens_oc
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


def _fazer_backup():
    try:
        bkp.fazer_backup()
    except Exception:
        pass


class Bridge(QObject):

    # ── Extração ─────────────────────────────────────────────────────────────

    @Slot(str, result=str)
    def ler_pdf_nf(self, caminho: str) -> str:
        return extrair_nf(caminho)

    @Slot(str, result=str)
    def ler_xml_nf(self, caminho: str) -> str:
        return extrair_nf_xml(caminho)

    @Slot(str, result=str)
    def ler_pdf_oc(self, caminho: str) -> str:
        return extrair_ordem_compra(caminho)

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

    @Slot(str, result=str)
    def listar_nfs_filtrado(self, filtros_json: str) -> str:
        return repositorio.listar_nfs(filtros_json)

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

    @Slot(int, int, result=str)
    def totais_nf_por_orgao(self, mes: int, ano: int) -> str:
        return repositorio.totais_nf_por_orgao(mes, ano)

    # ── Ordens de Compra ──────────────────────────────────────────────────────

    @Slot(str, result=str)
    def salvar_ordem_compra(self, dados_json: str) -> str:
        d = json.loads(dados_json)
        d["arquivo_pdf"] = _copiar_pdf(d.get("arquivo_pdf", ""), "pasta_ordens_compra")
        resultado = repositorio.salvar_ordem_compra(json.dumps(d))
        _fazer_backup()
        return resultado

    @Slot(result=str)
    def listar_ordens_compra(self) -> str:
        return repositorio.listar_ordens_compra()

    @Slot(result=str)
    def listar_ordens_compra_com_itens(self) -> str:
        return repositorio.listar_ordens_compra_com_itens()

    @Slot(int, result=str)
    def listar_itens_oc(self, ordem_compra_id: int) -> str:
        return repositorio.listar_itens_oc(ordem_compra_id)

    @Slot(str, result=str)
    def atualizar_status_entrega_oc(self, dados_json: str) -> str:
        return repositorio.atualizar_status_entrega_oc(dados_json)

    @Slot(int, str, result=str)
    def exportar_oc_xlsx(self, ordem_compra_id: int, caminho_destino: str) -> str:
        return exportar_itens_oc(ordem_compra_id, caminho_destino)

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
