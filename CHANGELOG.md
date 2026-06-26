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
