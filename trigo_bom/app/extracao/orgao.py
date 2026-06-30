"""
Detecção automática do órgão de uma NF a partir de palavras-chave no nome do
destinatário/remetente (ex.: "PREFEITURA MUNICIPAL DE GOIANAPOLIS",
"SECRETARIA MUNICIPAL DE SAÚDE DE GOIANAPOLIS").

Mapeamento de ids consistente com a tabela `orgaos` (app/db/schema.sql) e com
o frontend (app/ui/app.js — const ORGAOS / app/ui/index.html — #nf-orgao-tags):
    1 = Administração
    2 = Saúde
    3 = Educação
    4 = Assistência Social

Ver CLAUDE.md seção 6.3 — automação autorizada a pré-selecionar o órgão sem
exigir confirmação manual (exceção pontual à regra geral da seção 10).
"""
import unicodedata

# Ordem importa: palavras-chave mais específicas (secretarias) são checadas
# antes da palavra-chave genérica de Administração ("PREFEITURA"), para que
# uma "SECRETARIA MUNICIPAL DE SAÚDE" não seja capturada como Administração
# só por conter "MUNICIPAL".
_PALAVRAS_CHAVE = (
    (2, ("SAUDE",)),
    (3, ("EDUCACAO", "EDUCACIONAL")),
    (4, ("ASSISTENCIA SOCIAL",)),
    (1, ("PREFEITURA", "ADMINISTRACAO", "MUNICIPIO", "MUNICIPAL")),
)


def _normalizar(texto: str) -> str:
    """Maiúsculas e sem acentos, para comparação tolerante a variações de grafia."""
    sem_acento = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode("ascii")
    return sem_acento.upper()


def detectar_orgao(*textos: str) -> int | None:
    """
    Procura palavras-chave de órgão nos textos informados (ex.: nome do
    destinatário extraído da NF). Retorna o id do órgão (1-4) correspondente
    à primeira palavra-chave encontrada, ou None se nenhuma for encontrada.
    """
    texto_norm = _normalizar(" ".join(t for t in textos if t))
    if not texto_norm:
        return None
    for orgao_id, palavras in _PALAVRAS_CHAVE:
        for palavra in palavras:
            if palavra in texto_norm:
                return orgao_id
    return None
