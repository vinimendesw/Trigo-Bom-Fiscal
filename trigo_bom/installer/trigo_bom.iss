; TrigoBom Fiscal — Script Inno Setup
;
; Compilar via build.ps1 (passa /DMyAppVersion e /DDistDir automaticamente), ou
; manualmente:
;   iscc.exe /DMyAppVersion=1.0.0 /DDistDir=C:\...\dist\TrigoBom-1.0.0 trigo_bom.iss
;
; Requer Inno Setup 6 (https://jrsoftware.org/isdl.php).

; ── Versão e caminho de entrada ───────────────────────────────────────────────
; MyAppVersion e DistDir são obrigatoriamente passados pelo build.ps1.
; Os #ifndef abaixo servem apenas como fallback para compilação manual avulsa.
#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif
#ifndef DistDir
  ; Ajuste para o caminho real se compilar manualmente sem build.ps1
  #define DistDir "..\dist\TrigoBom-0.0.0"
#endif

#define MyAppName    "TrigoBom Fiscal"
#define MyAppPublisher "TrigoBom"
#define MyAppExeName "TrigoBom.exe"
; AppId FIXO — não alterar entre versões. Garante que upgrades substituam a
; instalação anterior no registro/Painel de Controle em vez de criar uma nova.
#define MyAppId      "{{E7A2F8C3-9D14-4BE8-A5C6-D7E8F9012345}"

; ── [Setup] ───────────────────────────────────────────────────────────────────
[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}

; Diretório de instalação padrão (configurável pelo usuário no instalador)
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
; Compressão LZMA2 — reduz o tamanho do instalador ~40% em relação ao zip padrão
Compression=lzma2
SolidCompression=yes
; Requer privilégios de administrador (necessário para instalar em Program Files
; e para disparar o instalador encadeado do Tesseract)
PrivilegesRequired=admin
; Suporta upgrade in-place: ao reinstalar sobre versão existente, o instalador
; desinstala silenciosamente a versão anterior antes de copiar os novos arquivos.
; %APPDATA%\TrigoBom (trigo_bom.db, config.json) NÃO é tocado — o uninstaller
; padrão do Inno Setup só remove o que foi instalado em {app}, jamais o AppData.
CloseApplications=yes
RestartIfNeededByRun=no
; Ícone da janela de instalação
SetupIconFile=..\app\ui\assets\icone.ico
; Saída: TrigoBomSetup-<versão>.exe na pasta dist/
OutputDir=..\dist
OutputBaseFilename=TrigoBomSetup-{#MyAppVersion}
; Informações exibidas na tela de licença (opcional — remover se não houver licença)
; LicenseFile=license.txt

; ── [Languages] ──────────────────────────────────────────────────────────────
[Languages]
Name: "portuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

; ── [Files] ───────────────────────────────────────────────────────────────────
; Copia todo o conteúdo de dist/TrigoBom-<versão>/ para {app}.
; recursesubdirs garante que _internal/ e subpastas sejam incluídas.
[Files]
Source: "{#DistDir}\*"; \
  DestDir: "{app}"; \
  Flags: recursesubdirs createallsubdirs ignoreversion

; Tesseract OCR — instalador encadeado (UB-Mannheim).
; O arquivo vendor\tesseract-setup.exe deve ser baixado manualmente de:
;   https://github.com/UB-Mannheim/tesseract/wiki
; e colocado em installer\vendor\tesseract-setup.exe antes de compilar.
; A entrada abaixo só é extraída e executada se NeedsTesseract() retornar True.
; deleteafterinstall: remove o arquivo de {tmp} após a instalação do Tesseract,
; sem deixar resíduos no sistema do cliente.
Source: "vendor\tesseract-setup.exe"; \
  DestDir: "{tmp}"; \
  Flags: deleteafterinstall; \
  Check: NeedsTesseract

; ── [Icons] ───────────────────────────────────────────────────────────────────
; Atalhos criados pelo instalador.
; O Inno Setup NÃO cria entradas em %APPDATA% — apenas em {group} (Menu Iniciar)
; e {commondesktop} (Área de Trabalho). Os dados do usuário em %APPDATA%\TrigoBom
; são gerados em runtime pelo próprio app e nunca removidos pelo uninstaller.
[Icons]
Name: "{group}\{#MyAppName}";     Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{group}\Desinstalar {#MyAppName}"; Filename: "{uninstallexe}"

; ── [Run] ─────────────────────────────────────────────────────────────────────
[Run]
; 1. Instala o Tesseract OCR silenciosamente (/S = silent install, flag UB-Mannheim)
;    somente se NeedsTesseract() retornar True (ou seja, se não estiver instalado).
Filename: "{tmp}\tesseract-setup.exe"; \
  Parameters: "/S"; \
  Check: NeedsTesseract; \
  StatusMsg: "Instalando Tesseract OCR (aguarde)..."; \
  Flags: waituntilterminated

; 2. Abre o TrigoBom após a instalação (opcional — usuário pode desmarcar)
Filename: "{app}\{#MyAppExeName}"; \
  Description: "Abrir {#MyAppName} agora"; \
  Flags: nowait postinstall skipifsilent

; ── [UninstallDelete] ─────────────────────────────────────────────────────────
; Lista VAZIA intencionalmente.
; O Inno Setup remove automaticamente os arquivos que ele instalou em {app}.
; %APPDATA%\TrigoBom (banco de dados e configurações do usuário) NÃO é
; referenciado aqui — dados do usuário sobrevivem a qualquer desinstalação
; ou upgrade. Se um dia for necessário oferecer "remoção completa", incluir
; aqui com uma confirmação explícita ao usuário.
[UninstallDelete]
; (intencionalmente vazio — ver comentário acima)

; ── [Code] — Pascal Script ────────────────────────────────────────────────────
[Code]

{ NeedsTesseract: retorna True se o Tesseract OCR ainda não estiver instalado.
  Verificação em três etapas:
    1. Caminho padrão x64 (UB-Mannheim default)
    2. Caminho padrão x86
    3. Resolução via PATH (tesseract.exe acessível sem caminho absoluto)
  Se qualquer etapa confirmar que o Tesseract existe, retorna False e o
  instalador encadeado é pulado — sem forçar reinstalação a cada update do
  TrigoBom (ver CLAUDE.md seção 14.3). }
function NeedsTesseract(): Boolean;
var
  ResultCode: Integer;
begin
  { Verifica instalação padrão x64 (UB-Mannheim instala aqui por padrão) }
  if FileExists('C:\Program Files\Tesseract-OCR\tesseract.exe') then
  begin
    Log('Tesseract encontrado em Program Files (x64) — pulando instalação.');
    Result := False;
    Exit;
  end;

  { Verifica instalação x86 (máquinas mais antigas) }
  if FileExists('C:\Program Files (x86)\Tesseract-OCR\tesseract.exe') then
  begin
    Log('Tesseract encontrado em Program Files (x86) — pulando instalação.');
    Result := False;
    Exit;
  end;

  { Tenta resolver via PATH: `tesseract --version` retorna 0 se o exe
    estiver acessível. A saída vai para nul; só o exit code importa. }
  if Exec(ExpandConstant('{cmd}'), '/C tesseract --version >nul 2>&1',
          '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
  begin
    if ResultCode = 0 then
    begin
      Log('Tesseract encontrado via PATH — pulando instalação.');
      Result := False;
      Exit;
    end;
  end;

  Log('Tesseract não encontrado — será instalado.');
  Result := True;
end;

{ VendorExists: verifica se o arquivo vendor do Tesseract foi incluído no
  instalador. Exibe um aviso claro ao usuário se estiver faltando, em vez
  de falhar silenciosamente. }
function VendorExists(): Boolean;
begin
  Result := FileExists(ExpandConstant('{tmp}\tesseract-setup.exe'));
  if not Result and NeedsTesseract() then
    MsgBox(
      'O Tesseract OCR não está instalado neste computador e o pacote de ' +
      'instalação do Tesseract não foi incluído neste instalador.' + #13#10 +
      #13#10 +
      'Para habilitar a leitura de PDFs com texto corrompido (OCR), instale ' +
      'manualmente o Tesseract OCR em:' + #13#10 +
      'https://github.com/UB-Mannheim/tesseract/wiki' + #13#10 +
      #13#10 +
      'O TrigoBom funcionará normalmente para PDFs comuns. O OCR fica ' +
      'indisponível até o Tesseract ser instalado.',
      mbInformation, MB_OK
    );
end;

{ InitializeSetup: ponto de entrada do script — valida o ambiente antes de
  iniciar a instalação. Retorna False cancela a instalação inteira. }
function InitializeSetup(): Boolean;
begin
  Result := True;  { deixa o instalador prosseguir sempre }
  VendorExists();  { avisa sobre Tesseract faltando, mas não bloqueia }
end;
