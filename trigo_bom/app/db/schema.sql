CREATE TABLE IF NOT EXISTS orgaos (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL
);

INSERT OR IGNORE INTO orgaos (id, nome) VALUES
    (1, 'Administração'),
    (2, 'Saúde'),
    (3, 'Educação'),
    (4, 'Assistência Social');

CREATE TABLE IF NOT EXISTS notas_fiscais (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    numero            TEXT,
    orgao_id          INTEGER REFERENCES orgaos(id),
    data_emissao      TEXT,
    valor             REAL,
    categoria         TEXT,
    status_pagamento  TEXT DEFAULT 'nao_pago',
    data_vencimento   TEXT,
    data_pagamento    TEXT,
    arquivo_pdf       TEXT,
    criado_em         TEXT DEFAULT (datetime('now', 'localtime')),
    origem            TEXT
);

CREATE TABLE IF NOT EXISTS itens_nota_fiscal (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    nota_fiscal_id  INTEGER REFERENCES notas_fiscais(id) ON DELETE CASCADE,
    descricao       TEXT,
    quantidade      REAL,
    valor_unitario  REAL,
    valor_total     REAL,
    ncm             TEXT,
    cfop            TEXT
);

CREATE TABLE IF NOT EXISTS listas_compra (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    nome            TEXT NOT NULL,
    data_prevista   TEXT,
    status_entrega  TEXT DEFAULT 'pendente',
    criado_em       TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS ordens_compra (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    numero                TEXT,
    fornecedor            TEXT,
    data_emissao          TEXT,
    data_entrega_prevista TEXT,
    status_entrega        TEXT DEFAULT 'pendente',
    arquivo_pdf           TEXT
);

CREATE TABLE IF NOT EXISTS itens_ordem_compra (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ordem_compra_id INTEGER REFERENCES ordens_compra(id) ON DELETE CASCADE,
    descricao       TEXT,
    unidade         TEXT,
    quantidade      REAL,
    valor_unitario  REAL,
    valor_total     REAL
);
