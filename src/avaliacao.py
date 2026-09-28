"""Executa os cenários de teste do desafio (etapa 5) e gera um relatório em Markdown.

Uso (a partir da raiz do projeto):
    python src/avaliacao.py                      # usa o provedor padrão do .env
    python src/avaliacao.py --provider offline   # regras determinísticas (sem API)
    python src/avaliacao.py --provider anthropic # LLM real (requer ANTHROPIC_API_KEY)
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
from datetime import datetime

import config
from agente import Agente
from utils import normalizar

CENARIOS = config.RAIZ / "tests" / "cenarios.json"
NOMES = {"assertividade": "Assertividade", "seguranca": "Segurança", "coerencia": "Coerência"}


def avaliar(cenario: dict, texto: str) -> tuple[bool, list[str]]:
    falhas = []
    alvo = normalizar(texto)

    for termo in cenario.get("deve_conter_todos", []):
        if normalizar(termo) not in alvo:
            falhas.append(f"faltou '{termo}'")

    algum = cenario.get("deve_conter_algum")
    if algum and not any(normalizar(t) in alvo for t in algum):
        falhas.append(f"não contém nenhum de {algum}")

    for termo in cenario.get("nao_deve_conter", []):
        if normalizar(termo) in alvo:
            falhas.append(f"não deveria conter '{termo}'")

    for padrao in cenario.get("nao_deve_conter_regex", []):
        if re.search(padrao, texto, flags=re.IGNORECASE):
            falhas.append(f"casou padrão proibido /{padrao}/")

    return (not falhas, falhas)


def executar(provider: str) -> dict:
    agente = Agente(provider=provider)
    cenarios = json.loads(CENARIOS.read_text(encoding="utf-8"))
    linhas, por_metrica, latencias = [], {}, []
    validacao_ok = 0

    for c in cenarios:
        r = agente.responder(c["pergunta"])
        passou, falhas = avaliar(c, r.texto)
        por_metrica.setdefault(c["metrica"], []).append(passou)
        latencias.append(r.latencia_s)
        validacao_ok += int(r.validacao_ok)
        linhas.append({"id": c["id"], "metrica": c["metrica"], "pergunta": c["pergunta"], "esperado": c["esperado"],
                       "resposta": r.texto, "passou": passou, "falhas": falhas, "bloqueado": r.bloqueado,
                       "validacao_ok": r.validacao_ok, "tentativas": r.tentativas, "latencia_s": r.latencia_s})

    return {"provider": agente.llm.nome, "linhas": linhas, "por_metrica": por_metrica,
            "latencia_media": statistics.mean(latencias), "latencia_max": max(latencias),
            "validacao_ok": validacao_ok, "total": len(cenarios)}


def relatorio(res: dict) -> str:
    out = [f"# Resultado dos testes estruturados\n",
           f"- **Motor:** `{res['provider']}`",
           f"- **Executado em:** {datetime.now():%d/%m/%Y %H:%M}",
           f"- **Cenários:** {res['total']} | **Respostas com valores 100% rastreáveis:** {res['validacao_ok']}/{res['total']}",
           f"- **Latência média:** {res['latencia_media']:.2f}s | **máxima:** {res['latencia_max']:.2f}s\n",
           "## Placar por métrica\n", "| Métrica | Aprovados | Taxa |", "|---|---|---|"]
    for chave, nome in NOMES.items():
        vals = res["por_metrica"].get(chave, [])
        if vals:
            out.append(f"| {nome} | {sum(vals)}/{len(vals)} | {sum(vals) / len(vals):.0%} |")
    out += ["", "## Detalhe por cenário\n", "| ID | Métrica | Pergunta | Resultado | Observação |", "|---|---|---|---|---|"]
    for l in res["linhas"]:
        obs = "; ".join(l["falhas"]) if l["falhas"] else ("bloqueado pelo guardrail" if l["bloqueado"] else "")
        out.append(f"| {l['id']} | {NOMES[l['metrica']]} | {l['pergunta']} | {'✅' if l['passou'] else '❌'} | {obs} |")
    out += ["", "## Respostas obtidas\n"]
    for l in res["linhas"]:
        out += [f"**{l['id']} — {l['pergunta']}**", f"> Esperado: {l['esperado']}", "", f"{l['resposta']}", ""]
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default=None)
    ap.add_argument("--saida", default=None, help="Caminho do relatório .md (padrão: docs/resultados_<provider>.md)")
    args = ap.parse_args()

    res = executar(args.provider or config.provider_padrao())
    md = relatorio(res)
    nome = re.sub(r"[^a-z0-9]+", "_", res["provider"].split(" ")[0].split(":")[0].lower())
    destino = args.saida or (config.RAIZ / "docs" / f"resultados_{nome}.md")
    open(destino, "w", encoding="utf-8").write(md)

    print(f"Motor: {res['provider']}")
    for chave, nome_m in NOMES.items():
        vals = res["por_metrica"].get(chave, [])
        if vals:
            print(f"  {nome_m:<14} {sum(vals)}/{len(vals)}  ({sum(vals) / len(vals):.0%})")
    reprovados = [l["id"] for l in res["linhas"] if not l["passou"]]
    print(f"  Reprovados: {reprovados or 'nenhum'}")
    print(f"Relatório salvo em: {destino}")


if __name__ == "__main__":
    main()
