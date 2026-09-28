"""Valores conferidos manualmente a partir de data/*.csv|json."""
import pytest

import ferramentas as ft
from contexto import extrair_valor_simulacao, montar_contexto
from utils import brl, extrair_dinheiro, numeros_no_texto


def test_gastos_de_outubro_batem_com_o_csv_original(base):
    out = ft.gastos_por_categoria(base)["2025-10"]
    assert out["alimentacao"] == 570.00      # 450 + 120
    assert out["moradia"] == 1380.00         # 1200 + 180
    assert out["transporte"] == 295.00       # 45 + 250
    assert out["saude"] == 188.00            # 89 + 99
    assert out["lazer"] == 55.90


def test_resumo_de_outubro(base):
    r = ft.resumo_mensal(base)["2025-10"]
    assert r["entradas"] == 5000.00
    assert r["saidas"] == 2488.90
    assert r["saldo"] == 2511.10
    assert r["taxa_poupanca"] == 50.2


def test_capacidade_media_de_poupanca(base):
    assert ft.capacidade_poupanca(base)["media_mensal"] == 2475.77


def test_meses_de_contribuicao():
    assert ft.meses_de_contribuicao("2026-06", "2025-11-01") == 8
    assert ft.meses_de_contribuicao("2027-12", "2025-11-01") == 26
    assert ft.meses_de_contribuicao("2025-01", "2025-11-01") == 0  # prazo vencido


def test_progresso_das_metas(base, data_ref):
    reserva, apto = ft.progresso_metas(base, data_ref)
    assert reserva["falta"] == 5000.00
    assert reserva["progresso_pct"] == 66.7
    assert reserva["aporte_mensal_necessario"] == 625.00
    assert apto["falta"] == 45000.00
    assert apto["aporte_mensal_necessario"] == 1730.77
    assert apto["premissa"]  # a premissa precisa estar explícita


def test_viabilidade_com_folga_apertada(base, data_ref):
    v = ft.viabilidade(base, data_ref)
    assert v["aporte_exigido_periodo_mais_exigente"] == 2355.77
    assert v["folga_mensal"] == 120.00
    assert v["viavel"] is True


def test_simulacao_2000_por_mes_cumpre_os_prazos(base, data_ref):
    sim = ft.simular_aporte(base, 2000, data_ref)
    reserva, apto = sim["metas"]
    assert (reserva["conclui_em"], reserva["meses"], reserva["no_prazo"]) == ("2026-01", 3, True)
    assert (apto["conclui_em"], apto["meses"], apto["no_prazo"]) == ("2027-11", 25, True)


def test_simulacao_1000_por_mes_nao_cumpre_o_apartamento(base, data_ref):
    sim = ft.simular_aporte(base, 1000, data_ref)
    assert sim["metas"][0]["no_prazo"] is True
    assert sim["metas"][1]["conclui_em"] == "2029-12"
    assert sim["metas"][1]["no_prazo"] is False


def test_simulacao_acima_da_capacidade_e_sinalizada(base, data_ref):
    assert ft.simular_aporte(base, 3000, data_ref)["acima_da_capacidade"] is True


def test_simulacao_valor_invalido(base, data_ref):
    with pytest.raises(ValueError):
        ft.simular_aporte(base, 0, data_ref)


def test_produtos_compativeis_respeitam_aceita_risco_false(base):
    comp = ft.produtos_compativeis(base)
    assert comp["risco_maximo"] == "baixo"
    assert set(comp["para_reserva"]) == {"Tesouro Selic", "CDB Liquidez Diária"}
    assert comp["para_metas_de_prazo_maior"] == ["LCI/LCA"]
    assert {i["nome"] for i in comp["incompativeis"]} == {"Fundo Multimercado", "Fundo de Ações"}


def test_variacao_de_saude_vem_da_farmacia(base):
    saude = next(v for v in ft.variacao_categorias(base) if v["categoria"] == "saude")
    assert saude["diferenca"] == 27.00
    farmacia = next(l for l in saude["lancamentos"] if l["descricao"] == "Farmácia")
    assert (farmacia["anterior"], farmacia["atual"]) == (62.00, 89.00)


def test_insights_incluem_alerta_de_folga_apertada(base, data_ref):
    ids = {i["id"]: i for i in ft.insights_proativos(base, data_ref)}
    assert ids["viabilidade"]["severidade"] == "atencao"
    assert "R$ 120,00" in ids["viabilidade"]["texto"]


@pytest.mark.parametrize("texto,esperado", [
    ("e se eu guardar R$ 1.000 por mês?", 1000.0),
    ("e se eu guardar 2000 por mês", 2000.0),
    ("posso poupar R$ 1.500,50?", 1500.5),
    ("quanto gastei em 2025?", None),          # sem gatilho de simulação
    ("guardar 10 reais", None),                # abaixo do piso de R$ 50
])
def test_extracao_do_valor_de_simulacao(texto, esperado):
    assert extrair_valor_simulacao(texto) == esperado


def test_formatacao_e_extracao_de_dinheiro():
    assert brl(1380) == "R$ 1.380,00"
    assert brl(55.9) == "R$ 55,90"
    assert extrair_dinheiro("R$ 1.380,00 e R$ 570 e R$ 55,9") == [1380.0, 570.0, 55.9]


def test_numeros_no_texto_aceita_formato_br_e_us():
    nums = numeros_no_texto("R$ 1.380,00 | 5000.00 | 55.90")
    assert {1380.0, 5000.0, 55.9} <= nums


def test_contexto_contem_secoes_essenciais(base, data_ref):
    ctx = montar_contexto(base, data_ref, "o que é CDI? e se eu guardar R$ 2.000 por mês?")
    for secao in ("CLIENTE", "RESUMO MENSAL", "GASTOS POR CATEGORIA", "METAS", "PRODUTOS DO CATÁLOGO",
                  "HISTÓRICO DE ATENDIMENTO", "INSIGHTS PROATIVOS", "SIMULAÇÃO SOLICITADA", "GLOSSÁRIO"):
        assert secao in ctx
