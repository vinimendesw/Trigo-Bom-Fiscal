"""
Camada 1 — Testes unitários de _limpar_valor.
Cobre os formatos reais que aparecem em PDFs brasileiros e casos de borda.
"""
import pytest
from extracao.nf import _limpar_valor


@pytest.mark.parametrize("entrada, esperado", [
    # Formato BR padrão
    ("1.234,56",   1234.56),
    ("10.000,00",  10000.0),
    ("0,99",       0.99),
    # Com símbolo R$
    ("R$ 1.500,00", 1500.0),
    # Sem separador de milhar
    ("250,00",     250.0),
    ("1234.56",    1234.56),
    # Valor inteiro sem centavos
    ("500",        500.0),
    # Zeros e limites
    ("0,00",       0.0),
    ("0.00",       0.0),
])
def test_valores_validos(entrada, esperado):
    assert _limpar_valor(entrada) == pytest.approx(esperado)


@pytest.mark.parametrize("entrada", [
    "",
    "abc",
    "R$ ",
    "---",
    None,
])
def test_entradas_invalidas_retornam_none(entrada):
    # _limpar_valor recebe str; None deve ser tratado com segurança
    if entrada is None:
        # a função espera str, mas pode receber None de extrações falhas
        try:
            resultado = _limpar_valor(entrada)
            assert resultado is None
        except (TypeError, AttributeError):
            pass  # aceitável — o chamador deve filtrar None antes
    else:
        assert _limpar_valor(entrada) is None
