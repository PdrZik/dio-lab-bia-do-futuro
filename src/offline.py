"""Modo offline: responde por regras usando as MESMAS ferramentas determinísticas.

Não é um LLM. Serve para (1) demonstrar o agente sem chave de API, (2) rodar os testes
automatizados de forma reproduzível e (3) ser plano B caso o provedor de IA esteja fora do ar.
"""
from __future__ import annotations

import re

import ferramentas as ft
from base_conhecimento import BaseConhecimento, buscar_glossario
from contexto import extrair_valor_simulacao
from utils import brl, nome_mes, normalizar, pct, rotulo_categoria

ALIASES_CATEGORIA = {
    "alimentacao": ["alimentacao", "comida", "mercado", "supermercado", "restaurante"],
    "moradia": ["moradia", "aluguel", "luz", "casa"],
    "transporte": ["transporte", "uber", "combustivel", "gasolina"],
    "saude": ["saude", "farmacia", "academia"],
    "lazer": ["lazer", "netflix", "streaming", "show"],
}
MESES_NOMES = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5, "junho": 6,
    "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
}
RE_TICKER = re.compile(r"\b[a-z]{4}\d{1,2}\b")
STOP_ALIAS = {"liquidez", "diaria", "fundo", "acoes_"}


class OfflineLLM:
    nome = "offline (regras determinísticas)"

    def __init__(self, base: BaseConhecimento, data_ref: str):
        self.base = base
        self.data_ref = data_ref

    def gerar(self, system: str, mensagens: list[dict]) -> str:
        msg = next(
            (m["content"] for m in reversed(mensagens)
             if m["role"] == "user" and not m["content"].startswith("[Verificação")),
            "",
        )
        return responder_offline(self.base, self.data_ref, msg)


# ---------------------------------------------------------------------------
def _min(texto: str) -> str:
    """Minúscula só na primeira letra (preserva siglas como IR)."""
    return texto[:1].lower() + texto[1:] if texto else texto


def _aliases_produto(nome: str) -> set[str]:
    n = normalizar(nome)
    aliases = {n}
    for tok in re.split(r"[ /()]+", n):
        if len(tok) >= 3 and tok not in {"liquidez", "diaria", "fundo", "selic"}:
            aliases.add(tok)
    return aliases


def _produto_mencionado(base: BaseConhecimento, n: str) -> dict | None:
    for prod in base.produtos:
        for alias in _aliases_produto(prod["nome"]):
            if re.search(rf"\b{re.escape(alias)}\b", n):
                return prod
    return None


def _produtos_mencionados(base: BaseConhecimento, n: str) -> list[dict]:
    achados = []
    for prod in base.produtos:
        if any(re.search(rf"\b{re.escape(a)}\b", n) for a in _aliases_produto(prod["nome"])):
            achados.append(prod)
    return achados


def _verbete_do_produto(base: BaseConhecimento, prod: dict) -> dict | None:
    """Verbete do glossário que corresponde ao produto (nome completo ou primeira palavra)."""
    nome = normalizar(prod["nome"])
    primeira = nome.split()[0]
    for v in base.glossario:
        if normalizar(v["termo"]) == nome:
            return v
    for v in base.glossario:
        if normalizar(v["termo"]).startswith(primeira):
            return v
    return None


def _periodo_mencionado(base: BaseConhecimento, n: str) -> str:
    disponiveis = sorted(base.transacoes["mes"].unique())
    for nome, num in MESES_NOMES.items():
        if nome in n:
            for p in disponiveis:
                if int(p.split("-")[1]) == num:
                    return p
    return disponiveis[-1]


def _categoria_mencionada(n: str) -> str | None:
    for cat, aliases in ALIASES_CATEGORIA.items():
        if any(re.search(rf"\b{a}\b", n) for a in aliases):
            return cat
    return None


# ---------------------------------------------------------------------------
def _txt_gastos(base, n) -> str:
    periodo = _periodo_mencionado(base, n)
    gastos = ft.gastos_por_categoria(base)[periodo]
    resumo = ft.resumo_mensal(base)[periodo]
    total = resumo["saidas"]
    cat = _categoria_mencionada(n)
    meses = sorted(ft.gastos_por_categoria(base))
    anterior = meses[meses.index(periodo) - 1] if meses.index(periodo) > 0 else None

    if cat and re.search(r"subi|aument|cresc|por que|porque|variou|mudou|pesou", n):
        var = next((v for v in ft.variacao_categorias(base) if v["categoria"] == cat), None)
        if var:
            mudou = [l for l in var["lancamentos"] if abs(l["atual"] - l["anterior"]) > 0.005]
            sentido = "subiram" if var["diferenca"] > 0 else "caíram" if var["diferenca"] < 0 else "ficaram iguais"
            txt = (f"Seus gastos com {rotulo_categoria(cat).lower()} {sentido}: {brl(var['atual'])} em "
                   f"{nome_mes(var['mes_atual'])} contra {brl(var['anterior'])} em {nome_mes(var['mes_anterior'])}")
            if var["diferenca_pct"] is not None and var["diferenca"] != 0:
                txt += f" ({'+' if var['diferenca'] > 0 else '-'}{pct(abs(var['diferenca_pct']))})"
            txt += ". "
            if mudou:
                itens = "; ".join(f"{l['descricao']} foi de {brl(l['anterior'])} para {brl(l['atual'])}" for l in mudou)
                txt += f"O que mudou nos lançamentos: {itens} (fonte: transacoes.csv). "
            return txt + "Os dados mostram o quê, mas não o motivo; isso só você sabe. Quer que eu compare outra categoria?"

    if cat and cat in gastos:
        valor = gastos[cat]
        txt = (f"Em {nome_mes(periodo)} você gastou {brl(valor)} com {rotulo_categoria(cat).lower()}, "
               f"cerca de {pct(valor / total * 100)} das suas saídas do mês (fonte: transacoes.csv).")
        if anterior:
            antes = ft.gastos_por_categoria(base)[anterior].get(cat)
            if antes is not None:
                txt += f" Em {nome_mes(anterior)} foram {brl(antes)}."
        return txt + " Quer que eu detalhe outra categoria?"

    top = list(gastos.items())[:3]
    partes = ", ".join(f"{rotulo_categoria(c).lower()} ({brl(v)})" for c, v in top)
    return (f"Em {nome_mes(periodo)} suas saídas somaram {brl(total)}, e as maiores categorias foram "
            f"{partes} (fonte: transacoes.csv). Sobraram {brl(resumo['saldo'])}, "
            f"{pct(resumo['taxa_poupanca'])} da sua renda. Quer olhar alguma categoria com mais calma?")


def _txt_metas(base, data_ref, n) -> str:
    metas = ft.progresso_metas(base, data_ref)
    viab = ft.viabilidade(base, data_ref)

    if re.search(r"cabem|cabe |orcamento|viabil|consigo|da para|e possivel", n):
        base_txt = (f"No período mais exigente, com as duas metas andando, você precisaria guardar "
                    f"{brl(viab['aporte_exigido_periodo_mais_exigente'])} por mês; sua média de sobra é "
                    f"{brl(viab['capacidade_media'])}. ")
        if viab["viavel"]:
            return (base_txt + f"Ou seja, as metas cabem, com folga de {brl(viab['folga_mensal'])} por mês. "
                    "A margem é curta, então imprevistos pesam. Quer simular quanto guardar por mês?")
        return (base_txt + f"Faltam {brl(abs(viab['folga_mensal']))} por mês, então vale revisar prazos ou valores. "
                "Quer simular alternativas?")

    alvo = None
    if "apartamento" in n or "entrada" in n or "imovel" in n:
        alvo = next((m for m in metas if not m["eh_reserva"]), None)
    elif "reserva" in n:
        alvo = next((m for m in metas if m["eh_reserva"]), None)
    if alvo:
        txt = (f"{alvo['meta']}: você está com {brl(alvo['atual'])} de {brl(alvo['alvo'])} "
               f"({pct(alvo['progresso_pct'])}) e faltam {brl(alvo['falta'])}. Até {nome_mes(alvo['prazo'])} "
               f"são {alvo['meses_restantes']} meses, o que dá {brl(alvo['aporte_mensal_necessario'])} por mês "
               "(fonte: perfil_investidor.json).")
        if alvo["premissa"]:
            txt += f" Premissa: {alvo['premissa']}."
        return txt + " Quer ver quanto você conseguiria guardar por mês?"

    linhas = [f"{m['meta']}: {pct(m['progresso_pct'])} concluída, faltam {brl(m['falta'])}, "
              f"{brl(m['aporte_mensal_necessario'])} por mês até {nome_mes(m['prazo'])}" for m in metas]
    return "Suas metas hoje: " + "; ".join(linhas) + ". Quer que eu veja se cabem no seu orçamento?"


def _txt_simulacao(base, data_ref, valor) -> str:
    sim = ft.simular_aporte(base, valor, data_ref)
    partes = []
    for r in sim["metas"]:
        if r["conclui_em"] is None:
            partes.append(f"{r['meta']} não fecha em prazo razoável")
        elif r["conclui_em"] == "já concluída":
            partes.append(f"{r['meta']} já está concluída")
        else:
            situ = "dentro do prazo" if r["no_prazo"] else f"fora do prazo ({nome_mes(r['prazo'])})"
            partes.append(f"{r['meta']} em {nome_mes(r['conclui_em'])} ({r['meses']} meses), {situ}")
    txt = f"Guardando {brl(valor)} por mês (reserva primeiro, depois as outras metas): " + "; ".join(partes) + "."
    if sim["acima_da_capacidade"]:
        txt += f" Atenção: esse valor passa da sua média de sobra ({brl(sim['capacidade_media'])})."
    return txt + " Quer testar outro valor?"


def _txt_recomendacao(base, n) -> str:
    comp = ft.produtos_compativeis(base)
    prods = {p["nome"]: p for p in base.produtos}

    def ficha(nm: str) -> str:
        p = prods[nm]
        return f"{nm} ({p['rentabilidade']}, aporte mínimo {brl(p['aporte_minimo'])}, risco {p['risco']})"

    reserva = "; ".join(ficha(nm) for nm in comp["para_reserva"][:2])
    txt = ("Não posso te dizer o que fazer, mas posso mostrar o que combina com o seu perfil. "
           f"Como você não aceita risco e a reserva precisa de resgate rápido, os compatíveis são: {reserva}")
    if "reserva" not in n and comp["para_metas_de_prazo_maior"]:
        txt += (f". Para metas de prazo maior, como a entrada do apartamento, também cabe "
                f"{ficha(comp['para_metas_de_prazo_maior'][0])}")
    return txt + (" (fonte: produtos_financeiros.json). Confira as condições vigentes antes de decidir. "
                  "Quer que eu explique a diferença entre eles?")


def _txt_produto(base, prod, n) -> str:
    comp = ft.produtos_compativeis(base)
    incompat = next((i for i in comp["incompativeis"] if i["nome"] == prod["nome"]), None)
    verbete = _verbete_do_produto(base, prod)
    explic = f" {verbete['definicao']}" if verbete else ""
    ficha = (f"{prod['nome']}: risco {prod['risco'] if prod['risco'] != 'medio' else 'médio'}, "
             f"rentabilidade {prod['rentabilidade']}, aporte mínimo {brl(prod['aporte_minimo'])}, "
             f"indicado para {_min(prod['indicado_para'])} (fonte: produtos_financeiros.json).")
    if incompat:
        return (f"{ficha}{explic} Esse produto não combina com o seu momento: {incompat['motivo']}. "
                "Por isso não o sugiro agora, mas posso te explicar como ele funciona. Ficou claro?")
    return f"{ficha}{explic} Combina com o seu perfil de risco baixo. Ficou claro?"


def _txt_comparacao(base, produtos) -> str:
    comp = ft.produtos_compativeis(base)
    incompat = {i["nome"] for i in comp["incompativeis"]}
    partes = []
    for p in produtos[:2]:
        risco = "médio" if p["risco"] == "medio" else p["risco"]
        partes.append(f"{p['nome']} tem risco {risco}, rende {p['rentabilidade']}, aporte mínimo "
                      f"{brl(p['aporte_minimo'])} e é indicado para {_min(p['indicado_para'])}")
    txt = "Comparando pelo catálogo: " + "; ".join(partes) + " (fonte: produtos_financeiros.json)."
    fora = [p["nome"] for p in produtos[:2] if p["nome"] in incompat]
    if fora:
        txt += f" Atenção: {', '.join(fora)} não combina com o seu perfil atual."
    return txt + " Quer que eu mostre qual se encaixa melhor na sua reserva?"


def _txt_glossario(base, verbetes) -> str:
    v = verbetes[0]
    txt = f"{v['termo']}: {v['definicao']}"
    return txt + " Ficou claro? Posso dar um exemplo com os seus números."


def _txt_nao_sei() -> str:
    return ("Não tenho essa informação: esse produto ou cotação não consta na minha base. "
            "Posso explicar os produtos que conheço, como o Tesouro Selic e o CDB Liquidez Diária. "
            "Quer começar por algum deles?")


def _txt_garantia() -> str:
    return ("Não posso garantir lucro em nenhum investimento: todo investimento tem algum tipo de risco, "
            "e risco maior significa também possibilidade de perda. O que posso fazer é te mostrar quais "
            "produtos combinam com o seu perfil e como cada um funciona. Quer ver?")


def _txt_padrao(base, data_ref) -> str:
    return ("Posso te ajudar com seus gastos por categoria, o andamento das suas metas, simulações de "
            "quanto guardar por mês e dúvidas sobre produtos financeiros. Sobre o que quer conversar?")


# ---------------------------------------------------------------------------
def responder_offline(base: BaseConhecimento, data_ref: str, mensagem: str) -> str:
    n = normalizar(mensagem)

    valor = extrair_valor_simulacao(mensagem)
    if valor:
        return _txt_simulacao(base, data_ref, valor)

    produto = _produto_mencionado(base, n)
    if RE_TICKER.search(n) or (
        re.search(r"quanto rende|rentabilidade", n) and re.search(r"\bproduto\b", n) and not produto
    ):
        return _txt_nao_sei()

    if re.search(r"garant", n) and re.search(r"lucro|rend|ganh|retorno", n):
        return _txt_garantia()

    mencionados = _produtos_mencionados(base, n)
    if len(mencionados) >= 2 and re.search(r"diferenca|compar|melhor|versus|\bvs\b|ou ", n):
        return _txt_comparacao(base, mencionados)

    if re.search(r"o que (e|sao)|explic|como funciona|significa|diferenca", n):
        verbetes = buscar_glossario(base, mensagem)
        if produto:
            return _txt_produto(base, produto, n)
        if verbetes:
            return _txt_glossario(base, verbetes)

    if produto:
        return _txt_produto(base, produto, n)

    if re.search(r"recomend|onde invest|onde devo|qual investimento|em que invest|onde aplic|devo invest|combinam", n):
        return _txt_recomendacao(base, n)

    if re.search(r"gast|categoria|sobrou|sobra|despesa", n):
        return _txt_gastos(base, n)

    if re.search(r"meta|reserva|apartamento|entrada|prazo|cabem|orcamento|falta|preciso guardar|guardar por mes", n):
        return _txt_metas(base, data_ref, n)

    verbetes = buscar_glossario(base, mensagem)
    if verbetes:
        return _txt_glossario(base, verbetes)

    return _txt_padrao(base, data_ref)
