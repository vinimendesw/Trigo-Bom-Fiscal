# CHANGELOG — TrigoBom Fiscal

Histórico de mudanças do projeto, registrado a cada sessão de trabalho com o Claude.

Formato de cada entrada:

```
## [AAAA-MM-DD] Título curto da sessão

- Mudança 1
- Mudança 2

**Arquivos afetados:** lista de arquivos/pastas alterados
```

Entradas mais recentes ficam no topo.

---

## [2026-07-02] Atualização automática via GitHub Releases (checagem, download e instalação silenciosa)

- Novo módulo `app/atualizacao.py`: consulta `GET /repos/vinimendesw/Trigo-Bom-Fiscal/releases/latest` (GitHub API, sem autenticação), compara a tag com `app.__version__.__version__`, baixa o asset `TrigoBomSetup-X.Y.Z.exe` da release mais nova (verificando o tamanho do download contra o declarado pela API) e dispara o instalador via `ShellExecuteW` com verbo `"runas"` e `/VERYSILENT /SUPPRESSMSGBOX /NORESTART` — sem nenhuma confirmação do app (decisão de produto). A única interação inevitável é o prompt de UAC do próprio Windows, exigido por `PrivilegesRequired=admin` no instalador.
- `bridge.py`: pipeline assíncrono em `QThreadPool` (`_TarefaAtualizacao`/`_EmissorAtualizacao`) com sinal `atualizacaoStatus` (estados `verificando`/`nenhuma`/`baixando`/`instalando`/`erro`) e slot `verificar_atualizacao()` (com trava contra chamadas concorrentes). Ao terminar de disparar o instalador, pede o fechamento do app (`prontoParaFechar` → `QApplication.quit()`), preservando o backup final e a remoção do lock já existentes no `aboutToQuit` do `main.py`.
- `main.py`: dispara `bridge.verificar_atualizacao()` 5s após abrir a janela (checagem automática em background, sem bloquear a abertura).
- UI (`index.html`/`app.js`): card "Atualizações" em Configurações com versão instalada, status da checagem e botão manual "Verificar atualizações" (mesmo pipeline da checagem automática). Toasts informativos (sem pedir confirmação) nos estados baixando/instalando/erro.
- `installer/trigo_bom.iss`: removido `skipifsilent` da entrada `[Run]` que reabre o TrigoBom após instalar — sem isso, uma instalação silenciosa (disparada pela atualização automática) deixaria o app fechado até o usuário abri-lo manualmente. Comportamento de instalação interativa não muda (checkbox "Abrir agora" continua marcado por padrão, usuário pode desmarcar).
- Corrigido texto desatualizado em Configurações ("a cada 10 minutos" → "a cada 3 minutos", refletindo o intervalo de backup já reduzido nesta sessão).
- Validação: testes de lógica pura (`_parse_versao`, `_versao_mais_nova`, seleção de asset, download via `file://` com verificação de integridade de tamanho); teste de integração do `Bridge` com `QApplication` cobrindo a sequência completa de estados, a trava contra checagens concorrentes e o pedido de fechamento do app; suíte completa (245 testes) passando; card de Configurações conferido visualmente no preview.

**Arquivos afetados:** `trigo_bom/app/atualizacao.py` (novo), `trigo_bom/app/bridge.py`, `trigo_bom/app/main.py`, `trigo_bom/app/ui/app.js`, `trigo_bom/app/ui/index.html`, `trigo_bom/installer/trigo_bom.iss`

## [2026-07-02] Dedup por número da NF passa a consultar o banco diretamente

- A 2ª camada de verificação de duplicidade (por número da NF) na revisão de PDFs detectados deixou de comparar contra a lista em memória `estado.nfs` e passa a consultar o banco diretamente, evitando falso-negativo quando a lista do front-end estiver desatualizada. Novo `repositorio.numero_nf_existe()` + slot `Bridge.numero_nf_existe`; `app.js` atualiza o aviso de forma assíncrona ao abrir a revisão. Comportamento mantido: alerta visível, não bloqueia.

**Arquivos afetados:** `trigo_bom/app/db/repositorio.py`, `trigo_bom/app/bridge.py`, `trigo_bom/app/ui/app.js`

## [2026-07-02] Máscara de valores, pasta de entrada com leitura automática e backup a cada 3 min

- **Máscara de moeda (R$):** novas funções `mascararMoeda()`/`moedaParaMascara()` em `app.js` no padrão "dígitos como centavos" (ex.: digitar `125000` exibe `1.250,00`), aplicadas via listener `input` no campo `#nf-valor` e no input de `valor_unitario` das linhas de item da NF. Valores existentes são exibidos já formatados; o valor salvo continua saindo por `parseBRL()` (float), preservando a compatibilidade.
- **Pasta de entrada monitorada (tempo real):** a `pasta_nfs` (já configurável) passa a ser também monitorada por `QFileSystemWatcher`. Ao detectar um PDF novo, a extração assíncrona (`extrair_nf` via `QThreadPool`) é disparada e o resultado vai para uma **fila de revisão** na tela Notas Fiscais — nada é salvo automaticamente. Baseline/dedup por nome: um PDF só é "novo" se seu nome não constar em `notas_fiscais.arquivo_pdf` (cobre o histórico já importado). 2ª camada de dedup por número da NF: aviso visível na revisão (não bloqueia). Descartar um item apenas o dispensa da revisão atual — reaparece na próxima verificação (não é ignorado permanentemente). O watcher é reiniciado quando a pasta é alterada em Configurações. Salvar pela revisão reaproveita `salvar_nf`; como o PDF já está na pasta, `_copiar_pdf` não regrava (`dest == src`), evitando loop no watcher.
- **Backup automático:** intervalo do timer reduzido de 10 para 3 minutos (`_BACKUP_INTERVAL_MS` em `main.py`). O debounce de 3s do backup por escrita (`bridge.py`) não foi alterado.
- Validação: testes de lógica da máscara (formatação em tempo real + round-trip `parseBRL`); smoke test do watcher (baseline, detecção, dedup por nome, descarte→reaparecimento, troca de pasta); conferência do estilo da fila de revisão e do aviso de duplicidade via inspeção de CSS no preview; suíte completa (245 testes) passando.

**Arquivos afetados:** `trigo_bom/app/main.py`, `trigo_bom/app/bridge.py`, `trigo_bom/app/db/repositorio.py`, `trigo_bom/app/ui/app.js`, `trigo_bom/app/ui/index.html`, `trigo_bom/app/ui/styles.css`

## [2026-07-02] Correção do KPI "A receber" negativo e do ícone de Configurações

- **BUG 1 — KPI "A receber" negativo:** o cálculo de `kpi-saldo` no dashboard passava a usar a mesma base de competência das entradas (`nfsMes`, por `data_emissao`). "A receber" agora é a soma das NFs do mês emitidas e ainda não pagas (`status_pagamento != 'pago'`), em vez de `entradas - recebido`. Isso elimina o saldo negativo quando uma NF é emitida em um mês e paga no seguinte. Os KPIs "Entradas" e "Recebido" foram mantidos com suas bases originais (intencionalmente diferentes).
- **BUG 2 — ícone de Configurações descentralizado:** o `<path>` customizado e assimétrico da engrenagem foi substituído pelo ícone "settings" padrão do Feather/Lucide (simétrico), mantendo o `<circle cx="12" cy="12" r="3">` e os atributos do SVG.
- Validação: ícone conferido visualmente no preview (engrenagem simétrica e centrada); lógica do dashboard testada com NF emitida em Jan e paga em Fev, confirmando que "A receber" não fica negativo.

**Arquivos afetados:** `trigo_bom/app/ui/app.js`, `trigo_bom/app/ui/index.html`

## [2026-06-30] Infraestrutura de build e empacotamento implementada

- `requirements.txt` atualizado: todos os `>=` trocados por `==` com as
  versões exatas instaladas no venv (PySide6 6.11.1, pdfplumber 0.11.10,
  PyMuPDF 1.27.2.3, openpyxl 3.1.5, pytesseract 0.3.13, Pillow 12.2.0).
  Builds agora são reprodutíveis sem risco de versão de lib diferente.
- `build.ps1` criado: script PowerShell que lê a versão de `app/__version__.py`
  (sem duplicar o número), roda o PyInstaller com `--onedir` e os `--add-data`
  corretos, renomeia a saída para `dist/TrigoBom-<versão>/` e chama o Inno Setup
  automaticamente. Suporta flag `-SemInstalador` para build só do PyInstaller.
- `installer/trigo_bom.iss` criado: script Inno Setup 6 que empacota o dist
  inteiro, cria atalhos na área de trabalho e no menu Iniciar, usa AppId fixo
  (não muda entre versões, garantindo upgrade in-place), gera
  `dist/TrigoBomSetup-<versão>.exe`. Inclui Pascal Script `NeedsTesseract()`
  que verifica em três etapas se o Tesseract já está instalado antes de disparar
  o instalador encadeado. `%APPDATA%\TrigoBom` não é referenciado em nenhuma
  seção `[Files]` ou `[UninstallDelete]` — banco e config sobrevivem a upgrades.
- `installer/vendor/LEIA-ME.txt` criado: instrui onde baixar o
  `tesseract-setup.exe` (UB-Mannheim) que não entra no repositório por tamanho.
- CLAUDE.md seção 9 atualizada com os comandos reais de build e pré-requisitos.

**Arquivos afetados:**
`trigo_bom/requirements.txt`, `trigo_bom/build.ps1`,
`trigo_bom/installer/trigo_bom.iss`, `trigo_bom/installer/vendor/LEIA-ME.txt`,
`CLAUDE.md`

---

## [2026-06-30] Estratégia de build, distribuição e atualizações definida

- Definida a arquitetura de empacotamento e entrega para o cliente único atual:
  PyInstaller `--onedir` (em vez de `--onefile`, por velocidade de abertura e
  menor chance de falso positivo de antivírus), `requirements.txt` com versões
  fixadas para build reprodutível, instalador único via Inno Setup que preserva
  `%APPDATA%\TrigoBom` entre versões e encadeia a instalação do Tesseract OCR
  (silenciosa, só se ainda não estiver presente). Sem assinatura de código por
  enquanto (cliente único).
- Distribuição via GitHub Releases (repositório privado): cada versão é uma
  tag + asset; entrega ao cliente continua manual. Atualização também
  permanece manual por ora — uma fase futura de notificação in-app (sem
  auto-instalação) foi desenhada mas não implementada.
- Criada a constante de versão única do projeto em `app/__version__.py`
  (semver), referenciada pela nova seção 14 do CLAUDE.md.
- Documentado tudo na nova seção 14 (Distribuição e Atualizações) do
  CLAUDE.md; seção 9 atualizada para apontar para ela e refletir `--onedir`.

**Arquivos afetados:** `CLAUDE.md`, `trigo_bom/app/__version__.py`

---

## [2026-06-30] Teste de capacidade da inclusão em lote

- Criado `tests/test_capacidade_lote.py` com 25 testes de benchmark cobrindo
  as 4 camadas do fluxo de lote (persistência NF, persistência OC, leitura/agregação,
  overhead de conexão), além de cenários de uso normal e pico retroativo.
- Todos os testes medem tempo real com `time.perf_counter` e falham se ultrapassarem
  os thresholds definidos no arquivo (documentação viva dos limites do sistema).

**Arquivos afetados:** `trigo_bom/tests/test_capacidade_lote.py`

---

## [2026-06-30] Comando PyInstaller atualizado com --icon

- Adicionado `--icon app/ui/assets/icone.ico` ao comando de build no CLAUDE.md (seção 9),
  garantindo que o `.exe` gerado carregue o ícone da espiga dourada — essencial para
  que o ícone apareça corretamente quando o app for fixado na barra de tarefas.

**Arquivos afetados:** `CLAUDE.md`

---

## [2026-06-30] Ícone da barra de tarefas: .ico multi-resolução

- Causa do ícone do Python persistir na barra de tarefas identificada: o
  `icone.ico` continha **apenas a imagem 256×256**. O Qt escala dentro do processo,
  mas a shell do Windows lê os tamanhos pequenos embutidos no `.ico`; sem 16/24/32/48
  ela cai de volta para o ícone do executável hospedeiro (python.exe).
- `icone.ico` regenerado a partir de `icone.png` (1523×1523) com 7 resoluções
  (16, 24, 32, 48, 64, 128, 256). `main.py` não precisou de mudança — o
  `AppUserModelID` e o `setWindowIcon` já estavam corretos.
- Nota para o empacotamento: o PyInstaller deve receber `--icon` apontando para
  `app/ui/assets/icone.ico`, para o próprio `.exe` carregar o ícone.

**Arquivos afetados:** `trigo_bom/app/ui/assets/icone.ico`

---

## [2026-06-30] Correções priorizadas: perda de dados, conexões, extração, XSS e extração assíncrona

Bateria de correções por risco (P0 → P2), incluindo a extração assíncrona (item 10,
implementada na opção signal-based após confirmação).

**P0 — Risco de perda de dados**
- Exclusão de NF não apaga mais o PDF **original** do usuário: `excluir_nf` /
  `excluir_nfs_em_massa` só removem o arquivo do disco quando ele está fisicamente
  dentro da Pasta de NFs configurada (cópia gerenciada). Antes, sem a pasta
  configurada, `arquivo_pdf` apontava para o original e era apagado. Novo helper
  `_arquivo_em_pasta_gerenciada` (compara caminhos resolvidos com `is_relative_to`).
- Backup agora usa snapshot consistente do SQLite (`Connection.backup()`) em vez de
  `shutil.copy2`, evitando cópia inconsistente com o banco em uso (WAL/transação).
  Metadado gravado atomicamente (arquivo temporário + `os.replace`) e só após o
  `.db`; cai para cópia direta quando a origem não é um SQLite válido.
- Comparação "backup mais novo" passou a usar um **contador de versão monotônico**
  (campo `versao` no metadado, persistido em `APPDATA/TrigoBom`), independente do
  relógio entre dispositivos; timestamp vira só fallback de compatibilidade.

**P1 — Correção funcional**
- Conexões SQLite agora são fechadas com `contextlib.closing` em todas as funções do
  repositório (antes o `with` só gerenciava a transação, vazando o handle).
- `limpar_valor` corrigido para milhar sem centavos: "1.500" → 1500 (antes 1,5).
- Nome de lista derivado do id (AUTOINCREMENT, nunca reusado) em vez de `COUNT(*)` —
  elimina nomes duplicados após exclusão.
- `_extrair_numero` preserva zeros à esquerda e não devolve mais "0" quando vazio.
- `escapeHtml` aplicado a todo texto de extração/banco interpolado em `innerHTML`
  (descrição, fornecedor, órgão, categoria, número, NCM/CFOP) — evita quebra de
  render/injeção com `<`, `&`, `"`.

**P2 — Performance / organização**
- Extração de valores/datas/padrões deduplicada em `app/extracao/util.py`
  (`limpar_valor`, `primeiro_match`, `normalizar_data`); `nf.py` e `ordem_compra.py`
  passam a importar de lá (aliases privados preservados p/ compatibilidade de testes).
- Removidos da bridge os slots sem uso no frontend (`listar_nfs_filtrado`,
  `totais_nf_por_orgao`, `listar_ordens_compra`, `listar_ordens_compra_com_itens`,
  `atualizar_status_entrega_oc`, `excluir_ordens_compra_em_massa`). As funções de
  repositório correspondentes foram mantidas por ainda serem cobertas por testes.
- **Extração assíncrona (item 10):** a leitura de PDF/XML deixou de rodar no corpo
  do `@Slot` (que bloqueava o event loop e congelava a janela). Agora é despachada
  para um worker do `QThreadPool` (`_TarefaExtracao`/`_EmissorExtracao`) e o
  resultado volta ao JS pelo sinal Qt `extracaoConcluida`, correlacionado por
  `request_id`. O JS ganhou `extrairAsync` + estado visual "Lendo arquivo…" (banner
  com spinner) nas telas de inclusão de NF e OC; a conferência manual antes de
  salvar é preservada. Validado por smoke test de runtime (Qt offscreen).
- Testes novos/ajustados para todos os itens acima (suíte: 220 passando).

**Correção de artefatos visuais (tela Notas Fiscais)**
- (De)selecionar uma NF deixou de reconstruir o board inteiro: o handler do
  checkbox (e do "selecionar todas"/"cancelar") chamava `renderNFs()` a cada
  clique, recriando todos os cards via `innerHTML` — destruindo o próprio checkbox
  clicado e gerando ghosting/flicker no QWebEngine. Agora atualiza só a barra de
  marcação em massa e o estado dos checkboxes existentes (`atualizarBarraMassa`),
  sem rebuild — mesma classe de bug já tratada na tela de listas.

**Arquivos afetados:** `trigo_bom/app/db/repositorio.py`, `trigo_bom/app/backup.py`,
`trigo_bom/app/bridge.py`, `trigo_bom/app/extracao/util.py` (novo),
`trigo_bom/app/extracao/nf.py`, `trigo_bom/app/extracao/ordem_compra.py`,
`trigo_bom/app/ui/app.js`, `trigo_bom/app/ui/index.html`, `trigo_bom/app/ui/styles.css`,
`trigo_bom/tests/test_limpar_valor.py`,
`trigo_bom/tests/test_repositorio_nf_exclusao.py`, `trigo_bom/tests/test_lista_compra.py`,
`trigo_bom/tests/test_backup_lock.py`, `trigo_bom/tests/test_estrutura_extracao.py`

---

## [2026-06-29] Substituição do ícone por arquivo .ico oficial

- Arquivo `Logo-trigo-Bom.ico` (fornecido pelo usuário) copiado para `assets/icone.ico`
- `main.py` simplificado: aponta direto para `icone.ico`, removendo a lógica de conversão PNG→ICO via Pillow

**Arquivos afetados:** `trigo_bom/app/main.py`, `trigo_bom/app/ui/assets/icone.ico` (novo)

---

## [2026-06-29] Ícone da espiga dourada na barra de tarefas do Windows

- Adicionada chamada `SetCurrentProcessExplicitAppUserModelID` via `ctypes` antes de criar a `QApplication`, fazendo o Windows exibir o ícone do TrigoBom (e não o do Python) na barra de tarefas

**Arquivos afetados:** `trigo_bom/app/main.py`

---

## [2026-06-29] Integração das logos TrigoBom na UI e ícone da aplicação

- Logo horizontal adicionada ao topo da sidebar em `index.html` (substituiu texto puro pelo `<img>`)
- Favicon da aplicação definido como `icone.png` via `<link rel="icon">` no HTML
- `main.py` passa a definir o ícone da janela e do app (barra de tarefas) com `QIcon` a partir de `assets/icone.png`
- Estilos da `.logo` atualizados em `styles.css` para exibir a imagem com `width: 100%` e proporção automática
- Adicionados os arquivos de imagem: `logo-horizontal.png` (sidebar) e `icone.png` (favicon/janela)

**Arquivos afetados:** `trigo_bom/app/ui/index.html`, `trigo_bom/app/ui/styles.css`, `trigo_bom/app/main.py`, `trigo_bom/app/ui/assets/logo-horizontal.png` (novo), `trigo_bom/app/ui/assets/icone.png` (novo)

---

## [2026-06-29] Correção de performance e artefatos visuais na tela de Lista de compras

Investigação de relatos de lentidão, travamentos e artefatos visuais na tela de listas. Identificadas e corrigidas 4 causas:

### 1 — FAB clicava em botão inexistente
`FAB_CONFIG.agenda` apontava para `btn-incluir-oc`, removido quando a tela passou a usar listas. Cada clique no botão flutuante disparava `null.click()` (TypeError). Corrigido para `btn-nova-lista`.

### 2 — Rebuild total do DOM dentro do handler de status (causa dos artefatos)
Ao trocar o status de uma lista, o callback chamava `renderListaCompras()`, que fazia `container.innerHTML = ...` reconstruindo **todos** os cards — inclusive o próprio `<select>` que disparou o evento. No QWebEngine/Chromium isso gerava artefatos visuais (dropdown fantasma, flicker) e fechava todos os cards abertos. Agora o handler atualiza **apenas a pill** da lista afetada, sem tocar no resto do DOM.

### 3 — Estado aberto/fechado dos cards era perdido a cada render
Adicionados `estado.listasAbertas` e `estado.ocsAbertas` (Sets de ids). O HTML do card aplica a classe `aberto` a partir desses Sets e os toggles os mantêm, preservando o que está expandido entre re-renders (ex.: após incluir OCs ou excluir).

### 4 — Backup síncrono bloqueava a UI a cada escrita (causa da lentidão/travamento)
`_fazer_backup()` no bridge fazia `shutil.copy2` do banco inteiro na thread principal a cada operação (troca de status, exclusão, cada OC de um lote). Em pasta de backup lenta (HD externo) ou sincronizada (Drive/OneDrive), cada clique congelava a tela. Implementado **debounce via QTimer** (`_BACKUP_DEBOUNCE_MS = 3000`): escritas sucessivas reagendam um único backup para 3s após a última. O `aboutToQuit` em `main.py` continua forçando o backup final, então nada se perde ao fechar.

### Refatoração de apoio
`renderListaCompras` dividida em `_htmlCardLista(lista)` e `_vincularEventosListas(container)` para legibilidade; removida a linha de comentário duplicada.

**Total da suíte:** 204 testes, todos passando.

**Arquivos afetados:** `app/ui/app.js`, `app/bridge.py`

---

## [2026-06-29] Lista de compras: listas manuais com OCs em lote e itens agregados

### Decisão de produto
A tela "Lista de compras" passa a organizar OCs em **listas manuais** criadas pelo usuário. Cada lista agrupa N OCs adicionadas em lote e exibe os itens somados quando a mesma descrição aparece em mais de uma OC (normalização por lowercase + remoção de acentos). OCs incluídas antes desta versão ficam numa seção "Sem lista".

### Backend
- `app/db/schema.sql`: nova tabela `listas_compra` (id, nome, data_prevista, status_entrega, criado_em)
- `app/db/repositorio.py`:
  - `_migrar()`: cria `listas_compra` e adiciona `lista_id` FK em `ordens_compra` se não existir
  - `_normalizar(s)`: lowercase + unicodedata sem acentos para comparação de descrições
  - `_agregar_itens(itens)`: agrupa por chave normalizada, soma quantidade e valor_total, mantém o primeiro valor_unitario
  - `_proximo_nome_lista(conn)`: gera "Lista 01", "Lista 02", etc.
  - `criar_lista(dados_json)` → `{id, nome}`
  - `listar_listas_com_ocs()` → listas com OCs e `itens_agregados` aninhados
  - `listar_ocs_sem_lista()` → OCs com `lista_id IS NULL`
  - `atualizar_status_lista(dados_json)` → `{ok}`
  - `atualizar_lista(dados_json)` → `{ok}`
  - `excluir_lista(lista_id)` → OCs ficam órfãs (lista_id = NULL), não são excluídas
  - `salvar_ordem_compra` atualizado para aceitar `lista_id`
- `app/exportacao/lista_compra_xlsx.py` (novo): exporta itens agregados da lista para `.xlsx`

### Bridge
- Novos slots: `criar_lista`, `listar_listas_com_ocs`, `listar_ocs_sem_lista`, `atualizar_status_lista`, `atualizar_lista`, `excluir_lista`, `exportar_lista_xlsx`

### UI
- `app/ui/index.html`: view "Lista de compras" redesenhada — botão "Nova lista", container de cards de lista, seção "Sem lista"; modais `#modal-nova-lista` e `#modal-excluir-lista`
- `app/ui/app.js`:
  - `renderListaCompras()`: cards de lista com itens agregados + sub-lista colapsável de OCs
  - `_htmlOCInterna(oc)`: HTML reutilizável para OC dentro de lista ou seção sem lista
  - `criarLista()`, `abrirIncluirOCsNaLista(listaId)`, `exportarListaXlsx(listaId)`, `abrirModalExcluirLista`, `fecharModalExcluirLista`, `confirmarExcluirLista`
  - `recarregarListas()`: reload combinado de listas + OCs sem lista
  - `salvarOCAtual` atualizado para incluir `lista_id` no payload
  - `processarProximaOC` atualizado para usar `recarregarListas` ao finalizar lote
- `app/ui/styles.css`: estilos para `.lista-card`, `.lista-agregados`, `.lista-ocs-*`, `.secao-titulo`

### Testes
- `tests/test_lista_compra.py` (novo): 19 testes — criação, nomes auto-incrementais, OCs vinculadas, OCs sem lista, agregação (itens iguais somados, normalização case + acentos, itens diferentes separados), status por lista, exclusão, isolamento entre listas

**Total da suíte:** 204 testes, todos passando.

**Arquivos afetados:** `app/db/schema.sql`, `app/db/repositorio.py`, `app/exportacao/lista_compra_xlsx.py` (novo), `app/bridge.py`, `app/ui/index.html`, `app/ui/app.js`, `app/ui/styles.css`, `tests/test_lista_compra.py` (novo)

---

## [2026-06-29] Dashboard: gráfico de pizza por órgão substituído por Faturado x Recebido

- O card "Distribuição por órgão" (pizza, baseado só em NFs pagas no mês) foi substituído por um gráfico de barras agrupadas "Faturado x Recebido por órgão", mostrando para cada órgão duas barras no mês selecionado: Faturado (regime de competência, por `data_emissao`) e Recebido (regime de caixa, por `data_pagamento`). Objetivo: deixar explícita a mistura de bases que já existia nos KPIs (uma NF emitida em um mês pode ser paga em outro) e dar visibilidade por órgão de quanto foi faturado vs. efetivamente recebido — antes a pizza só mostrava a distribuição do valor recebido, sem comparar com o faturado.
- Decisão de produto (sessão com o usuário, modo de discussão): entre 3 bases possíveis para "o que deveria entrar" (emissão / vencimento / pagamento), optou-se por **emissão**; entre gráficos separados ou combinados, optou-se por **combinado**; e o escopo ficou restrito ao **mês atual** selecionado no dashboard (sem virar série histórica de 6 meses).
- `renderPieOrgao()` foi removido e substituído por `renderBarsOrgao()` em `app.js`; a constante `CORES_ORGAO` ficou sem uso após a remoção da pizza (mantida no código, não removida nesta sessão).

**Arquivos afetados:** `trigo_bom/app/ui/index.html`, `trigo_bom/app/ui/styles.css`, `trigo_bom/app/ui/app.js`

---

## [2026-06-29] Repaginação visual: botão flutuante de incluir, ícones na sidebar e mais profundidade

- Botões "Incluir NF" e "Incluir OC" deixaram de viver no topheader (pouco visíveis, comprimidos na barra preta) e passaram a um botão flutuante (FAB) fixo no canto inferior direito, que troca de ícone/texto/ação conforme a view ativa (Notas Fiscais → Incluir NF, Lista de Compras → Incluir OC). Os botões originais continuam no DOM (ocultos via `display:none`) para preservar os handlers existentes — o FAB apenas delega o clique a eles. Tamanho do FAB aumentado (padding, fonte e ícone maiores) a pedido do usuário, para reforçar a visibilidade.
- Sidebar: pontinhos de navegação substituídos por ícones SVG inline (dashboard, carrinho, recibo, engrenagem), sem depender de fonte de ícone externa (app roda offline).
- Sombras dos cards (`.card`, `.kpi-card`, `.nf-card`, `.oc-card`, `.task-card`) ficaram mais presentes, com leve elevação no hover dos cards clicáveis — reduz o minimalismo "flat" anterior sem mudar paleta de cores.
- Decisão de produto (sessão com o usuário): variação de estilo escolhida entre 3 propostas foi a "Variação A" — FAB em formato pill com ícone+texto e sombra moderada, ícones outline simples.
- Filtro da tela Notas Fiscais redesenhado: o filtro por categoria foi removido (a pedido do usuário) e os filtros restantes (órgão, status, mês) deixaram de ficar sempre visíveis na barra — agora ficam num painel recolhível, aberto por um botão "Filtros" com badge mostrando quantos filtros estão ativos e um resumo em texto ao lado (ex.: "Saúde · Não pagas"). Decisão de produto: "Variação B" entre 3 propostas (chips de status / painel recolhível / tags de órgão).

**Arquivos afetados:** `trigo_bom/app/ui/index.html`, `trigo_bom/app/ui/styles.css`, `trigo_bom/app/ui/app.js`

---

## [2026-06-29] Exclusão de NFs, dashboard com base de pagamento e remoção de categoria/itens do formulário de NF

### 1 — Exclusão de Notas Fiscais (individual e em massa)
- `app/db/repositorio.py`: `excluir_nf(nota_fiscal_id)` — deleta o registro, remove itens em cascata (`ON DELETE CASCADE`) e apaga o arquivo PDF do disco (falha na remoção do arquivo é ignorada, o registro sempre é excluído); `excluir_nfs_em_massa(dados_json)` — mesma lógica em transação única para múltiplos ids
- `app/bridge.py`: slots `excluir_nf(int)` e `excluir_nfs_em_massa(str)`, ambos chamando `_fazer_backup()` após deletar
- `app/ui/index.html`: botão "Excluir selecionadas" adicionado à `#massa-bar`; modal `#modal-excluir-nf` com mensagem adaptada para individual (1 NF) e em massa (N NFs)
- `app/ui/app.js`: estado `nfExcluindoId`/`nfExcluindoIds`; funções `abrirModalExcluirNF`, `fecharModalExcluirNF`, `confirmarExcluirNF` (mesma estrutura de OC); botão `✕` adicionado em todo card NF (pagas e não pagas); bind em `renderNFs`; bind do botão de massa em `vincularEventos`
- Testes: `tests/test_repositorio_nf_exclusao.py` (13 testes) — registro removido, itens em cascata, PDF no disco removido, arquivo já inexistente não quebra, lista vazia, isolamento entre NFs

### 2 — Dashboard: "Recebido" e pizza por mês de pagamento, não de emissão
- `app/db/repositorio.py` — `totais_nf_por_orgao` alterada para agrupar por `data_pagamento` e filtrar `status_pagamento = 'pago'` em vez de `data_emissao`; mantém consistência com o que o frontend passa a mostrar
- `app/ui/app.js` — `renderDashboard()`: adicionado `nfsRecebidasMes` (filtrado por `data_pagamento` no mês selecionado); KPI "Recebido" e gráfico de pizza passam a usar `nfsRecebidasMes`; KPI "Entradas" e tabela do dashboard continuam usando `nfsMes` (por `data_emissao`); `kpi-saldo` mistura intencionalmente as duas bases (regime de caixa)
- Testes: `test_totais_por_orgao_soma_correta` e `test_totais_por_orgao_filtra_por_mes` atualizados para inserir NFs com `status_pagamento: pago` e `data_pagamento`, refletindo a nova semântica da função

### 3 — Remoção de categoria e itens do formulário de inclusão de NF
- `app/ui/index.html`: bloco `#nf-sec-itens` e campo `#nf-categoria-tags` removidos do `#nf-form-dados` e substituídos por comentários explicando a decisão e o status dos artefatos (banco e código JS mantidos)
- `app/ui/app.js`: `resetarFormNF()` — removida referência a `nf-sec-itens` e ao seletor de categoria; `mudarModoNF()` — removidas manipulações de `nf-sec-itens`, `btn-add-item-nf`, `nf-itens-tabela`, `nf-itens-empty`; `processarProximaNF()` — removido bloco que extraia e exibia itens do XML; `avancarNFLote()` — removida referência a `nf-sec-itens`; `salvarNFAtual()` — `categoria: null` e `itens: []` fixos (schema e filtro existente preservados para NFs antigas)
- Código morto (`adicionarLinhaItemNF`, `removerItemNF`, `renderItensNFForm`) mantido sem alteração para reativação futura

**Total da suíte:** 185 testes, todos passando.

**Arquivos afetados:** `app/db/repositorio.py`, `app/bridge.py`, `app/ui/index.html`, `app/ui/app.js`, `tests/test_repositorio_nf_exclusao.py` (novo), `tests/test_novas_funcionalidades.py`

---

## [2026-06-28] Fallback de OCR na extração de NF por PDF

- Problema relatado: a tela "Incluir NF" não preenchia automaticamente número, fornecedor, data e valor para alguns PDFs reais do cliente — a causa raiz era a camada de texto desses PDFs (DANFEs) vir com encoding de fonte corrompido, fazendo `pdfplumber`/`PyMuPDF` extraírem texto vazio ou ilegível.
- `app/extracao/nf.py`: adicionado fallback de OCR (`_ocr_pdf`, via PyMuPDF para rasterizar páginas a 300 DPI + `pytesseract`, idiomas `por`→`eng`), acionado quando o texto extraído é vazio ou não contém nenhuma das frases-padrão de um DANFE legível (`_texto_parece_corrompido`). Resultado da extração passou a expor `_ocr_usado` (bool) para diagnóstico.
- Ao validar com 3 PDFs reais do cliente, o texto OCR revelou dois problemas adicionais, corrigidos no mesmo arquivo: (1) o fornecedor às vezes não é capturado na seção "IDENTIFICAÇÃO DO EMITENTE" (nome sobreposto a um logo/imagem que o OCR não lê) — adicionado fallback via a linha do canhoto "RECEBEMOS DE ..." (`_RECEBEMOS_DE`), além de descartar capturas que na verdade vieram do cabeçalho da tabela do destinatário; (2) o padrão genérico de valor (`R$...`) por vezes casava com a linha padrão de "Valor aproximado tributos R$0,00", presente em todo DANFE — corrigido com lookbehind negativo e um padrão de maior prioridade que lê o "VALOR TOTAL: R$/RS ..." do canhoto (cobrindo a variante onde o OCR engole o "$").
- `_extrair_texto` agora levanta `FileNotFoundError` explicitamente quando o arquivo não existe, preservando o contrato de sempre retornar `_erro` nesse caso (antes era um efeito colateral de uma exceção não tratada; o novo código de fallback a engolia silenciosamente).
- `tests/test_extracao_nf_ocr.py` (novo): 12 testes cobrindo detecção de texto corrompido, uso do texto OCR no pipeline, fallback de fornecedor via canhoto, e fallback de valor ignorando a linha de tributos.
- `requirements.txt`: adicionadas dependências `pytesseract` e `Pillow`.
- `CLAUDE.md`: stack (seção 1), pré-requisitos de desenvolvimento (seção 8, binário do Tesseract), build/distribuição (seção 9, aviso sobre empacotar o binário) e limitações conhecidas (seção 11) atualizados para refletir o fallback de OCR.
- Validado com os 3 PDFs reais fornecidos pelo cliente (números 5081, 5085 e 671) — todos os campos (número, fornecedor, data, valor, destinatário, órgão) extraídos corretamente via OCR — e suíte completa de testes (172 passando).

**Arquivos afetados:** `app/extracao/nf.py`, `tests/test_extracao_nf_ocr.py`, `requirements.txt`, `CLAUDE.md`

## [2026-06-28] Tela de confirmação de NF (PDF/XML) deixa de parecer inclusão manual

- Problema relatado: ao incluir uma NF por PDF/XML, a tela de confirmação dos dados extraídos era idêntica à de inclusão manual, porque as abas "PDF / XML / Manual" e o título "Forma de inclusão" continuavam visíveis junto do formulário de conferência — sem indicar visualmente que se tratava de uma confirmação, e não de uma nova entrada do zero.
- `app/ui/index.html`: título "Forma de inclusão" e as abas de modo (`#nf-modo-tabs`) foram envolvidos em um novo `<div id="nf-modo-wrap">`, permitindo escondê-los independentemente do restante do card.
- `app/ui/app.js`: `processarProximaNF()` agora oculta `#nf-modo-wrap` assim que os dados são extraídos e o formulário de confirmação é exibido — a tela passa a se parecer com a confirmação de OC (campos editáveis, sem opção de trocar de modo no meio da conferência). `resetarFormNF()` e `mudarModoNF()` voltam a exibir o wrapper ao reabrir o formulário ou ao selecionar/permanecer no modo Manual (que não tem etapa de confirmação separada — é entrada do zero). `atualizarProgressoNF()` passou a definir o título `#nf-conf-titulo` sempre como "NF X de N" (antes só em lote com mais de 1 arquivo), igualando ao padrão já usado na confirmação de OC mesmo para um único arquivo.
- Validado com `node --check` (sintaxe ok) e suite completa de testes (151 passando, sem alteração em arquivos Python).

**Arquivos afetados:** `app/ui/index.html`, `app/ui/app.js`

---

## [2026-06-28] Detecção automática de órgão no destinatário da NF

- Novo módulo `app/extracao/orgao.py` (`detectar_orgao`): identifica o órgão (Administração/Saúde/Educação/Assistência Social) por busca de palavra-chave no texto do destinatário/remetente da NF, normalizando acentos e maiúsculas. Prioriza palavras-chave específicas (SAÚDE, EDUCAÇÃO, ASSISTÊNCIA SOCIAL) sobre o fallback genérico de Administração (PREFEITURA/ADMINISTRAÇÃO/MUNICÍPIO/MUNICIPAL), para que "SECRETARIA MUNICIPAL DE SAÚDE" não seja classificada como Administração só por conter "MUNICIPAL".
- `app/extracao/nf.py`: passa a extrair também o campo `destinatario` do DANFE (ancorado nos rótulos "NOME / RAZÃO SOCIAL" e "DESTINATÁRIO/REMETENTE", distintos do rótulo de emitente já usado para `fornecedor`) e a chamar `detectar_orgao` sobre esse texto, preenchendo `orgao_id`. Extração de NF via PDF continua só de cabeçalho (sem itens) — fora de escopo desta mudança.
- `app/extracao/nf_xml.py`: mesma lógica, lendo o destinatário do elemento `<dest><xNome>` do XML da NFe.
- `app/ui/app.js` (`processarProximaNF`): ao extrair uma NF (PDF/XML, único ou em lote), pré-seleciona automaticamente a tag de órgão correspondente a `orgao_id` na tela "Incluir NF", sem exigir confirmação manual (exceção autorizada na seção 6.3/10 do CLAUDE.md). Usuário pode trocar a seleção livremente antes de salvar.
- `app/ui/index.html`: comentário da seção de órgão atualizado de TODO para descrição do comportamento implementado.
- `CLAUDE.md`: seção 6.3 atualizada — detecção automática de órgão deixa de ser "planejada" e passa a documentar o desenho implementado.
- Testes novos: `tests/test_orgao.py` (11 casos para `detectar_orgao`), `tests/test_extracao_nf_orgao.py` (4 casos de integração PDF→destinatário→órgão, usando PDF sintético gerado via PyMuPDF), `tests/fixtures/nfe_com_dest_saude.xml` (fixture XML com `<dest>` de Saúde). Testes existentes atualizados: `tests/test_nf_xml.py` (3 novos casos + chaves `destinatario`/`orgao_id` em `CHAVES_NF_XML`) e `tests/test_estrutura_extracao.py` (mesmas chaves em `CHAVES_NF`).
- Suíte completa: 151 testes, todos passando.

**Arquivos afetados:** `app/extracao/orgao.py` (novo), `app/extracao/nf.py`, `app/extracao/nf_xml.py`, `app/ui/app.js`, `app/ui/index.html`, `CLAUDE.md`, `tests/test_orgao.py` (novo), `tests/test_extracao_nf_orgao.py` (novo), `tests/fixtures/nfe_com_dest_saude.xml` (novo), `tests/test_nf_xml.py`, `tests/test_estrutura_extracao.py`

---

## [2026-06-28] Extração de nome do produto + coluna UN, e exclusão de Ordens de Compra

### 1 — Extração de nome do produto e coluna UN (Etapa 1)
- `app/extracao/ordem_compra.py`: a coluna `PRODUTO` do PDF de OC traz a descrição completa do item junto com texto técnico longo (especificações, marca, etc.). Passa a extrair apenas o nome do produto, truncando em torno de 70 caracteres quando não há separador "."/":" — recuando até o limite de palavra mais próximo para não cortar no meio de uma palavra, e removendo pontuação solta no final.
- Mesma função passa a capturar também a coluna `UN` (unidade) da tabela de itens da OC, antes descartada.
- Coluna `unidade` propagada por toda a cadeia: `app/db/schema.sql` (nova coluna em `itens_ordem_compra`, com migração em `repositorio._migrar()` para bancos já existentes), `app/db/repositorio.py` (`salvar_ordem_compra`), `app/exportacao/ordem_compra_xlsx.py` (nova coluna "UN" no xlsx exportado) e `app/ui/index.html`/`app.js` (exibida na tabela de itens da OC, na tela de confirmação de inclusão e no card da Lista de Compras).
- `tests/test_exportacao_xlsx.py` ajustado: índices de coluna deslocados em 1 por conta da nova coluna "UN" no xlsx.

### 2 — Exclusão de Ordens de Compra, individual e em lote (Etapa 2)
- `app/db/repositorio.py`: novas funções `excluir_ordem_compra` e `excluir_ordens_compra_em_massa` (a última em transação única, mesmo padrão de `marcar_pagas_em_massa`). Os itens da OC são removidos automaticamente via `ON DELETE CASCADE` já existente no schema — sem necessidade de exclusão manual dos itens.
- `app/bridge.py`: dois novos `@Slot` expondo as funções acima ao JS, cada um disparando backup automático do banco após a exclusão.
- `app/ui/index.html` / `app.js` / `styles.css`: nova barra de seleção em massa na tela Lista de Compras (checkbox "Selecionar todas" + checkbox por card de OC), botão de exclusão individual em cada card, e modal de confirmação único (`#modal-excluir-oc`) reaproveitado tanto para exclusão individual quanto em lote — a exclusão nunca é instantânea, sempre exige confirmação.
- `tests/test_repositorio_oc.py`: 6 novos testes cobrindo exclusão individual (com e sem cascata de itens), exclusão de OC inexistente (não falha), exclusão em massa (incluindo cascata de itens) e lista de ids vazia.
- Suíte completa validada após as duas etapas: 142 testes passando (eram 134 antes desta sessão).

**Arquivos afetados:** `app/extracao/ordem_compra.py`, `app/db/schema.sql`, `app/db/repositorio.py`, `app/bridge.py`, `app/exportacao/ordem_compra_xlsx.py`, `app/ui/index.html`, `app/ui/app.js`, `app/ui/styles.css`, `tests/test_exportacao_xlsx.py`, `tests/test_repositorio_oc.py`

---

## [2026-06-28] Correção da extração de Ordens de Compra (layout real da Prefeitura de Goianápolis)

A partir de 3 PDFs reais de Ordem de Compra (fornecedor PANIFICADORA E SUPERMERCADO TRIGO BOM - EIRELI, layout da Prefeitura de Goianápolis), identificados e corrigidos três bugs em `app/extracao/ordem_compra.py`:

- **Descrição do item vinha vazia/errada**: a busca da coluna de descrição considerava "item"/"descri"/"produto" na mesma prioridade; como a coluna `ITEM` (só o número sequencial) aparece antes da coluna `PRODUTO` na tabela, `descricao` sempre pegava o número do item ("0001", "0002"...) em vez do texto do produto. Corrigido para priorizar a coluna `PRODUTO`/`DESCRIÇÃO` e só cair para `ITEM` se nenhuma das duas existir.
- **Número da OC vinha vazio**: a regex de `numero` exigia "Nº"/"N°" mas não aceitava o "N." com ponto usado no layout real ("ORDEM DE COMPRA - N. 62340"), então nunca casava. Regex ajustada para aceitar ponto após o N.
- **Fornecedor vinha com o código em vez do nome**: a regex de `fornecedor` casava com o primeiro rótulo encontrado no texto ("fornecedor"/"empresa"/"razão social"); no layout real, "CÓD. FORNECEDOR: 14487" aparece antes de "EMPRESA: PANIFICADORA...", então sempre capturava o código numérico. Regex passa a priorizar o campo "EMPRESA:" (com lookahead até o próximo rótulo em caixa alta), com os demais padrões como fallback.
- **Bug adicional corrigido na mesma função**: descrições de produto longas que atravessam quebra de página geravam uma linha de tabela "fantasma" (só com a continuação do texto, sem número de item nem valores) na página seguinte; essa linha agora é detectada (sem número de item e sem valores) e concatenada à descrição do item anterior, em vez de virar um item extra incorreto.

Validado executando o extrator contra os 3 PDFs reais: número, fornecedor e descrição completa de cada item agora corretos, com totais batendo (R$701,20 / R$1.579,26 / R$2.760,00).

**Arquivos afetados:** `app/extracao/ordem_compra.py`

---

## [2026-06-26] Remoção de Saldo de Licitação, dashboard com pizza por órgão, Lista de Compras, Notas Fiscais com filtros e marcação em massa, backup por timer

### 1 — Remoção de Saldo de Licitação
- Apagado `app/extracao/licitacao.py` e `tests/test_repositorio_licitacao.py`
- `app/db/schema.sql`: removidas as definições de `licitacoes`, `itens_licitacao` e `movimentos_licitacao`
- `app/db/repositorio._migrar()`: adicionado `DROP TABLE IF EXISTS` para as três tabelas, garantindo remoção limpa em bancos existentes
- `app/bridge.py`: removidos todos os slots de licitação e o import de `extrair_licitacao`
- `app/config.py`: removida a chave `pasta_licitacoes` de `CHAVES`
- UI: removidos os links de sidebar, views e modal relacionados a licitações; campo "Pasta de Licitações" removido da tela de Configurações

### 2 — Dashboard
- KPI "NFs não pagas" removido; grid passa de 4 para 3 cards
- Novo gráfico de pizza (`conic-gradient`) exibindo distribuição do valor de NFs do mês por órgão (Administração/Saúde/Educação/Assistência Social), calculado client-side a partir do cache `estado.nfs`
- Novo `repositorio.totais_nf_por_orgao(mes, ano)` para uso em testes e futuras extensões

### 3 — Agenda de Compras → Lista de Compras
- Renomeada no sidebar e no cabeçalho da tela
- Kanban (3 colunas por status) substituído por lista única
- Itens de cada OC exibidos diretamente no card, sem necessidade de abrir tela de detalhe separada
- `repositorio.listar_ordens_compra_com_itens()`: nova função que retorna OCs com itens aninhados em payload único
- Upload em lote: `abrir_dialogo_multiplos_arquivos` (novo slot no bridge usando `QFileDialog.getOpenFileNames`) permite selecionar múltiplos PDFs; fila processada um a um com confirmação antes de salvar
- Status de entrega alterável via `<select>` inline no card
- Exportação para planilha disponível diretamente no card (sem tela de detalhe)

### 4 — Pagamentos → Notas Fiscais
- Tela e menu renomeados
- **Filtros client-side**: órgão, categoria, status de pagamento, mês — combinados em qualquer ordem, sem chamada adicional ao backend
- **Marcação em massa**: checkbox em cada card de NF não paga + "Selecionar todas" + modal de confirmação com data de pagamento → `repositorio.marcar_pagas_em_massa(ids, data)` em transação única
- **Inclusão em lote** (PDF e XML): `abrir_dialogo_multiplos_arquivos` abre seleção múltipla; cada arquivo passa pela mesma extração + tela de confirmação manual (fila); indicador de progresso (pontos coloridos)
- TODO registrado no HTML (seção 6.3 CLAUDE.md): detecção automática de órgão pode pré-selecionar sem confirmação quando for implementada

### 5 — Backup por timer
- `app/main.py`: `QTimer` de 10 minutos dispara `backup.fazer_backup()` automaticamente enquanto o app está aberto; timer é parado antes de `aboutToQuit` para evitar backup duplicado

**Total da suíte:** 136 testes, todos passando.

**Arquivos afetados:** `app/config.py`, `app/db/schema.sql`, `app/db/repositorio.py`, `app/bridge.py`, `app/main.py`, `app/ui/index.html`, `app/ui/app.js`, `app/ui/styles.css`, `tests/test_contratos_bridge.py`, `tests/test_estrutura_extracao.py`, `tests/test_config.py`, `tests/test_novas_funcionalidades.py` (novo) — `app/extracao/licitacao.py` e `tests/test_repositorio_licitacao.py` removidos

---

## [2026-06-26] Decisões de arquitetura: Dashboard, Lista de Compras, Notas Fiscais e remoção do Saldo de Licitação

Cinco decisões de produto/arquitetura registradas (ainda sem implementação de código).

- **Dashboard**: removido o KPI "NFs não pagas" (passa a ser coberto pelos filtros da tela Notas Fiscais); adicionado gráfico de pizza com distribuição do valor de NFs do mês por órgão
- **Agenda de Compras → Lista de Compras**: removido o formato kanban/to-do por status de entrega; OCs passam a aparecer em lista única com os itens já visíveis no card; adicionada inclusão em lote de múltiplos PDFs de OC
- **Pagamentos → Notas Fiscais**: adicionada inclusão em lote (PDF e/ou XML), filtros (órgão, categoria, status, período) e marcação em massa como paga; registrada decisão pendente sobre detecção automática de órgão — quando implementada, está autorizada a pré-selecionar sem confirmação manual, como exceção à convenção geral de conferência (seção 10), mas o desenho da lógica fica para conversa futura
- **Saldo de Licitação**: tela removida completamente do escopo do sistema. Em cascata, saíram do modelo de dados as tabelas `licitacoes`, `itens_licitacao` e `movimentos_licitacao`, o módulo `app/extracao/licitacao.py`, a "Pasta de Licitações" da tela de Configurações e todas as referências a licitação em arquitetura/convenções/limitações
- **Backup**: adicionado timer de 10 minutos que dispara backup automático do banco enquanto o app estiver aberto, além dos gatilhos já existentes (salvamento relevante e fechamento do app)

**Arquivos afetados:** `CLAUDE.md` (seções 1, 3, 4, 5, 6, 7, 10, 11, 12) — ainda sem implementação de código, apenas decisão de arquitetura registrada

---

## [2026-06-25] Implementação das Frentes 1 e 2 — armazenamento configurável, backup/lock e NF via XML/manual com itens

### Frente 1 — Armazenamento em pastas configuráveis

- Criado `app/config.py`: lê/escreve `%APPDATA%\TrigoBom\config.json` com os 4 caminhos configuráveis (`pasta_nfs`, `pasta_ordens_compra`, `pasta_licitacoes`, `pasta_backup`); expõe `carregar_config()`, `salvar_config()` e `pasta_valida()`
- Criado `app/backup.py`: `fazer_backup()` copia o banco local para `pasta_backup` com metadado de timestamp; `verificar_backup_mais_novo()` compara timestamps; `restaurar_backup()` sobrescreve banco local; `gravar_lock()` / `verificar_lock()` / `remover_lock()` implementam o protocolo de lock com expiração por idade (padrão 8h)
- Atualizado `app/main.py`: ao iniciar, verifica lock de outro dispositivo (aviso não bloqueante) e compara backup — se mais novo, oferece restauração via `QMessageBox`; grava lock do dispositivo atual; conecta `aboutToQuit` para fazer backup final e remover lock
- Atualizado `app/bridge.py`: slots `carregar_config`, `salvar_config`, `abrir_dialogo_pasta`; cópia automática de PDFs para pasta configurada em `salvar_nf`, `salvar_ordem_compra`, `salvar_licitacao`; chamada de `fazer_backup()` após toda escrita relevante
- Adicionada tela de Configurações na UI com 4 campos de pasta + botão de seleção de diretório por campo
- Novos testes: `tests/test_config.py` (8 testes) e `tests/test_backup_lock.py` (15 testes)

### Frente 2 — Inclusão de NF via PDF, XML e manual com itens

- Atualizado `app/db/schema.sql`: coluna `origem TEXT` em `notas_fiscais`; nova tabela `itens_nota_fiscal` (id, nota_fiscal_id FK cascade, descricao, quantidade, valor_unitario, valor_total, ncm, cfop)
- Atualizado `app/db/repositorio.py`: nova função `_migrar()` aplica `ALTER TABLE` e `CREATE TABLE IF NOT EXISTS` sem quebrar bancos existentes; `salvar_nf` grava `origem` e insere itens em transação única; nova função `listar_itens_nf(nota_fiscal_id)`
- Criado `app/extracao/nf_xml.py`: parser de NFe (modelo 55) usando `xml.etree.ElementTree`; aceita `<NFe>` como raiz ou `<nfeProc><NFe>`; extrai cabeçalho (numero, fornecedor, data_emissao, valor) e lista de itens (descricao, quantidade, valor_unitario, valor_total, ncm, cfop); retorna JSON com `_erro` em caso de falha
- Atualizado `app/bridge.py`: slot `ler_xml_nf`, slot `abrir_dialogo_arquivo_xml` (filtro `.xml`)
- Atualizada tela "Incluir NF" na UI com 3 abas: **PDF** (fluxo existente, sem itens), **XML** (upload .xml → extração + tabela de itens read-only para confirmação), **Manual** (formulário em branco + tabela editável com adicionar/remover linha)
- Adicionada tela "Detalhe NF" (acessível clicando em qualquer NF nos cards de Pagamentos ou na tabela do Dashboard): mostra informações completas + tabela de itens (com NCM e CFOP) se houver
- Criado `tests/fixtures/nfe_exemplo.xml`: XML de NFe mínimo válido com 2 itens para testes
- Novos testes: `tests/test_nf_xml.py` (17 testes) e `tests/test_repositorio_nf_itens.py` (15 testes)

**Total da suíte:** 126 testes, todos passando.

**Arquivos afetados:** `app/config.py` (novo), `app/backup.py` (novo), `app/extracao/nf_xml.py` (novo), `app/main.py`, `app/bridge.py`, `app/db/schema.sql`, `app/db/repositorio.py`, `app/ui/index.html`, `app/ui/app.js`, `app/ui/styles.css`, `tests/conftest.py`, `tests/test_config.py` (novo), `tests/test_backup_lock.py` (novo), `tests/test_nf_xml.py` (novo), `tests/test_repositorio_nf_itens.py` (novo), `tests/fixtures/nfe_exemplo.xml` (novo)

---

## [2026-06-25] Decisão de arquitetura: inclusão de NF via XML e entrada manual, com itens

Definidas duas novas formas de incluir nota fiscal, além do upload de PDF já existente.

- Nova forma **Importar XML da NFe**: parsing do leiaute nacional padronizado (SEFAZ), extraindo cabeçalho e itens (descrição, quantidade, valor, NCM, CFOP) — sem depender de heurística de layout de PDF. Cobre apenas NFe modelo 55; NFS-e municipal não é suportada
- Nova forma **Entrada manual**: usuário digita cabeçalho e pode adicionar itens um a um, sem depender de arquivo
- Upload de PDF continua como antes (só cabeçalho, sem itens)
- Nova tabela `itens_nota_fiscal` (mesma estrutura de `itens_ordem_compra`, mais `ncm`/`cfop` opcionais) — só populada via XML ou entrada manual
- Nova coluna `origem` em `notas_fiscais` (`pdf`/`xml`/`manual`)
- Novo módulo planejado `app/extracao/nf_xml.py`

**Arquivos afetados:** `CLAUDE.md` (seções 1, 4, 5, 6.4, 7.1, 11) — ainda sem implementação de código, apenas decisão de arquitetura registrada

---

## [2026-06-25] Decisão de arquitetura: armazenamento em pastas configuráveis pelo usuário

Definida a arquitetura de armazenamento para suportar o cliente que se desloca entre dispositivos, sem custo de servidor.

- Tela de Configurações terá 4 campos de pasta escolhidos pelo usuário: Pasta de NFs, Pasta de Ordens de Compra, Pasta de Licitações e Pasta de Dados/Backup (podem ser HD/SSD externo ou pasta sincronizada de nuvem como Google Drive/OneDrive)
- PDFs são copiados para a pasta correspondente ao tipo no momento do upload (arquivos estáticos, seguros em pastas sincronizadas)
- Banco SQLite continua local em `%APPDATA%\TrigoBom\trigo_bom.db` (escrita ativa não é segura em pasta sincronizada/HD externo); a cada salvamento relevante é gerado um snapshot/backup na Pasta de Dados/Backup
- Ao abrir o app, compara backup remoto vs banco local e oferece restaurar o mais novo — é assim que o cliente "leva os dados" entre dispositivos
- Suporte a múltiplos dispositivos é "alternado com aviso de lock": arquivo de lock (dispositivo + timestamp) gravado na Pasta de Dados/Backup ao abrir, com aviso se outro dispositivo já estiver ativo; não há escrita simultânea real nem merge de conflitos
- Caminhos das pastas configuradas são persistidos em `%APPDATA%\TrigoBom\config.json`

**Arquivos afetados:** `CLAUDE.md` (seções 4, 11, 12 novas/atualizadas; sumário renumerado) — ainda sem implementação de código, apenas decisão de arquitetura registrada

---

## [2026-06-25] Estado inicial registrado

Primeira entrada do changelog. Snapshot do que já existia no projeto antes de o versionamento começar a ser registrado por sessão.

- Estrutura do app criada em `trigo_bom/app` (PySide6 + QWebEngineView + QWebChannel)
- Módulos de extração de PDF (`app/extracao/nf.py`, `ordem_compra.py`, `licitacao.py`)
- Camada de banco SQLite (`app/db/schema.sql`, `repositorio.py`)
- Exportação de itens de OC para `.xlsx` (`app/exportacao/ordem_compra_xlsx.py`)
- UI baseada no protótipo HTML/CSS/JS (`app/ui/`)
- Suíte de testes em `tests/` (extração, repositório de NF/OC/licitação, exportação)
- Documentação de arquitetura e modelo de dados em `CLAUDE.md`, contexto de produto em `IDEA.md`

**Arquivos afetados:** todo o projeto (snapshot inicial, não há histórico granular anterior a esta data)
