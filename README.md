# TrigoBom Fiscal

App desktop (Windows) para a Trigo Bom organizar a emissão de notas fiscais para o município, o acompanhamento de ordens de compra e o controle manual de pagamentos — lendo PDFs/XMLs de NF e OC diretamente das pastas do usuário, sem depender de ERP ou servidor.

Contexto de produto e problema: [IDEA.md](IDEA.md). Documentação técnica completa (stack, arquitetura, modelo de dados, build e distribuição): [CLAUDE.md](CLAUDE.md). Histórico de mudanças: [CHANGELOG.md](CHANGELOG.md).

## Stack

Python 3.11+, PySide6 + QWebEngineView (shell desktop com a UI em HTML/CSS/JS), pdfplumber/PyMuPDF/pytesseract para extração de PDF, XML padrão da NFe para importação com itens, SQLite local e openpyxl para exportação. Empacotado com PyInstaller + Inno Setup. Detalhes e justificativas na [seção 1](CLAUDE.md#1-stack-tecnológica) e [seção 2](CLAUDE.md#2-por-que-essa-combinação) do CLAUDE.md.

## Como rodar em desenvolvimento

```bash
cd trigo_bom
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app/main.py
```

Requer também o **Tesseract OCR** instalado no sistema (fallback de OCR para DANFEs com texto corrompido) — ver [seção 8](CLAUDE.md#8-como-rodar-em-desenvolvimento) do CLAUDE.md.

## Testes

```bash
cd trigo_bom
pytest
```

## Build e distribuição

```bash
cd trigo_bom
.\build.ps1
```

Gera `dist\TrigoBom-<versão>\` (PyInstaller `--onedir`) e `dist\TrigoBomSetup-<versão>.exe` (instalador Inno Setup, com Tesseract encadeado quando ausente). A versão única do projeto vive em `trigo_bom/app/__version__.py`. Fluxo completo de empacotamento, versionamento e atualizações: [seção 14](CLAUDE.md#14-distribuição-e-atualizações) do CLAUDE.md.

## Status

Cliente único em produção. Sem autenticação, sem sincronização em tempo real entre dispositivos (alternância com aviso de lock) — ver [Limitações Conhecidas](CLAUDE.md#11-limitações-conhecidas).
