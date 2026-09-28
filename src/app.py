"""Interface Streamlit do Fin — Copiloto Financeiro Proativo.

Executar a partir da raiz do projeto:  streamlit run src/app.py
"""
from __future__ import annotations

import streamlit as st

import config
import ferramentas as ft
from agente import Agente
from base_conhecimento import BaseInvalidaError, carregar
from llm import LLMIndisponivelError, PROVEDORES
from utils import brl, nome_mes, pct

st.set_page_config(page_title="Fin • Copiloto Financeiro", page_icon="🧭", layout="wide")

ICONES = {"positivo": "✅", "atencao": "⚠️", "info": "💡"}
PERGUNTAS_RAPIDAS = [
    "Minhas metas cabem no meu orçamento?",
    "E se eu guardar R$ 2.000 por mês?",
    "Onde estou gastando mais?",
    "Onde posso colocar minha reserva?",
]


@st.cache_resource(show_spinner=False)
def carregar_base():
    return carregar()


def criar_agente(provider: str) -> Agente:
    return Agente(base=carregar_base(), data_ref=config.DATA_REFERENCIA, provider=provider)


# ------------------------------------------------------------------ dados
try:
    base = carregar_base()
except BaseInvalidaError as e:
    st.error(f"Não consegui carregar a base de conhecimento: {e}")
    st.stop()

data_ref = config.DATA_REFERENCIA
metas = ft.progresso_metas(base, data_ref)
insights = ft.insights_proativos(base, data_ref)
resumo = ft.resumo_mensal(base)
ultimo = ft.ultimo_mes(base)

# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.title("🧭 Fin")
    st.caption("Copiloto financeiro proativo")

    st.subheader("Cliente (dados fictícios)")
    p = base.perfil
    st.markdown(f"**{p['nome']}**, {p['idade']} anos  \n{p['profissao']}")
    st.markdown(f"Perfil: **{p['perfil_investidor']}** · Aceita risco: **{'sim' if p['aceita_risco'] else 'não'}**")
    c1, c2 = st.columns(2)
    c1.metric("Renda", brl(p["renda_mensal"]))
    c2.metric(f"Sobra {nome_mes(ultimo)}", brl(resumo[ultimo]["saldo"]))

    st.subheader("Metas")
    for m in metas:
        st.markdown(f"**{m['meta']}**")
        st.progress(min(m["progresso_pct"] / 100, 1.0))
        st.caption(f"{brl(m['atual'])} de {brl(m['alvo'])} · {pct(m['progresso_pct'])} · prazo {nome_mes(m['prazo'])}")

    st.subheader("Motor de IA")
    padrao = config.provider_padrao()
    provider = st.selectbox("Provedor", PROVEDORES, index=PROVEDORES.index(padrao) if padrao in PROVEDORES else 3,
                            help="Configure as chaves no arquivo .env. 'offline' funciona sem internet.")
    if st.button("🗑️ Limpar conversa", use_container_width=True):
        st.session_state.mensagens = []
        st.rerun()
    st.caption("O Fin não substitui um profissional certificado e não faz recomendação de investimento regulada.")

# ------------------------------------------------------------------ agente
chave_agente = f"agente_{provider}"
if chave_agente not in st.session_state:
    try:
        st.session_state[chave_agente] = criar_agente(provider)
    except LLMIndisponivelError as e:
        st.sidebar.error(f"{e} Usando o modo offline.")
        provider = "offline"
        chave_agente = "agente_offline"
        if chave_agente not in st.session_state:
            st.session_state[chave_agente] = criar_agente("offline")
agente: Agente = st.session_state[chave_agente]

if "mensagens" not in st.session_state:
    st.session_state.mensagens = []

# ------------------------------------------------------------------ tela principal
st.title(f"Olá, {p['nome'].split()[0]}! 👋")
st.markdown("Sou o **Fin**. Antes de você perguntar, separei o que merece a sua atenção hoje:")

cols = st.columns(min(len(insights), 3))
for i, ins in enumerate(insights[:6]):
    with cols[i % len(cols)]:
        with st.container(border=True):
            st.markdown(f"{ICONES[ins['severidade']]} **{ins['titulo']}**")
            st.write(ins["texto"])
            if st.button("Perguntar ao Fin", key=f"ins_{ins['id']}"):
                st.session_state.pendente = ins["pergunta_sugerida"]

st.divider()
st.subheader("Converse comigo")

atalhos = st.columns(len(PERGUNTAS_RAPIDAS))
for col, pergunta in zip(atalhos, PERGUNTAS_RAPIDAS):
    if col.button(pergunta, use_container_width=True):
        st.session_state.pendente = pergunta

for m in st.session_state.mensagens:
    with st.chat_message(m["role"], avatar="🧭" if m["role"] == "assistant" else None):
        st.markdown(m["content"])
        meta = m.get("meta")
        if meta:
            with st.expander("🔍 Como o Fin chegou nessa resposta"):
                if meta["bloqueado"]:
                    st.info(f"Bloqueada pelo guardrail de entrada: **{meta['motivo']}** (o LLM nem foi chamado).")
                else:
                    ok = "✅ todos os valores foram rastreados nos dados" if meta["validacao_ok"] \
                        else f"⚠️ problemas: {meta['problemas']}"
                    st.write(f"**Validação anti-alucinação:** {ok}")
                    st.write(f"**Motor:** {meta['provider']} · **Tentativas:** {meta['tentativas']} · "
                             f"**Latência:** {meta['latencia_s']:.2f}s")
                    if meta.get("erro"):
                        st.error(meta["erro"])
                    st.caption("Contexto enviado ao modelo:")
                    st.code(meta["contexto"], language="text")

entrada = st.chat_input("Pergunte sobre gastos, metas ou investimentos...")
pergunta = entrada or st.session_state.pop("pendente", None)

if pergunta:
    historico = [{"role": m["role"], "content": m["content"]} for m in st.session_state.mensagens]
    st.session_state.mensagens.append({"role": "user", "content": pergunta})
    with st.spinner("Fin está analisando seus dados..."):
        resp = agente.responder(pergunta, historico)
    st.session_state.mensagens.append({
        "role": "assistant", "content": resp.texto,
        "meta": {"bloqueado": resp.bloqueado, "motivo": resp.motivo, "validacao_ok": resp.validacao_ok,
                 "problemas": resp.problemas, "provider": resp.provider, "tentativas": resp.tentativas,
                 "latencia_s": resp.latencia_s, "contexto": resp.contexto, "erro": resp.erro},
    })
    st.rerun()
