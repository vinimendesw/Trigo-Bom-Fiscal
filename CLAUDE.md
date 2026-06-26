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
| **PyMuPDF (fitz)** | Suporte/fallback para extração de texto quando `pdfplumber` não resolver bem o layout |
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
- Detecção automática de órgão a partir de dados da NF (ex.: cadastro do fornecedor/destinatário) é uma automação **planejada, ainda sem desenho definido** — quando implementada, está autorizada a pré-selecionar o órgão **sem exigir confirmação manual**, como exceção pontual à regra geral da seção 10 (toda extração automática passa por conferência antes de salvar). Decisão de produto já registrada; lógica de detecção fica para conversa futura.

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

```bash
pyinstaller --noconfirm --windowed --name TrigoBom app/main.py
```

**Saída em `dist/TrigoBom/`:**
- Executável único para Windows, sem exigir Python instalado na máquina do cliente.

> A definição final de ícone, arquivos adicionais (`--add-data`) e geração de instalador (ex.: Inno Setup/NSIS) fica para quando o projeto entrar na fase de empacotamento.

---

## 10. Convenções

- Os arquivos originais (PDFs de NF, OC) **nunca são alterados ou movidos** pelo sistema — apenas lidos. Os dados extraídos são gravados no SQLite.
- Toda extração automática deve permitir **conferência/correção manual** antes de salvar (a leitura é automática, mas o usuário confirma antes de persistir). **Exceção planejada:** a futura detecção automática do órgão de uma NF (seção 6.3) está autorizada a pré-selecionar sem exigir confirmação manual — desenho da lógica ainda pendente.
- Fluxos manuais (status de pagamento) **não têm qualquer tentativa de automação além da exceção acima** — são sempre ação explícita do usuário.

---

## 11. Limitações Conhecidas

| Limitação | Detalhes |
|---|---|
| **Extração depende do layout do PDF** | `pdfplumber`/`PyMuPDF` extraem bem PDFs com texto selecionável e layout consistente; PDFs escaneados como imagem (sem OCR) não são suportados no momento |
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
