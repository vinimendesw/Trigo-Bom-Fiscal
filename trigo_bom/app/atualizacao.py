"""Verificação de atualização disponível via GitHub Releases.

Consultado uma vez ao iniciar o app. A verificação roda em thread separada para
não bloquear a UI. Se houver versão mais nova, o sinal `nova_versao` é emitido
com a tag e a URL da Release — a UI decide o que exibir.

Comportamento:
- Timeout de 5 s na requisição HTTP.
- Qualquer falha (sem rede, repo privado, rate-limit) é silenciada — o app
  continua normalmente sem avisar o usuário sobre a falha de checagem.
- Compara versões por semver numérico (evita comparação lexicográfica de strings).
"""

import urllib.request
import json
import logging
from packaging.version import Version, InvalidVersion

from PySide6.QtCore import QObject, Signal, QRunnable, QThreadPool

from __version__ import __version__

_API_URL = "https://api.github.com/repos/vinimendesw/Trigo-Bom-Fiscal/releases/latest"
_TIMEOUT_S = 5

log = logging.getLogger(__name__)


def _versao_tag(tag: str) -> Version:
    """Remove prefixo 'v' e converte para Version comparável."""
    return Version(tag.lstrip("v"))


class _Verificador(QRunnable):
    def __init__(self, sinal_nova_versao):
        super().__init__()
        self._sinal = sinal_nova_versao

    def run(self):
        try:
            req = urllib.request.Request(
                _API_URL,
                headers={"User-Agent": f"TrigoBom/{__version__}"},
            )
            with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
                dados = json.loads(resp.read().decode())

            tag_remota = dados.get("tag_name", "")
            url_release = dados.get("html_url", "")
            if not tag_remota:
                return

            try:
                versao_remota = _versao_tag(tag_remota)
                versao_local = _versao_tag(__version__)
            except InvalidVersion:
                return

            if versao_remota > versao_local:
                self._sinal.emit(tag_remota, url_release)

        except Exception as exc:
            log.debug("Checagem de atualização falhou (silenciada): %s", exc)


class VerificadorAtualizacao(QObject):
    """Emite `nova_versao(tag, url)` se houver release mais nova no GitHub."""

    nova_versao = Signal(str, str)

    def verificar(self):
        worker = _Verificador(self.nova_versao)
        worker.setAutoDelete(True)
        QThreadPool.globalInstance().start(worker)
