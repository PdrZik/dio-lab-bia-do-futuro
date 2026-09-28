"""Montagem do contexto enviado ao LLM: dados do cliente + FATOS CALCULADOS + glossário."""
from __future__ import annotations

import re

import ferramentas as ft
from base_conhecimento import BaseConhecimento, buscar_glossario
from utils import brl, nome_mes, normalizar, pct, rotulo_categoria

GATILHOS_SIMULACAO = ("guardar", "poupar", "aportar", "investir", "separar", "depositar", "economizar")
_VALOR = r"(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d{1,2}))?"
_RE_SIMULACAO = re.compile(
    rf"(?:r\$\s*{_VALOR})|(?:{_VALOR}\s*reais)|(?:{_VALOR}\s*(?:por|ao|/)\s*m[eê]s)",
    re.IGNORECASE,
)


def extrair_valor_simulacao(mensagem: str) -> float | None:
    """Detecta 'e se eu guardar R$ 1.000 por mês?' e devolve 1000.0 (ou None)."""
    texto = normalizar(mensagem)
    if not any(g in texto for g in GATILHOS_SIMULACAO):
        return None
    m = _RE_SIMULACAO.search(mensagem)
    if not m:
        return None
    grupos = [g for g in m.groups() if g is not None]
    inteiro = grupos[0].replace(".", "")
    centavos = grupos[1] if len(grupos) > 1 else None
    valor = float(inteiro) + (float(centavos) / 10 ** len(centavos) if centavos else 0)
    return valor if valor >= 50 else None


def montar_contexto(base: BaseConhecimento, data_ref: str, mensagem: str = "") -> str:
    p = base.perfil
    linhas: list[str] = []
    add = linhas.append

    add("=== DATA DE REFERÊNCIA ===")
    ano, mes = data_ref.split("-")[:2]
    add(f"Considere que hoje é o início de {nome_mes(f'{ano}-{mes}')} (dados de exemplo).")

    add("\n=== CLIENTE (fonte: perfil_investidor.json) ===")
    add(f"- Nome: {p['nome']}, {p['idade']} anos, {p['profissao']}")
    add(f"- Renda mensal: {brl(p['renda_mensal'])}")
    add(f"- Perfil declarado: {p['perfil_investidor']} | Aceita risco: {'sim' if p['aceita_risco'] else 'não'}")
    add(f"- Objetivo principal: {p['objetivo_principal']}")
    add(f"- Patrimônio total: {brl(p['patrimonio_total'])} | Reserva atual: {brl(p['reserva_emergencia_atual'])}")

    add("\n=== RESUMO MENSAL (fonte: transacoes.csv) ===")
    resumo = ft.resumo_mensal(base)
    for mes_, r in resumo.items():
        add(f"- {nome_mes(mes_)}: entradas {brl(r['entradas'])} | saídas {brl(r['saidas'])} | "
            f"saldo {brl(r['saldo'])} | taxa de poupança {pct(r['taxa_poupanca'])}")
    cap = ft.capacidade_poupanca(base)
    add(f"- Média mensal de sobra ({cap['meses_considerados']} meses): {brl(cap['media_mensal'])}")

    add("\n=== GASTOS POR CATEGORIA (fonte: transacoes.csv) ===")
    for mes_, cats in ft.gastos_por_categoria(base).items():
        total = resumo[mes_]["saidas"]
        partes = [f"{rotulo_categoria(c)} {brl(v)} ({pct(v / total * 100)})" for c, v in cats.items()]
        add(f"- {nome_mes(mes_)} (total {brl(total)}): " + "; ".join(partes))

    variacoes = ft.variacao_categorias(base)
    if variacoes:
        v0 = variacoes[0]
        add(f"\n=== VARIAÇÃO POR CATEGORIA: {nome_mes(v0['mes_atual'])} vs {nome_mes(v0['mes_anterior'])} (fonte: transacoes.csv) ===")
        for v in variacoes:
            sinal = "+" if v["diferenca"] >= 0 else "-"
            pct_txt = f", {sinal}{pct(abs(v['diferenca_pct']))}" if v["diferenca_pct"] is not None else ""
            detalhe = "; ".join(f"{l['descricao']} {brl(l['atual'])} (antes {brl(l['anterior'])})" for l in v["lancamentos"])
            add(f"- {rotulo_categoria(v['categoria'])}: {brl(v['atual'])} vs {brl(v['anterior'])} "
                f"({sinal}{brl(abs(v['diferenca']))}{pct_txt}) | {detalhe}")

    add("\n=== METAS (calculado a partir de perfil_investidor.json) ===")
    for m in ft.progresso_metas(base, data_ref):
        add(f"- {m['meta']}: alvo {brl(m['alvo'])} | atual {brl(m['atual'])} | falta {brl(m['falta'])} | "
            f"progresso {pct(m['progresso_pct'])} | prazo {nome_mes(m['prazo'])} | "
            f"{m['meses_restantes']} meses de aporte | aporte mensal necessário "
            f"{brl(m['aporte_mensal_necessario']) if m['aporte_mensal_necessario'] is not None else 'n/d'}")
        if m["premissa"]:
            add(f"  (premissa: {m['premissa']})")
    v = ft.viabilidade(base, data_ref)
    add(f"- Viabilidade: aporte exigido no período mais exigente {brl(v['aporte_exigido_periodo_mais_exigente'])} | "
        f"capacidade média {brl(v['capacidade_media'])} | folga mensal {brl(v['folga_mensal'])} | "
        f"{'as metas cabem' if v['viavel'] else 'as metas NÃO cabem'} no orçamento")

    add("\n=== PRODUTOS DO CATÁLOGO (fonte: produtos_financeiros.json) ===")
    for prod in base.produtos:
        add(f"- {prod['nome']} | {prod['categoria']} | risco {prod['risco']} | rentabilidade: "
            f"{prod['rentabilidade']} | aporte mínimo {brl(prod['aporte_minimo'])} | indicado para: {prod['indicado_para']}")
    comp = ft.produtos_compativeis(base)
    add(f"COMPATIBILIDADE COM O PERFIL (risco máximo aceito: {comp['risco_maximo']}):")
    add(f"- Compatíveis para reserva/liquidez: {', '.join(comp['para_reserva']) or 'nenhum'}")
    add(f"- Compatíveis para metas de prazo maior: {', '.join(comp['para_metas_de_prazo_maior']) or 'nenhum'}")
    for inc in comp["incompativeis"]:
        add(f"- INCOMPATÍVEL: {inc['nome']} ({inc['motivo']})")

    add("\n=== HISTÓRICO DE ATENDIMENTO (fonte: historico_atendimento.csv) ===")
    for _, h in base.historico.iterrows():
        add(f"- {h['data'].strftime('%d/%m/%Y')} | {h['canal']} | {h['tema']} | {h['resumo']} | resolvido: {h['resolvido']}")

    add("\n=== INSIGHTS PROATIVOS (já calculados) ===")
    for i in ft.insights_proativos(base, data_ref):
        add(f"- {i['titulo']}: {i['texto']}")

    valor_sim = extrair_valor_simulacao(mensagem)
    if valor_sim:
        sim = ft.simular_aporte(base, valor_sim, data_ref)
        add(f"\n=== SIMULAÇÃO SOLICITADA: guardar {brl(valor_sim)} por mês (reserva primeiro, depois as demais metas) ===")
        if sim["acima_da_capacidade"]:
            add(f"- ATENÇÃO: o valor é maior que a média de sobra do cliente ({brl(sim['capacidade_media'])}).")
        for r in sim["metas"]:
            if r["conclui_em"] is None:
                add(f"- {r['meta']}: não é concluída em prazo razoável.")
            elif r["conclui_em"] == "já concluída":
                add(f"- {r['meta']}: já concluída.")
            else:
                situacao = "DENTRO do prazo" if r["no_prazo"] else "FORA do prazo"
                add(f"- {r['meta']}: concluída em {nome_mes(r['conclui_em'])} ({r['meses']} meses), "
                    f"prazo {nome_mes(r['prazo'])} -> {situacao}")

    verbetes = buscar_glossario(base, mensagem)
    if verbetes:
        add("\n=== GLOSSÁRIO (use estas definições para explicar conceitos) ===")
        for vb in verbetes:
            add(f"- {vb['termo']}: {vb['definicao']}")

    return "\n".join(linhas)
