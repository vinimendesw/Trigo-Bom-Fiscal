import sys
import os
import ctypes
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtCore import QUrl, QTimer, Qt
from PySide6.QtGui import QIcon

from bridge import Bridge
import backup
from atualizacao import VerificadorAtualizacao

_BACKUP_INTERVAL_MS = 10 * 60 * 1000  # 10 minutos



def _checar_backup_e_lock(app: QApplication) -> None:
    lock_info = backup.verificar_lock()
    if lock_info:
        ts   = lock_info.get("ts", "?")[:16].replace("T", " ")
        host = lock_info.get("hostname", "?")
        QMessageBox.warning(
            None,
            "Atenção — Uso simultâneo",
            f"O dispositivo <b>{host}</b> também está com o TrigoBom aberto "
            f"(desde {ts}).\n\nContinuando, você pode sobrescrever dados não "
            "sincronizados. Feche o app no outro dispositivo antes de fazer alterações.",
        )

    meta = backup.verificar_backup_mais_novo()
    if meta:
        ts   = meta.get("ts", "?")[:16].replace("T", " ")
        host = meta.get("hostname", "?")
        resposta = QMessageBox.question(
            None,
            "Banco de dados desatualizado",
            f"Um backup mais recente foi encontrado na pasta configurada\n"
            f"(criado em {ts} por <b>{host}</b>).\n\n"
            "Deseja restaurar esse backup antes de continuar?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if resposta == QMessageBox.StandardButton.Yes:
            backup.restaurar_backup()

    backup.gravar_lock()


def main():
    # Define AppUserModelID antes de criar a QApplication para que o Windows
    # use o ícone do app na barra de tarefas em vez do ícone do Python.
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("TrigoBom.Fiscal.1")
        except Exception:
            pass

    app = QApplication(sys.argv)

    # Ícone do app (espiga dourada) — .ico com múltiplas resoluções para barra de tarefas
    icone_path = os.path.join(os.path.dirname(__file__), "ui", "assets", "icone.ico")
    if os.path.exists(icone_path):
        icon = QIcon(icone_path)
        app.setWindowIcon(icon)

    _checar_backup_e_lock(app)

    view = QWebEngineView()
    channel = QWebChannel()
    bridge = Bridge()
    channel.registerObject("backend", bridge)
    view.page().setWebChannel(channel)

    ui_path = os.path.join(os.path.dirname(__file__), "ui", "index.html")
    view.setUrl(QUrl.fromLocalFile(ui_path))
    view.setWindowTitle("TrigoBom Fiscal")
    if os.path.exists(icone_path):
        view.setWindowIcon(icon)
    view.resize(1280, 800)
    view.show()

    # Verificação de atualização — roda em background, não bloqueia a UI
    _verificador = VerificadorAtualizacao()

    def _avisar_nova_versao(tag: str, url: str):
        msg = QMessageBox(view)
        msg.setWindowTitle("Atualização disponível")
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setText(
            f"Uma nova versão do TrigoBom está disponível: <b>{tag}</b>.<br><br>"
            f"Acesse o link abaixo para baixar o instalador:<br>"
            f'<a href="{url}">{url}</a>'
        )
        msg.setTextFormat(Qt.TextFormat.RichText)
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.exec()

    _verificador.nova_versao.connect(_avisar_nova_versao)
    QTimer.singleShot(3000, _verificador.verificar)

    # Timer de backup automático a cada 10 minutos
    timer_backup = QTimer(app)
    timer_backup.timeout.connect(lambda: backup.fazer_backup())
    timer_backup.start(_BACKUP_INTERVAL_MS)

    def _ao_fechar():
        timer_backup.stop()
        backup.fazer_backup()
        backup.remover_lock()

    app.aboutToQuit.connect(_ao_fechar)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
