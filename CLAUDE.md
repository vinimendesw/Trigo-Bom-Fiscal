# CLAUDE.md — TrigoBom Fiscal

> **Status:** Em definição (pré-implementação)

Contexto de produto, problema e escopo: ver [IDEA.md](IDEA.md).

---

## Sumário

1. [Stack Tecnológica](#1-stack-tecnológica)
2. [Por que essa combinação](#2-por-que-essa-combinação)
3. [Arquitetura](#3-arquitetura)
4. [Estrutura de Diretórios](#4-estrutura-de-diretórios)
5. [Modelo de Dados](#5-modelo-de-dados)
6. [Funcionalidades](#6-funcionalidades)
7. [Guia de Uso](#7-guia-de-uso)
8. [Como Rodar em Desenvolvimento](#8-como-rodar-em-desenvolvimento)
9. [Build e Distribuição](#9-build-e-distribuição)
10. [Convenções](#10-convenções)
11. [Limitações Conhecidas](#11-limitações-conhecidas)
12. [Armazenamento e Configuração de Pastas](#12-armazenamento-e-configuração-de-pastas)
13. [Versionamento (CHANGELOG)](#13-versionamento-changelog)
14. [Distribuição e Atualizações](#14-distribuição-e-atualizações)

---

## 1. Stack Tecnológica

### Linguagem e runtime

| Tecnologia | Função |
|---|---|
| **Python 3.11+** | Linguagem única do projeto — extração de PDF, regras de negócio, persistência e ponte com a interface |

### Interface

| Tecnologia | Função |
|---|---|
| **PySide6** | Shell desktop nativo (janela, menus, ciclo de vida da aplicação) |
| **QWebEngineView** | Motor de navegador (Chromium via Qt) embutido na janela, renderiza o protótipo HTML/CSS/JS já validado com o cliente |
| **QWebChannel** | Ponte de comunicação entre o JavaScript da tela e as funções Python (sem servidor HTTP local) |
| HTML/CSS/JS (`prototipos/trigo-bom-prototipo.html`) | Camada visual — reaproveitada do protótipo aprovado, adaptada para consumir dados reais via `QWebChannel` |

### Extração de documentos

| Tecnologia | Função |
|---|---|
| **pdfplumber** | Extração de texto e tabelas de PDFs com layout previsível (NFs, OCs) |
| **PyMuPDF (fitz)** | Suporte/fallback para extração de texto quando `pdfplumber` não resolver bem o layout; também usado para rasterizar páginas (`get_pixmap`) no fallback de OCR |
| **pytesseract** | Fallback de OCR para NF em PDF quando a camada de texto do PDF estiver corrompida (encoding de fonte quebrado — comum em DANFEs gerados por alguns emissores). Requer o binário do Tesseract instalado no sistema (não é instalável via `pip`) |
| **Pillow (PIL)** | Conversão da página rasterizada (PyMuPDF) para imagem em memória antes de passar ao `pytesseract` |
| **xml.etree.ElementTree** (biblioteca padrão) | Parsing do XML padronizado da NFe (leiaute nacional SEFAZ) para importação de NF com itens, sem depender de heurística de layout de PDF |

### Persistência e exportação

| Tecnologia | Função |
|---|---|
| **SQLite** (via `sqlite3`, biblioteca padrão) | Banco local, sem servidor — adequado a app desktop monousuário de baixo volume |
| **openpyxl** | Exportação da lista de itens de ordens de compra para planilha `.xlsx` (única exportação prevista no momento) |

### Empacotamento

| Tecnologia | Função |
|---|---|
| **PyInstaller** | Gera executável único (`.exe`) para distribuição ao cliente, sem exigir Python instalado na máquina |

---

## 2. Por que essa combinação

A interação (frontend) e a extração/organização dos dados (backend) ficam separadas em **camadas de linguagem** — HTML/CSS/JS para a tela, Python para PDF e regras de negócio — mas dentro de **um único processo e runtime**. Isso evita o custo de empacotar dois runtimes (ex.: Python + Node/Electron) para um projeto de baixo volume (~30 documentos/mês) e escopo desktop-only, e ainda permite reaproveitar quase integralmente o protótipo HTML já aprovado com o cliente.

Python foi escolhido como linguagem de extração por ter o ecossistema mais maduro para ler tabelas dentro de PDF — requisito central do sistema, já que NFs e ordens de compra precisam ser lidas **item a item**, não só como documento único.

Se no futuro o projeto precisar virar um app acessível remotamente (não só desktop), a camada Python pode ser exposta como API (ex.: FastAPI) sem reescrever a lógica de extração — apenas a forma como a UI se comunica com ela mudaria.

---

## 3. Arquitetura

Processo único, com três camadas internas:

```
┌──────────────────────────────────────────────────────────┐
│                     APP DESKTOP (PySide6)                 │
│                        app/main.py                         │
│                                                            │
│   ┌────────────────────────────────────────────────────┐  │
│   │            QWebEngineView (janela principal)        │  │
│   │      carrega app/ui/index.html (protótipo HTML)     │  │
│   └───────────────────────┬──────────────────────────────┘  │
│                           │ QWebChannel                    │
│                           ▼                                │
│   ┌────────────────────────────────────────────────────┐  │
│   │                  app/bridge.py                       │  │
│   │   funções expostas ao JS: ler_pdf(), salvar_nf(),    │  │
│   │   listar_itens_oc(), exportar_oc_xlsx(), ...         │  │
│   └───────┬───────────────────┬───────────────┬─────────┘  │
│           ▼                   ▼               ▼            │
│   ┌──────────────┐   ┌────────────────┐  ┌───────────────┐ │
│   │ app/extracao │   │   app/db        │  │ app/exportacao│ │
│   │ (pdfplumber/ │   │ (SQLite local)  │  │ (openpyxl)    │ │
│   │  PyMuPDF)    │   │                 │  │               │ │
│   └──────────────┘   └────────────────┘  └───────────────┘ │
└──────────────────────────────────────────────────────────┘
```

**Princípios:**
- A interface (HTML/JS) nunca acessa arquivos ou banco diretamente — toda operação passa por `app/bridge.py`.
- Os PDFs originais (NF, OC) nunca são alterados ou movidos — apenas lidos pelos módulos de `app/extracao`.
- Toda extração automática é exibida para o usuário **antes** de ser persistida no banco, permitindo correção manual.

---

## 4. Estrutura de Diretórios

```
trigo_bom/
├── app/
│   ├── main.py                   # ponto de entrada, abre a janela PySide6 + QWebEngineView
│   ├── bridge.py                  # QWebChannel — funções expostas ao JS
│   ├── extracao/
│   │   ├── nf.py                   # extração de NF a partir de PDF (cabeçalho apenas: número, fornecedor, data, valor)
│   │   ├── nf_xml.py               # extração de NF a partir do XML padronizado da NFe (cabeçalho + itens)
│   │   └── ordem_compra.py         # extração de OCs item a item
│   ├── db/
│   │   ├── schema.sql              # definição das tabelas (ver seção 5)
│   │   └── repositorio.py          # acesso ao SQLite (CRUD)
│   ├── exportacao/
│   │   └── ordem_compra_xlsx.py    # exportação dos itens de OC para planilha
│   └── ui/
│       ├── index.html              # protótipo adaptado (telas reais)
│       ├── styles.css
│       └── app.js                  # chamadas via QWebChannel
├── prototipos/                    # protótipos visuais originais (referência de design)
├── IDEA.md
└── CLAUDE.md
```

**Diretórios criados em runtime** (dados do usuário, fora do código-fonte):

```
%APPDATA%\TrigoBom\
├── trigo_bom.db        # banco SQLite — cópia de trabalho local (sempre lida/escrita pelo app)
└── config.json         # caminhos das pastas configuráveis pelo usuário (ver seção 12)
```

As pastas de PDFs (NFs, OCs) e a pasta de backup do banco **não** ficam fixas em `%APPDATA%` — são escolhidas pelo usuário na tela de Configurações e podem apontar para qualquer local (HD/SSD externo, pasta sincronizada do Google Drive/OneDrive, etc.). Detalhes em [seção 12](#12-armazenamento-e-configuração-de-pastas).

---

## 5. Modelo de Dados

### Tabela `orgaos`

| Coluna | Tipo | Descrição |
|---|---|---|
| `id` | INTEGER PK | Identificador |
| `nome` | TEXT | Administração / Saúde / Educação / Assistência Social |

### Tabela `notas_fiscais`

| Coluna | Tipo | Descrição |
|---|---|---|
| `id` | INTEGER PK | Identificador |
| `numero` | TEXT | Número da NF |
| `orgao_id` | INTEGER FK | Órgão ao qual a nota se refere (`orgaos.id`), escolhido no upload |
| `data_emissao` | TEXT | Data de emissão |
| `valor` | REAL | Valor da nota |
| `categoria` | TEXT | Alimentícios / Limpeza / Embalagens / Manutenção / Equipamentos / Outros |
| `status_pagamento` | TEXT | `pago` ou `nao_pago` — marcação manual |
| `data_vencimento` | TEXT | Data de vencimento |
| `data_pagamento` | TEXT | Preenchida quando marcada como paga |
| `arquivo_pdf` | TEXT | Caminho do PDF original (vazio quando a nota for incluída só por XML, sem PDF anexado) |
| `criado_em` | TEXT | Data/hora do upload |
| `origem` | TEXT | `pdf` / `xml` / `manual` — como a nota foi incluída (ver seção 6.4) |

### Tabela `itens_nota_fiscal`

Só é populada quando a NF é incluída via XML ou via entrada manual com itens (seção 6.4). NF incluída só por PDF não tem itens.

| Coluna | Tipo | Descrição |
|---|---|---|
| `id` | INTEGER PK | Identificador |
| `nota_fiscal_id` | INTEGER FK | `notas_fiscais.id` |
| `descricao` | TEXT | Descrição do item/produto |
| `quantidade` | REAL | Quantidade |
| `valor_unitario` | REAL | Valor unitário |
| `valor_total` | REAL | Valor total do item |
| `ncm` | TEXT | Código NCM do item — preenchido quando vier do XML, vazio em itens digitados manualmente |
| `cfop` | TEXT | Código CFOP do item — preenchido quando vier do XML, vazio em itens digitados manualmente |

> NCM/CFOP não são usados hoje em nenhuma regra de negócio — guardados para viabilizar sugestão automática de categoria no futuro, sem precisar migrar o banco depois.

### Tabela `ordens_compra`

| Coluna | Tipo | Descrição |
|---|---|---|
| `id` | INTEGER PK | Identificador |
| `numero` | TEXT | Número da OC |
| `fornecedor` | TEXT | Fornecedor/cliente da OC |
| `data_emissao` | TEXT | Data de emissão |
| `data_entrega_prevista` | TEXT | Usada na agenda/to-do |
| `status_entrega` | TEXT | `pendente` / `atrasada` / `entregue` |
| `arquivo_pdf` | TEXT | Caminho do PDF original |

### Tabela `itens_ordem_compra`

| Coluna | Tipo | Descrição |
|---|---|---|
| `id` | INTEGER PK | Identificador |
| `ordem_compra_id` | INTEGER FK | `ordens_compra.id` |
| `descricao` | TEXT | Descrição do item extraída do PDF |
| `quantidade` | REAL | Quantidade |
| `valor_unitario` | REAL | Valor unitário |
| `valor_total` | REAL | Valor total do item |

> **Removido em 2026-06-26:** as tabelas `licitacoes`, `itens_licitacao` e `movimentos_licitacao` saíram do modelo de dados junto com a remoção da tela "Saldo de Licitação" (ver seção 6). Se o app já tiver sido implementado com essas tabelas, a remoção é responsabilidade da migração de banco, não apenas da documentação.

---

## 6. Funcionalidades

### 6.1 Dashboard

- Mostra entradas e saídas a partir das NFs emitidas para o município, **segmentadas por órgão** (Administração, Saúde, Educação, Assistência Social).
- Navegação entre meses (setas + seletor rápido dos últimos meses).
- Cards de KPI (entradas, saídas, saldo), distribuição da movimentação, status das notas e tendência dos últimos 6 meses. KPI de "NFs não pagas" foi removido — passa a ser coberto pelos filtros/contagem da tela Notas Fiscais (seção 6.3).
- **Gráfico de pizza por órgão**: logo após os KPIs, mostra a distribuição do valor das NFs do mês entre Administração, Saúde, Educação e Assistência Social.

### 6.2 Lista de Compras

> Renomeada de "Agenda de Compras". O formato kanban/to-do por status de entrega foi removido.

- Lê ordens de compra em PDF e extrai os **itens item a item** (descrição, quantidade, valor).
- Apresenta as OCs em **lista única**, sem agrupamento por status de entrega; os itens de cada OC aparecem diretamente no card, sem precisar abrir uma tela de detalhe.
- Permite **inclusão em lote**: upload de múltiplos PDFs de OC de uma vez, cada um extraído e exibido para confirmação antes de salvar.
- Permite **exportar a lista de itens de uma OC para planilha** (`.xlsx`).

### 6.3 Notas Fiscais

> Renomeada de "Pagamentos".

- Board manual com duas colunas: **não pagas** e **pagas**.
- Botão **"Incluir NF"** abre a tela de inclusão (seção 6.4), agora também com **inclusão em lote**: upload de múltiplos arquivos (PDF e/ou XML) de uma vez, cada um extraído e exibido para confirmação antes de salvar.
- **Filtros** sobre a lista/board (por órgão, categoria, status de pagamento, período).
- **Marcação em massa como paga**: seleção de várias NFs (ex.: via checkbox nos cards) e ação única para marcar todas como pagas, preenchendo a data de pagamento.
- **Detecção automática de órgão** a partir do destinatário/remetente da NF — implementada via busca de palavra-chave no texto extraído (`destinatario`, vindo do PDF ou do `<dest><xNome>` do XML): "SAÚDE" → Saúde, "EDUCAÇÃO"/"EDUCACIONAL" → Educação, "ASSISTÊNCIA SOCIAL" → Assistência Social, "PREFEITURA"/"ADMINISTRAÇÃO"/"MUNICÍPIO"/"MUNICIPAL" → Administração (fallback genérico, só usado quando nenhuma palavra-chave mais específica é encontrada — ex.: "SECRETARIA MUNICIPAL DE SAÚDE" resolve para Saúde, não Administração). Implementado em `app/extracao/orgao.py` (`detectar_orgao`), chamado por `app/extracao/nf.py` e `app/extracao/nf_xml.py`. A tela "Incluir NF" pré-seleciona a tag do órgão detectado **sem exigir confirmação manual**, como exceção pontual à regra geral da seção 10 (toda extração automática passa por conferência antes de salvar) — usuário pode trocar a seleção livremente antes de salvar.

### 6.4 Incluir NF

Três formas de inclusão, escolhidas pelo usuário na tela de inclusão:

- **Upload de PDF** — extração automática de número, fornecedor, data e valor a partir do texto do PDF (`pdfplumber`/PyMuPDF), exibida para confirmação/edição manual antes de salvar. Nota fica **sem itens** (só cabeçalho), como já funcionava antes.
- **Importar XML da NFe** — leitura do XML padronizado (leiaute nacional SEFAZ), extraindo cabeçalho (número, fornecedor, data, valor total) **e os itens da nota** (descrição, quantidade, valor, NCM, CFOP), exibidos para confirmação antes de salvar. Cobre apenas NFe modelo 55 (leiaute nacional) — não cobre NFS-e municipal (ver seção 11).
- **Entrada manual** — usuário digita os campos de cabeçalho e pode adicionar itens um a um na tela (mesma lógica usada hoje em Ordens de Compra), sem depender de nenhum arquivo. PDF/XML de origem é opcional nesse caminho.

Em qualquer um dos três caminhos, depois da extração/digitação:
- Seleção do **órgão** ao qual a nota se refere.
- Seleção de **categoria** (Alimentícios, Limpeza, Embalagens, Manutenção, Equipamentos, Outros).
- Marcação manual de status (paga/não paga) e datas de vencimento/pagamento.

A inclusão em lote (seção 6.3) reaproveita esse mesmo fluxo por arquivo: cada item do lote passa pela mesma extração + confirmação antes de salvar, um a um ou em sequência — não é descarte da etapa de conferência manual.

---

## 7. Guia de Uso

### 7.1 Incluir uma nota fiscal

1. Acesse **Notas Fiscais → Incluir NF**.
2. Escolha a forma de inclusão: **PDF**, **XML** ou **manual** — para um único arquivo, ou em **lote** para vários PDFs/XMLs de uma vez.
   - PDF: faça upload do arquivo e confira os dados extraídos do cabeçalho (número, fornecedor, data, valor); a nota fica sem itens.
   - XML: faça upload do XML da NFe; confira cabeçalho e a lista de itens extraída (descrição, quantidade, valor, NCM, CFOP).
   - Manual: digite os campos de cabeçalho e, se quiser, adicione os itens um a um.
   - Lote: selecione múltiplos arquivos; cada um passa pela mesma extração e tela de confirmação antes de salvar.
3. Corrija qualquer campo extraído, se necessário.
4. Selecione o **órgão** e a **categoria**.
5. Marque o status de pagamento (paga/não paga) e, se aplicável, a data de pagamento.
6. Salve — a nota aparece no Dashboard e no board de Notas Fiscais.

Para marcar várias notas como pagas de uma vez, use os filtros para localizá-las e a ação de **marcação em massa** (seção 6.3).

### 7.2 Acompanhar ordens de compra

1. Acesse **Lista de Compras**.
2. As OCs lidas aparecem em lista única, com os itens já visíveis no card.
3. Para incluir várias OCs de uma vez, use a opção de **upload em lote**.
4. Use **Exportar para planilha** para gerar o `.xlsx` com os itens de uma OC.

---

## 8. Como Rodar em Desenvolvimento

### Pré-requisitos

- Python 3.11+
- pip
- **Tesseract OCR** instalado no sistema (binário externo, não vem pelo `pip`) — usado pelo `pytesseract` no fallback de OCR da extração de NF (seção 11). No Windows, instalar o pacote do Tesseract (ex.: build do UB-Mannheim) e garantir que o executável esteja no `PATH`, ou apontar `pytesseract.pytesseract.tesseract_cmd` para o caminho do binário.

### Instalação

```bash
git clone <repositório>
cd trigo_bom
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### Iniciar a aplicação

```bash
python app/main.py
```

Isso abre a janela PySide6 com o `QWebEngineView` carregando `app/ui/index.html`. Em desenvolvimento, o banco SQLite é criado localmente no diretório de dados do usuário (equivalente ao `userData` do Electron).

---

## 9. Build e Distribuição

O fluxo completo é executado pelo script **`build.ps1`**, na raiz de `trigo_bom/`:

```powershell
# Build completo (PyInstaller + instalador Inno Setup):
.\build.ps1

# Só PyInstaller, sem gerar o .exe do instalador:
.\build.ps1 -SemInstalador
```

O script:
1. Lê a versão de `app/__version__.py` (fonte única de verdade — seção 14.1).
2. Roda o PyInstaller com as flags abaixo e renomeia a saída para `dist/TrigoBom-<versão>/`.
3. Chama `iscc.exe` passando a versão e o caminho do dist, gerando `dist/TrigoBomSetup-<versão>.exe`.

**Flags do PyInstaller** (gerenciadas pelo `build.ps1`):
```
--noconfirm --windowed --onedir
--icon     app\ui\assets\icone.ico
--name     TrigoBom
--paths    app
--add-data "app\ui:ui"
--add-data "app\db\schema.sql:db"
--hidden-import pytesseract
--hidden-import PIL.Image
--collect-all fitz
app\main.py
```

**Pré-requisitos do build:**
- `.venv` com `pip install -r requirements.txt` (o `build.ps1` instala o PyInstaller no venv automaticamente se faltar)
- Inno Setup 6 instalado (padrão em `C:\Program Files (x86)\Inno Setup 6\iscc.exe`) para gerar o instalador
- `installer/vendor/tesseract-setup.exe` presente para incluir o Tesseract no instalador (ver seção 14.3)

**Saída:**
- `dist/TrigoBom-<versão>/` — pasta com o executável e recursos (`--onedir`, não `--onefile` — ver justificativa na seção 14.2)
- `dist/TrigoBomSetup-<versão>.exe` — instalador final para entregar ao cliente

> O fluxo completo de empacotamento (instalador, dependência do Tesseract, versionamento e como as atualizações chegam ao cliente) está definido na [seção 14](#14-distribuição-e-atualizações).

---

## 10. Convenções

- Os arquivos originais (PDFs de NF, OC) **nunca são alterados ou movidos** pelo sistema — apenas lidos. Os dados extraídos são gravados no SQLite.
- Toda extração automática deve permitir **conferência/correção manual** antes de salvar (a leitura é automática, mas o usuário confirma antes de persistir). **Exceção planejada:** a futura detecção automática do órgão de uma NF (seção 6.3) está autorizada a pré-selecionar sem exigir confirmação manual — desenho da lógica ainda pendente.
- Fluxos manuais (status de pagamento) **não têm qualquer tentativa de automação além da exceção acima** — são sempre ação explícita do usuário.

---

## 11. Limitações Conhecidas

| Limitação | Detalhes |
|---|---|
| **Extração depende do layout do PDF** | `pdfplumber`/`PyMuPDF` extraem bem PDFs com texto selecionável e layout consistente |
| **Fallback de OCR para camada de texto corrompida** | Alguns DANFEs (notadamente de certos emissores) têm a camada de texto do PDF com encoding de fonte quebrado — `pdfplumber`/`PyMuPDF` retornam texto vazio ou ilegível. Nesses casos, `app/extracao/nf.py` detecta a corrupção (ausência das frases-padrão de um DANFE legível) e cai para OCR: rasteriza as páginas via PyMuPDF (`get_pixmap`, 300 DPI) e roda `pytesseract` (idioma `por`, com fallback para `eng`). Texto OCR tem maior taxa de erro em campos sobrepostos a logos/imagens (ex.: nome do emitente na seção "IDENTIFICAÇÃO DO EMITENTE" às vezes fica vazio) — por isso o fornecedor e o valor têm fallback adicional via o canhoto de recebimento ("RECEBEMOS DE ...", "VALOR TOTAL: R$ ..."), mais robusto a OCR do que as seções formais do DANFE. Depende do binário do Tesseract instalado no sistema (seção 8) — sem ele, a extração apenas retorna os campos vazios para conferência manual, sem quebrar |
| **PDFs escaneados como imagem pura** | Quando o PDF é uma imagem sem nenhuma camada de texto (nem corrompida), o fluxo de OCR ainda se aplica (mesmo critério de "texto vazio" aciona o fallback), mas a qualidade depende da resolução/nitidez da digitalização |
| **Importação de XML cobre só NFe modelo 55** | O leiaute nacional padronizado é o da NFe (produtos). NFS-e (notas de serviço municipais) tem leiaute próprio por município e não é lida pelo parser de XML — essas notas continuam só por PDF ou entrada manual |
| **Sem autenticação** | Não há controle de acesso ou perfis de usuário — qualquer pessoa com acesso ao computador tem acesso total |
| **Sem escrita simultânea real entre dispositivos** | O modelo de multi-dispositivo (seção 12) é "alternado com aviso de lock", não sincronização em tempo real. Se dois dispositivos editarem ao mesmo tempo ignorando o aviso de lock, o backup mais recente sobrescreve o outro sem mesclar — risco de perda de dados aceito por decisão de produto, dado que não há servidor |
| **Exportação limitada** | Apenas a lista de itens de ordens de compra pode ser exportada para planilha; as demais telas não têm exportação prevista |
| **Sem controle de saldo de licitação** | Funcionalidade removida do escopo do sistema (decisão de 2026-06-26) — qualquer acompanhamento de licitação é feito fora do TrigoBom |
| **Volume de uso** | Dimensionado para baixo volume (~30 documentos/mês); a inclusão em lote (seção 6.2/6.3) facilita picos pontuais, mas não foi pensada para processamento em lote pesado/contínuo |

---

## 12. Armazenamento e Configuração de Pastas

### 12.1 Motivação

O cliente se desloca com frequência e o custo de servidor ainda não é viável. A solução é dar a ele controle total sobre **onde** os dados ficam guardados — HD/SSD externo, pasta sincronizada do Google Drive/OneDrive, ou qualquer outro local local — sem depender de infraestrutura própria do TrigoBom.

### 12.2 Pastas configuráveis (tela de Configurações)

A tela de Configurações expõe **quatro campos de pasta**, cada um escolhido pelo usuário (podendo ser a mesma unidade física, ex.: um HD externo, em subpastas diferentes):

| Campo | Conteúdo |
|---|---|
| **Pasta de NFs** | PDFs das notas fiscais incluídas |
| **Pasta de Ordens de Compra** | PDFs das ordens de compra incluídas |
| **Pasta de Dados/Backup** | Snapshots do banco SQLite (ver 12.3) |

> A "Pasta de Licitações" foi removida junto com a funcionalidade de Saldo de Licitação (seção 6).

Os caminhos escolhidos são persistidos em `%APPDATA%\TrigoBom\config.json` (não dentro das próprias pastas configuráveis, para que o app sempre saiba onde procurar mesmo que uma unidade esteja desconectada no momento da abertura).

Cada PDF incluído é **copiado** para a pasta correspondente ao seu tipo no momento do upload — o arquivo original informado pelo usuário não é movido nem alterado (mantém a convenção da seção 10). Por serem arquivos estáticos depois de salvos, funcionam bem mesmo em pastas sincronizadas por clientes de nuvem (Drive/OneDrive), que não geram conflito de escrita em arquivos que não são reabertos para edição.

### 12.3 Banco de dados: local + backup, não escrita direta na pasta do usuário

O banco SQLite **não** vive diretamente na pasta escolhida pelo usuário. Ele continua como cópia de trabalho local em `%APPDATA%\TrigoBom\trigo_bom.db`, lido e escrito normalmente pelo app. Motivo: SQLite com escrita ativa não é seguro dentro de uma pasta sincronizada em tempo real (o cliente de sync pode mover/baixar o arquivo no meio de uma transação) nem imune a queda de energia/desconexão de um HD externo durante a escrita.

A cada salvamento relevante (e ao fechar o app), o sistema grava um **snapshot/backup** do banco na Pasta de Dados/Backup configurada. Esse arquivo é estático após escrito — seguro para nuvem ou HD externo.

Além disso, um **timer de 10 minutos** dispara o mesmo backup automaticamente enquanto o app estiver aberto, mesmo sem nenhum salvamento explícito do usuário no intervalo — reduz a janela de perda de dados em sessões longas sem fechar o app.

### 12.4 Restauração ao abrir o app (suporte a múltiplos dispositivos)

Ao iniciar, o app compara a data/versão do snapshot na Pasta de Dados/Backup com a do banco local:

- Se o snapshot remoto for **mais novo**, o app oferece restaurá-lo antes de continuar (é assim que o cliente "leva os dados" de um dispositivo para outro — notebook, HD externo, outro computador).
- Se o local for igual ou mais novo, segue normalmente.

### 12.5 Lock de uso simultâneo

Não há servidor para arbitrar escrita concorrente real entre dispositivos. Para reduzir (não eliminar) o risco de dois dispositivos abertos ao mesmo tempo apontando para a mesma Pasta de Dados/Backup:

- Ao abrir, o app grava um arquivo de lock na Pasta de Dados/Backup contendo identificação do dispositivo e timestamp.
- Se já existir um lock de outro dispositivo, o app avisa o usuário antes de prosseguir (não bloqueia — é um alerta, já que o cliente pode estar ciente e optar por continuar).
- O lock é removido ao fechar o app normalmente; um lock "preso" (de um fechamento anormal) é tratado por expiração/timestamp antigo, não impedindo o uso indefinidamente.

Esse modelo é "alternado com aviso", não sincronização em tempo real — ver limitação correspondente na seção 11.

---

## 13. Versionamento (CHANGELOG)

O histórico de mudanças do projeto é mantido em [CHANGELOG.md](CHANGELOG.md).

**Instrução obrigatória:** ao final de toda conversa em que algum arquivo do projeto for criado, editado ou removido, adicione uma nova entrada no topo do `CHANGELOG.md`, seguindo o formato já usado no arquivo:

```
## [AAAA-MM-DD] Título curto da sessão

- Mudança 1
- Mudança 2

**Arquivos afetados:** lista de arquivos/pastas alterados
```

Regras:
- Use a data real da conversa (formato `AAAA-MM-DD`).
- Uma entrada por sessão/conversa, não por arquivo.
- Descreva o que mudou e por quê (não apenas "editado arquivo X"), de forma curta e direta.
- Liste os arquivos afetados.
- Nunca edite entradas antigas — apenas adicione novas no topo.
- Se a conversa não resultou em nenhuma mudança de arquivo (só discussão/planejamento), não criar entrada.

---

## 14. Distribuição e Atualizações

> **Contexto:** cliente único hoje, baixo volume de releases, sem orçamento/necessidade de infraestrutura de servidor (mesma lógica da seção 12.1). As decisões abaixo priorizam simplicidade operacional sobre automação completa.

### 14.1 Versionamento

- O projeto usa **semver** (`MAJOR.MINOR.PATCH`).
- A versão vive em **um único lugar**: `app/__version__.py`, na constante `__version__`. É essa constante que a UI (ex.: tela "Sobre") e o script de build leem — nunca duplicar o número em outro arquivo.
- Cada versão entregue ao cliente corresponde a uma **tag git** (`vX.Y.Z`) e a uma entrada do `CHANGELOG.md` (seção 13). A tag marca o commit exato que foi empacotado.

### 14.2 Build (PyInstaller)

- Usar **`--onedir`**, não `--onefile`. O onefile se autoextrai numa pasta temporária a cada abertura — mais lento (perceptível com Qt/Chromium embutido) e mais propenso a falso positivo de antivírus, já que "executável que extrai e roda outro código" é a assinatura típica de um dropper. O onedir abre direto e levanta menos suspeita; o instalador (seção 14.3) cuida de esconder a pasta do cliente atrás de um atalho.
- `requirements.txt` deve manter **versões fixas** (`==`, não `>=`) a partir de agora, para que o build seja reprodutível — um rebuild futuro não deve trazer uma versão de lib diferente da que foi testada.

### 14.3 Empacotamento (Inno Setup)

- A pasta gerada pelo PyInstaller é embrulhada num instalador único (`TrigoBomSetup-X.Y.Z.exe`) com **Inno Setup** (gratuito, scriptável).
- O instalador **preserva `%APPDATA%\TrigoBom`** entre versões — nunca apaga `trigo_bom.db` ou `config.json` do cliente numa atualização.
- **Tesseract OCR encadeado:** o instalador inclui o instalador oficial do Tesseract (build UB-Mannheim) como arquivo extra e o dispara silenciosamente durante a instalação — mas **só se o Tesseract ainda não estiver presente** na máquina (checar `tesseract.exe` no `PATH`/caminho padrão antes de rodar o setup encadeado), para não forçar reinstalação a cada atualização do TrigoBom.
- **Sem assinatura de código** por enquanto — o aviso do Windows SmartScreen ("aplicativo desconhecido") é aceito como custo operacional dado o cliente único. Reavaliar se o app passar a ser distribuído para mais clientes.

### 14.4 Distribuição (GitHub Releases)

- Cada versão é publicada como uma **Release** no repositório (privado), com a tag `vX.Y.Z` e o instalador anexado como asset.
- Como o repositório é privado, o cliente não acessa a página de Release diretamente — a entrega ao cliente continua **manual** (link do asset ou arquivo enviado por e-mail/Drive).
- Vantagem de usar Releases mesmo com entrega manual: histórico de versões centralizado, sem precisar gerenciar uma pasta de "versões antigas" à parte.

### 14.5 Atualizações

Duas fases, para não construir automação que o projeto não precisa ainda:

1. **Fase atual (manual):** você builda, publica a Release, envia o link/instalador ao cliente. Ele instala por cima da versão anterior (o Inno Setup faz upgrade in-place, preservando os dados — seção 14.3). Sem código extra, sem risco de auto-update quebrar algo num app que controla dinheiro.
2. **Fase futura (notificação, não auto-update):** se o cliente passar a reclamar de não saber que há versão nova, adicionar uma checagem leve no `main.py` — ao abrir, consulta a API do GitHub pela release mais recente, compara com `app.__version__.__version__`, e mostra um banner discreto "Nova versão disponível" com link de download. **Sem download/instalação silenciosa automática** — evita precisar de certificado de assinatura e o risco de uma atualização forçada travar o app no meio do expediente do cliente.
