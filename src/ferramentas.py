"""Ferramentas determinísticas do Fin.

TODO número que o agente apresenta nasce aqui, calculado a partir dos arquivos da pasta
data/. O LLM não faz contas: ele recebe estes resultados e apenas os explica.
"""
from __future__ import annotations

import re

from base_conhecimento import BaseConhecimento
from utils import brl, nome_mes, normalizar, pct, rotulo_categoria

ORDEM_RISCO = {"baixo": 0, "medio": 1, "alto": 2}


def _rotulo_risco(risco: str) -> str:
    return {"medio": "médio"}.get(risco, risco)


# ---------------------------------------------------------------------------
# Transações
# ---------------------------------------------------------------------------
def resumo_mensal(base: BaseConhecimento) -> dict[str, dict]:
    """Entradas, saídas, saldo e taxa de poupança por mês (YYYY-MM)."""
    resultado = {}
    for mes, g in base.transacoes.groupby("mes"):
        entradas = float(g.loc[g["tipo"] == "entrada", "valor"].sum())
        saidas = float(g.loc[g["tipo"] == "saida", "valor"].sum())
        saldo = entradas - saidas
        resultado[mes] = {
            "entradas": round(entradas, 2),
            "saidas": round(saidas, 2),
            "saldo": round(saldo, 2),
            "taxa_poupanca": round(saldo / entradas * 100, 1) if entradas else 0.0,
        }
    return dict(sorted(resultado.items()))


def gastos_por_categoria(base: BaseConhecimento) -> dict[str, dict[str, float]]:
    """{mes: {categoria: total}} considerando apenas saídas, ordenado do maior para o menor."""
    saidas = base.transacoes[base.transacoes["tipo"] == "saida"]
    resultado = {}
    for mes, g in saidas.groupby("mes"):
        soma = g.groupby("categoria")["valor"].sum().sort_values(ascending=False)
        resultado[mes] = {cat: round(float(v), 2) for cat, v in soma.items()}
    return dict(sorted(resultado.items()))


def ultimo_mes(base: BaseConhecimento) -> str:
    return sorted(base.transacoes["mes"].unique())[-1]


def capacidade_poupanca(base: BaseConhecimento) -> dict:
    saldos = [m["saldo"] for m in resumo_mensal(base).values()]
    return {
        "media_mensal": round(sum(saldos) / len(saldos), 2),
        "ultimo_mes": saldos[-1],
        "meses_considerados": len(saldos),
    }


def variacao_categorias(base: BaseConhecimento) -> list[dict]:
    """Compara o último mês com o anterior, por categoria e por lançamento (descrição)."""
    meses = sorted(base.transacoes["mes"].unique())
    if len(meses) < 2:
        return []
    atual, anterior = meses[-1], meses[-2]
    saidas = base.transacoes[base.transacoes["tipo"] == "saida"]
    resultado = []
    for cat in sorted(saidas["categoria"].unique()):
        g_atual = saidas[(saidas["mes"] == atual) & (saidas["categoria"] == cat)]
        g_ant = saidas[(saidas["mes"] == anterior) & (saidas["categoria"] == cat)]
        v_atual, v_ant = float(g_atual["valor"].sum()), float(g_ant["valor"].sum())
        por_desc_atual = g_atual.groupby("descricao")["valor"].sum().to_dict()
        por_desc_ant = g_ant.groupby("descricao")["valor"].sum().to_dict()
        lancamentos = [
            {"descricao": d, "atual": round(float(por_desc_atual.get(d, 0.0)), 2),
             "anterior": round(float(por_desc_ant.get(d, 0.0)), 2)}
            for d in sorted(set(por_desc_atual) | set(por_desc_ant))
        ]
        resultado.append({
            "categoria": cat, "mes_atual": atual, "mes_anterior": anterior,
            "atual": round(v_atual, 2), "anterior": round(v_ant, 2),
            "diferenca": round(v_atual - v_ant, 2),
            "diferenca_pct": round((v_atual - v_ant) / v_ant * 100, 1) if v_ant else None,
            "lancamentos": lancamentos,
        })
    return resultado


# ---------------------------------------------------------------------------
# Metas
# ---------------------------------------------------------------------------
def meses_de_contribuicao(prazo: str, data_ref: str) -> int:
    """Quantos aportes mensais cabem entre a data de referência e o prazo (inclusive)."""
    ano_p, mes_p = (int(x) for x in prazo.split("-")[:2])
    ano_r, mes_r = (int(x) for x in data_ref.split("-")[:2])
    return max((ano_p - ano_r) * 12 + (mes_p - mes_r) + 1, 0)


def patrimonio_livre(base: BaseConhecimento) -> float:
    p = base.perfil
    return max(p["patrimonio_total"] - p["reserva_emergencia_atual"], 0.0)


def _eh_meta_reserva(nome_meta: str) -> bool:
    return "reserva" in normalizar(nome_meta)


def progresso_metas(base: BaseConhecimento, data_ref: str) -> list[dict]:
    p = base.perfil
    metas = []
    for m in p["metas"]:
        reserva = _eh_meta_reserva(m["meta"])
        atual = p["reserva_emergencia_atual"] if reserva else patrimonio_livre(base)
        premissa = None
        if not reserva:
            premissa = (
                f"considera os {brl(patrimonio_livre(base))} do patrimônio que estão fora "
                "da reserva como já destinados a esta meta"
            )
        alvo = m["valor_necessario"]
        falta = max(alvo - atual, 0.0)
        meses = meses_de_contribuicao(m["prazo"], data_ref)
        metas.append({
            "meta": m["meta"],
            "alvo": alvo,
            "atual": atual,
            "falta": round(falta, 2),
            "progresso_pct": round(min(atual / alvo * 100, 100), 1) if alvo else 100.0,
            "prazo": m["prazo"],
            "meses_restantes": meses,
            "aporte_mensal_necessario": round(falta / meses, 2) if meses > 0 else None,
            "eh_reserva": reserva,
            "premissa": premissa,
        })
    return metas


def viabilidade(base: BaseConhecimento, data_ref: str) -> dict:
    """Compara o aporte mensal exigido pelas metas com a capacidade média de poupança."""
    metas = progresso_metas(base, data_ref)
    exigido = round(sum(m["aporte_mensal_necessario"] or 0 for m in metas), 2)
    capacidade = capacidade_poupanca(base)["media_mensal"]
    folga = round(capacidade - exigido, 2)
    return {
        "aporte_exigido_periodo_mais_exigente": exigido,
        "capacidade_media": capacidade,
        "folga_mensal": folga,
        "viavel": folga >= 0,
    }


def _periodo_apos(data_ref: str, deslocamento: int) -> str:
    ano, mes = (int(x) for x in data_ref.split("-")[:2])
    indice = ano * 12 + (mes - 1) + deslocamento
    return f"{indice // 12:04d}-{indice % 12 + 1:02d}"


def simular_aporte(base: BaseConhecimento, valor_mensal: float, data_ref: str) -> dict:
    """Simula aportes mensais fixos: primeiro a reserva, depois as demais metas (por prazo)."""
    if valor_mensal <= 0:
        raise ValueError("O valor mensal precisa ser positivo.")

    metas = sorted(
        progresso_metas(base, data_ref),
        key=lambda m: (not m["eh_reserva"], m["prazo"]),
    )
    faltas = {m["meta"]: m["falta"] for m in metas}
    conclusao: dict[str, tuple[str, int] | None] = {
        m["meta"]: ("já concluída", 0) if m["falta"] <= 0 else None for m in metas
    }

    for mes_idx in range(1, 601):  # até 50 anos
        disponivel = valor_mensal
        for m in metas:
            nome = m["meta"]
            if faltas[nome] > 0 and disponivel > 0:
                uso = min(disponivel, faltas[nome])
                faltas[nome] -= uso
                disponivel -= uso
                if faltas[nome] <= 1e-6 and conclusao[nome] is None:
                    conclusao[nome] = (_periodo_apos(data_ref, mes_idx - 1), mes_idx)
        if all(v is not None for v in conclusao.values()):
            break

    resultado = []
    for m in metas:
        concl = conclusao[m["meta"]]
        if concl is None:
            resultado.append({"meta": m["meta"], "conclui_em": None, "meses": None,
                              "prazo": m["prazo"], "no_prazo": False})
        else:
            periodo, meses = concl
            no_prazo = periodo == "já concluída" or periodo <= m["prazo"]
            resultado.append({"meta": m["meta"], "conclui_em": periodo, "meses": meses,
                              "prazo": m["prazo"], "no_prazo": no_prazo})

    cap = capacidade_poupanca(base)["media_mensal"]
    return {
        "valor_mensal": valor_mensal,
        "acima_da_capacidade": valor_mensal > cap,
        "capacidade_media": cap,
        "metas": resultado,
    }


# ---------------------------------------------------------------------------
# Produtos
# ---------------------------------------------------------------------------
def risco_maximo(perfil: dict) -> str:
    """Se o cliente declara não aceitar risco, essa restrição prevalece sobre o rótulo do perfil."""
    if not perfil.get("aceita_risco", False):
        return "baixo"
    return {"conservador": "baixo", "moderado": "medio", "arrojado": "alto"}.get(
        normalizar(perfil["perfil_investidor"]), "baixo"
    )


def produtos_compativeis(base: BaseConhecimento) -> dict:
    limite = risco_maximo(base.perfil)
    para_reserva, para_prazo_maior, incompativeis = [], [], []
    for prod in base.produtos:
        if ORDEM_RISCO[prod["risco"]] > ORDEM_RISCO[limite]:
            incompativeis.append({
                "nome": prod["nome"],
                "motivo": f"risco {_rotulo_risco(prod['risco'])} acima do máximo aceito pelo perfil, que é {_rotulo_risco(limite)}",
            })
        elif re.search(r"reserva|diari", normalizar(prod["indicado_para"])):
            para_reserva.append(prod["nome"])
        else:
            para_prazo_maior.append(prod["nome"])
    return {
        "risco_maximo": limite,
        "para_reserva": para_reserva,
        "para_metas_de_prazo_maior": para_prazo_maior,
        "incompativeis": incompativeis,
    }


# ---------------------------------------------------------------------------
# Insights proativos
# ---------------------------------------------------------------------------
def insights_proativos(base: BaseConhecimento, data_ref: str) -> list[dict]:
    """Observações que o agente traz sem ser perguntado. Texto 100% derivado dos dados."""
    insights: list[dict] = []
    perfil = base.perfil
    metas = progresso_metas(base, data_ref)
    viab = viabilidade(base, data_ref)
    resumo = resumo_mensal(base)
    gastos = gastos_por_categoria(base)
    meses = list(resumo)
    atual = meses[-1]

    # 1) Meta de reserva de emergência
    reserva = next((m for m in metas if m["eh_reserva"]), None)
    if reserva and reserva["falta"] > 0 and reserva["aporte_mensal_necessario"] is not None:
        folga_ok = viab["capacidade_media"] >= reserva["aporte_mensal_necessario"]
        insights.append({
            "id": "reserva",
            "severidade": "positivo" if folga_ok else "atencao",
            "titulo": "Reserva de emergência",
            "texto": (
                f"Sua reserva está em {pct(reserva['progresso_pct'])} da meta "
                f"({brl(reserva['atual'])} de {brl(reserva['alvo'])}). Faltam {brl(reserva['falta'])} "
                f"e restam {reserva['meses_restantes']} meses até {nome_mes(reserva['prazo'])}: "
                f"são {brl(reserva['aporte_mensal_necessario'])} por mês."
            ),
            "pergunta_sugerida": "Quanto preciso guardar por mês para completar a reserva no prazo?",
        })

    # 2) Viabilidade conjunta das metas
    if len(metas) > 1:
        apertada = viab["viavel"] and viab["folga_mensal"] < 0.10 * viab["capacidade_media"]
        if viab["viavel"]:
            texto = (
                f"No período mais exigente (com as duas metas em andamento) você precisa guardar "
                f"{brl(viab['aporte_exigido_periodo_mais_exigente'])} por mês. Sua média de sobra é "
                f"{brl(viab['capacidade_media'])}, então há folga de {brl(viab['folga_mensal'])} por mês"
                + (": cabe, mas a margem é apertada e qualquer imprevisto pesa." if apertada else ".")
            )
        else:
            texto = (
                f"No período mais exigente você precisaria guardar "
                f"{brl(viab['aporte_exigido_periodo_mais_exigente'])} por mês, mas sua média de sobra é "
                f"{brl(viab['capacidade_media'])}. Faltam {brl(abs(viab['folga_mensal']))} por mês: "
                "vale revisar prazo ou valor de alguma meta."
            )
        insights.append({
            "id": "viabilidade",
            "severidade": "positivo" if viab["viavel"] and not apertada else "atencao",
            "titulo": "Suas metas cabem no orçamento?",
            "texto": texto,
            "pergunta_sugerida": "Minhas metas cabem no meu orçamento?",
        })

    # 3) Categoria que mais subiu no último mês
    if len(meses) >= 2:
        anterior = meses[-2]
        maior = None
        for cat, valor in gastos[atual].items():
            antes = gastos[anterior].get(cat, 0.0)
            aumento = valor - antes
            if antes > 0 and aumento >= 20 and aumento / antes >= 0.10:
                if maior is None or aumento > maior[1]:
                    maior = (cat, aumento, antes, valor)
        if maior:
            cat, aumento, antes, valor = maior
            insights.append({
                "id": "variacao",
                "severidade": "info",
                "titulo": f"{rotulo_categoria(cat)} subiu",
                "texto": (
                    f"Em {nome_mes(atual)} você gastou {brl(valor)} com {rotulo_categoria(cat).lower()}, "
                    f"contra {brl(antes)} em {nome_mes(anterior)} (+{brl(aumento)}). "
                    "Não é um problema em si: só um ponto para ficar de olho."
                ),
                "pergunta_sugerida": f"Por que meus gastos com {rotulo_categoria(cat).lower()} subiram?",
            })

    # 4) Taxa de poupança do último mês
    r = resumo[atual]
    insights.append({
        "id": "poupanca",
        "severidade": "positivo" if r["saldo"] > 0 else "atencao",
        "titulo": "Quanto sobrou no mês",
        "texto": (
            f"Em {nome_mes(atual)} entraram {brl(r['entradas'])} e saíram {brl(r['saidas'])}: "
            f"sobraram {brl(r['saldo'])} ({pct(r['taxa_poupanca'])} da renda)."
        ),
        "pergunta_sugerida": "Como estão meus gastos por categoria?",
    })

    # 5) Continuidade com o último assunto atendido
    nomes_produto = {normalizar(p["nome"]): p["nome"] for p in base.produtos}
    for _, linha in base.historico.iloc[::-1].iterrows():
        tema = normalizar(str(linha["tema"]))
        casado = next((orig for norm, orig in nomes_produto.items() if tema in norm or norm in tema), None)
        if casado:
            data = linha["data"].strftime("%d/%m/%Y")
            insights.append({
                "id": "continuidade",
                "severidade": "info",
                "titulo": "De onde paramos",
                "texto": (
                    f"Em {data} você tirou dúvidas sobre {linha['tema']}. "
                    f"Posso mostrar como isso se relaciona com as suas metas, se quiser."
                ),
                "pergunta_sugerida": f"Como {casado} se relaciona com as minhas metas?",
            })
            break

    # 6) Transparência sobre o perfil
    if normalizar(perfil["perfil_investidor"]) == "moderado" and not perfil.get("aceita_risco", False):
        insights.append({
            "id": "perfil",
            "severidade": "info",
            "titulo": "Como tratamos seu perfil",
            "texto": (
                "Seu perfil está como 'moderado', mas você indicou que não aceita risco. "
                "Por segurança, a restrição de risco prevalece e só sugiro produtos de risco baixo."
            ),
            "pergunta_sugerida": "Quais produtos combinam com o meu perfil?",
        })

    return insights
