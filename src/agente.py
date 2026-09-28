"""Orquestrador do Fin: guardrail de entrada -> contexto -> LLM -> validação de saída."""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import config
from base_conhecimento import BaseConhecimento, carregar
from contexto import montar_contexto
from guardrails import checar_entrada, validar_saida
from llm import LLM, LLMIndisponivelError, criar_llm
from prompts import SYSTEM_PROMPT
from utils import numeros_no_texto

AVISO_NAO_VERIFICADO = (
    "\n\n> ⚠️ Alguns valores desta resposta não puderam ser confirmados nos dados do cliente. "
    "Confira antes de tomar qualquer decisão."
)
MENSAGEM_ERRO_LLM = (
    "Tive um problema para consultar o modelo de IA agora. Tente de novo em instantes "
    "ou troque o motor de IA na barra lateral."
)


@dataclass
class Resposta:
    texto: str
    bloqueado: bool = False
    motivo: str = ""
    contexto: str = ""
    validacao_ok: bool = True
    problemas: list[dict] = field(default_factory=list)
    tentativas: int = 0
    latencia_s: float = 0.0
    provider: str = ""
    erro: str = ""


class Agente:
    def __init__(self, base: BaseConhecimento | None = None, llm: LLM | None = None,
                 data_ref: str | None = None, provider: str | None = None):
        self.base = base or carregar()
        self.data_ref = data_ref or config.DATA_REFERENCIA
        self.llm = llm or criar_llm(provider, self.base, self.data_ref)

    def responder(self, mensagem: str, historico: list[dict] | None = None) -> Resposta:
        inicio = time.perf_counter()
        historico = [{"role": m["role"], "content": m["content"]} for m in (historico or [])]

        entrada = checar_entrada(mensagem)
        if entrada.bloqueado:
            return Resposta(texto=entrada.resposta, bloqueado=True, motivo=entrada.motivo,
                            latencia_s=time.perf_counter() - inicio, provider=self.llm.nome)

        contexto = montar_contexto(self.base, self.data_ref, mensagem)
        system = f"{SYSTEM_PROMPT}\n\nCONTEXTO\n{contexto}"
        turnos = historico[-config.MAX_TURNOS_HISTORICO * 2:]
        mensagens = [*turnos, {"role": "user", "content": mensagem}]

        texto_usuario = " ".join(m["content"] for m in mensagens if m["role"] == "user")
        permitidos = numeros_no_texto(contexto + " " + texto_usuario)

        try:
            texto = self.llm.gerar(system, mensagens)
            validacao = validar_saida(texto, permitidos)
            tentativas = 1

            while not validacao.ok and tentativas <= config.MAX_REESCRITAS:
                itens = "; ".join(_descrever(p) for p in validacao.problemas)
                correcao = (
                    "[Verificação automática] Sua resposta anterior tem problemas: "
                    f"{itens}. Reescreva usando APENAS valores presentes no contexto e sem "
                    "promessas de retorno (ou diga que não tem a informação). "
                    "Não mencione esta verificação."
                )
                texto = self.llm.gerar(system, [*mensagens, {"role": "assistant", "content": texto},
                                                {"role": "user", "content": correcao}])
                validacao = validar_saida(texto, permitidos)
                tentativas += 1
        except (LLMIndisponivelError, Exception) as e:  # noqa: BLE001 - erro de rede/API não deve derrubar o app
            return Resposta(texto=MENSAGEM_ERRO_LLM, contexto=contexto, erro=f"{type(e).__name__}: {e}",
                            latencia_s=time.perf_counter() - inicio, provider=self.llm.nome)

        if not validacao.ok:
            texto += AVISO_NAO_VERIFICADO

        return Resposta(
            texto=texto, contexto=contexto, validacao_ok=validacao.ok, problemas=validacao.problemas,
            tentativas=tentativas, latencia_s=time.perf_counter() - inicio, provider=self.llm.nome,
        )


def _descrever(problema: dict) -> str:
    tipo = problema["tipo"]
    if tipo == "valor_nao_rastreavel":
        return f"o valor R$ {problema['valor']:.2f} não consta nos dados"
    if tipo == "percentual_nao_rastreavel":
        return f"o percentual {problema['valor']}% não consta nos dados"
    return f"contém a promessa proibida '{problema['trecho']}'"
