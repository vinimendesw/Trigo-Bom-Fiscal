<#
.SYNOPSIS
    Build e empacotamento do TrigoBom Fiscal.

.DESCRIPTION
    1. Extrai a versao de app/__version__.py (fonte unica de verdade).
    2. Roda PyInstaller (--onedir) e renomeia a saida para dist/TrigoBom-<ver>/.
    3. Opcionalmente compila o instalador Inno Setup (TrigoBomSetup-<ver>.exe).

.PARAMETER SemInstalador
    Pula a etapa do Inno Setup (util para testar so o PyInstaller).

.PARAMETER InnoSetupExe
    Caminho para o iscc.exe, caso nao esteja no PATH.
    Padrao: "C:\Program Files (x86)\Inno Setup 6\iscc.exe"

.EXAMPLE
    # Build completo (PyInstaller + Inno Setup):
    .\build.ps1

    # So PyInstaller, sem gerar instalador:
    .\build.ps1 -SemInstalador

    # Caminho personalizado para o Inno Setup:
    .\build.ps1 -InnoSetupExe "D:\InnoSetup\iscc.exe"
#>
param(
    [switch]$SemInstalador,
    [string]$InnoSetupExe = "C:\Program Files (x86)\Inno Setup 6\iscc.exe"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ---- Diretorio raiz do projeto (trigo_bom/) ----------------------------------
$Root    = $PSScriptRoot   # build.ps1 fica em trigo_bom/
$Python  = Join-Path $Root ".venv\Scripts\python.exe"
$PyInst  = Join-Path $Root ".venv\Scripts\pyinstaller.exe"

# ---- Validacoes iniciais -------------------------------------------------------
if (-not (Test-Path $Python)) {
    Write-Error ("venv nao encontrado em $Root\.venv" +
                 " -- rode: python -m venv .venv ; pip install -r requirements.txt")
}

if (-not (Test-Path $PyInst)) {
    Write-Host "PyInstaller nao encontrado no venv -- instalando..."
    & $Python -m pip install pyinstaller --quiet
}

# ---- Le a versao de app/__version__.py ----------------------------------------
# Unica fonte de verdade (CLAUDE.md secao 14.1) -- nao duplicar aqui.
$VersionPy = Join-Path $Root "app\__version__.py"
$Version   = & $Python -c "exec(open(r'$VersionPy').read()); print(__version__)"
if (-not $Version) {
    Write-Error "Nao foi possivel ler __version__ de $VersionPy"
}
Write-Host "Versao: $Version"

# ---- Caminhos de saida --------------------------------------------------------
$DistBase  = Join-Path $Root "dist"
$DistBuild = Join-Path $DistBase "TrigoBom"           # saida padrao do PyInstaller
$DistFinal = Join-Path $DistBase "TrigoBom-$Version"  # renomeado com versao

# ---- Limpeza de builds anteriores ---------------------------------------------
Write-Host "Limpando builds anteriores..."
if (Test-Path $DistBuild) { Remove-Item -Recurse -Force $DistBuild }
if (Test-Path $DistFinal) { Remove-Item -Recurse -Force $DistFinal }
$BuildDir = Join-Path $Root "build"
if (Test-Path $BuildDir)  { Remove-Item -Recurse -Force $BuildDir }

# ---- PyInstaller --------------------------------------------------------------
# --onedir   : pasta com exe + recursos (nao --onefile; CLAUDE.md secao 14.2)
# --windowed : sem janela de console no Windows
# --icon     : icone multi-resolucao da espiga dourada
# --paths    : adiciona app/ ao sys.path da analise (imports sem pacote raiz)
# --add-data : copia dados nao-Python lidos em runtime via __file__:
#              app\ui -> ui\           (HTML, CSS, JS, assets/icone.ico)
#              app\db\schema.sql -> db\ (lido em repositorio.py)
# --hidden-import : modulos importados via try/except (nao detectados estaticamente)
# --collect-all fitz : PyMuPDF 1.27+ tem estrutura de pacote nao-trivial
Write-Host "Rodando PyInstaller..."
& $PyInst `
    --noconfirm `
    --windowed `
    --icon        "app\ui\assets\icone.ico" `
    --name        "TrigoBom" `
    --paths       "app" `
    --add-data    "app\ui:ui" `
    --add-data    "app\db\schema.sql:db" `
    --hidden-import "pytesseract" `
    --hidden-import "PIL.Image" `
    --collect-all "fitz" `
    "app\main.py"

if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller falhou (exit code $LASTEXITCODE)"
}

# ---- Renomeia a saida incluindo a versao --------------------------------------
Write-Host "Renomeando dist\TrigoBom -> dist\TrigoBom-$Version..."
Rename-Item -Path $DistBuild -NewName "TrigoBom-$Version"
Write-Host "Build concluido: $DistFinal"

# ---- Inno Setup (opcional) ----------------------------------------------------
if ($SemInstalador) {
    Write-Host ""
    Write-Host "=== Build finalizado: TrigoBom $Version (sem instalador) ==="
    exit 0
}

$IssFile = Join-Path $Root "installer\trigo_bom.iss"

if (-not (Test-Path $IssFile)) {
    Write-Warning "installer\trigo_bom.iss nao encontrado -- pulando etapa do Inno Setup."
}
elseif (-not (Test-Path $InnoSetupExe)) {
    Write-Warning ("iscc.exe nao encontrado em: $InnoSetupExe" +
                   " -- Instale o Inno Setup 6 ou use -InnoSetupExe [caminho]. Pulando.")
}
else {
    # Vendor do Tesseract: avisa se o .exe ainda nao foi baixado
    $TessVendor = Join-Path $Root "installer\vendor\tesseract-setup.exe"
    if (-not (Test-Path $TessVendor)) {
        Write-Warning ("installer\vendor\tesseract-setup.exe nao encontrado." +
                       " Baixe o instalador UB-Mannheim em " +
                       "https://github.com/UB-Mannheim/tesseract/wiki" +
                       " e salve como installer\vendor\tesseract-setup.exe." +
                       " O instalador sera gerado SEM incluir o Tesseract.")
    }

    Write-Host "Compilando instalador Inno Setup..."
    & $InnoSetupExe `
        "/DMyAppVersion=$Version" `
        "/DDistDir=$DistFinal" `
        $IssFile

    if ($LASTEXITCODE -ne 0) {
        Write-Error "Inno Setup falhou (exit code $LASTEXITCODE)"
    }

    $InstallerPath = Join-Path $DistBase "TrigoBomSetup-$Version.exe"
    Write-Host "Instalador gerado: $InstallerPath"
}

Write-Host ""
Write-Host "=== Build finalizado: TrigoBom $Version ==="
