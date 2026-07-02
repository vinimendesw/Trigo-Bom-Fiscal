"""
Verificação e instalação automática de atualizações via GitHub Releases.

Fluxo (CLAUDE.md, seção 14.5): checa a release mais recente do repositório,
compara com `app.__version__.__version__`; se houver versão mais nova, baixa
o instalador (asset .exe anexado à release) e o executa em modo silencioso,
sem pedir confirmação ao usuário em nenhuma etapa — decisão de produto
(cliente único, baixo volume de releases). O instalador precisa de elevação
administrativa (PrivilegesRequired=admin no Inno Setup); o Windows exige o
prompt de UAC para isso — não há como suprimi-lo a partir do processo filho,
é a única interação que o sistema operacional força.

Depois de instalar, o próprio instalador fecha o TrigoBom em execução
(CloseApplications=yes) e o reabre ao final (ver [Run] em trigo_bom.iss).

Toda a checagem é best-effort: qualquer falha de rede/parsing resulta em
`None`/exceção tratada pelo chamador — uma checagem de atualização nunca deve
travar ou atrapalhar o uso normal do app.
"""

import ctypes
import json
import re
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from __version__ import __version__ as VERSAO_ATUAL

REPO = "vinimendesw/Trigo-Bom-Fiscal"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
_USER_AGENT = "TrigoBom-Fiscal-Updater"
_TIMEOUT_VERIFICACAO_S = 15
_TIMEOUT_DOWNLOAD_S = 60


def _parse_versao(v: str) -> tuple:
    """'v1.2.3' ou '1.2.3' -> (1, 2, 3). Tupla vazia se ilegível."""
    if not v:
        return ()
    m = re.match(r"v?(\d+)\.(\d+)\.(\d+)", v.strip())
    return tuple(int(x) for x in m.groups()) if m else ()


def _versao_mais_nova(remota: str, local: str) -> bool:
    vr, vl = _parse_versao(remota), _parse_versao(local)
    return bool(vr) and vr > vl


def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={
        "User-Agent": _USER_AGENT,
        "Accept": "application/vnd.github+json",
    })
    with urllib.request.urlopen(req, timeout=_TIMEOUT_VERIFICACAO_S) as resp:
        return json.loads(resp.read().decode("utf-8"))


def verificar_atualizacao() -> dict | None:
    """
    Consulta a release mais recente no GitHub Releases.

    Retorna None se: não houver versão mais nova que `VERSAO_ATUAL`, a
    checagem falhar (rede indisponível, resposta inesperada) ou a release não
    tiver um asset de instalador (nome iniciando com "TrigoBomSetup" e
    terminando em ".exe" — mesmo padrão gerado por build.ps1). Nunca levanta
    exceção.
    """
    try:
        release = _get_json(API_LATEST)
    except Exception:
        return None

    tag = release.get("tag_name", "") or ""
    if not _versao_mais_nova(tag, VERSAO_ATUAL):
        return None

    asset = next(
        (a for a in release.get("assets", [])
         if str(a.get("name", "")).startswith("TrigoBomSetup")
         and str(a.get("name", "")).endswith(".exe")),
        None,
    )
    if not asset:
        return None

    return {
        "versao": tag.lstrip("vV"),
        "versao_atual": VERSAO_ATUAL,
        "asset_url": asset.get("browser_download_url"),
        "asset_nome": asset.get("name"),
        "tamanho": asset.get("size"),
    }


def baixar_instalador(asset_url: str, asset_nome: str, tamanho_esperado: int | None = None) -> Path:
    """
    Baixa o instalador para uma pasta temporária dedicada
    (%TEMP%\\TrigoBomUpdate\\). Levanta exceção se o download falhar ou se o
    tamanho final não bater com o esperado (download incompleto/corrompido) —
    nunca dispara um instalador que não foi baixado por completo.
    """
    destino_dir = Path(tempfile.gettempdir()) / "TrigoBomUpdate"
    destino_dir.mkdir(parents=True, exist_ok=True)
    destino = destino_dir / asset_nome

    req = urllib.request.Request(asset_url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=_TIMEOUT_DOWNLOAD_S) as resp, open(destino, "wb") as f:
        while True:
            chunk = resp.read(1024 * 256)
            if not chunk:
                break
            f.write(chunk)

    if tamanho_esperado and destino.stat().st_size != tamanho_esperado:
        destino.unlink(missing_ok=True)
        raise IOError("Download incompleto: tamanho do arquivo não confere com o esperado.")

    return destino


def instalar_silenciosamente(caminho_instalador: Path) -> None:
    """
    Dispara o instalador em modo totalmente silencioso (sem wizard, sem
    caixas de mensagem), elevado via UAC. A elevação é exigida pelo Windows
    (PrivilegesRequired=admin) e não pode ser suprimida por este processo —
    é o único ponto em que o sistema operacional interrompe o usuário; fora
    isso, nenhuma confirmação é pedida.
    """
    parametros = "/VERYSILENT /SUPPRESSMSGBOX /NORESTART"
    SW_HIDE = 0
    # ShellExecuteW com verbo "runas" solicita elevação (equivalente a
    # "Executar como administrador"); QProcess não tem suporte nativo a isso.
    resultado = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", str(caminho_instalador), parametros, None, SW_HIDE
    )
    # ShellExecuteW retorna >32 em sucesso; <=32 é código de erro (ex.: 5 =
    # usuário negou a elevação UAC, 2 = arquivo não encontrado).
    if resultado <= 32:
        raise OSError(f"Falha ao iniciar o instalador (código {resultado}).")
