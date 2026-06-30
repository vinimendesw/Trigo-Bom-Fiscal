"""
Camada 1 — Detecção automática de órgão por palavra-chave (CLAUDE.md seção 6.3).
"""
from extracao.orgao import detectar_orgao


def test_detecta_saude():
    assert detectar_orgao("SECRETARIA MUNICIPAL DE SAÚDE DE GOIANAPOLIS") == 2


def test_detecta_educacao():
    assert detectar_orgao("SECRETARIA MUNICIPAL DE EDUCAÇÃO") == 3


def test_detecta_educacao_sem_acento():
    assert detectar_orgao("SECRETARIA MUNICIPAL DE EDUCACAO") == 3


def test_detecta_assistencia_social():
    assert detectar_orgao("SECRETARIA DE ASSISTÊNCIA SOCIAL DE GOIANAPOLIS") == 4


def test_detecta_administracao_generica_prefeitura():
    assert detectar_orgao("PREFEITURA MUNICIPAL DE GOIANAPOLIS") == 1


def test_detecta_administracao_por_palavra_administracao():
    assert detectar_orgao("SECRETARIA DE ADMINISTRAÇÃO DE GOIANAPOLIS") == 1


def test_nao_detecta_quando_sem_palavra_chave():
    assert detectar_orgao("DISTRIBUIDORA CENTRAL LTDA") is None


def test_nao_detecta_com_texto_vazio():
    assert detectar_orgao("") is None
    assert detectar_orgao(None) is None


def test_secretaria_especifica_tem_prioridade_sobre_municipal():
    # "MUNICIPAL" por si só cairia em Administração, mas "SAÚDE" é mais específico
    # e deve prevalecer.
    assert detectar_orgao("SECRETARIA MUNICIPAL DE SAÚDE") == 2


def test_aceita_multiplos_textos_concatenados():
    assert detectar_orgao("", "SECRETARIA MUNICIPAL DE EDUCAÇÃO") == 3


def test_case_insensitive():
    assert detectar_orgao("secretaria municipal de saude") == 2
