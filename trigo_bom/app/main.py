import sys
import os
import ctypes
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtCore import QUrl, QTimer
from PySide6.QtGui import QIcon

from bridge import Bridge, fazer_backup_async, aguardar_backup
import backup

_BACKUP_INTERVAL_MS = 3 * 60 * 1000  # 3 minutos



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

    # Timer de backup automático a cada 3 minutos — roda em worker (bridge)
    # para não bloquear a UI quando a pasta de backup é uma unidade lenta.
    timer_backup = QTimer(app)
    timer_backup.timeout.connect(fazer_backup_async)
    timer_backup.start(_BACKUP_INTERVAL_MS)

    def _ao_fechar():
        timer_backup.stop()
        # Espera um backup em worker terminar antes do snapshot final síncrono,
        # evitando duas escritas concorrentes no mesmo arquivo de destino.
        aguardar_backup()
        backup.fazer_backup()
        backup.remover_lock()

    app.aboutToQuit.connect(_ao_fechar)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
