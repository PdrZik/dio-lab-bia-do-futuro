"""Guardrails do Fin: filtro de entrada e validação de saída (anti-alucinação).

Entrada  -> bloqueia injeção de prompt, pedidos de dados sensíveis e assuntos fora do escopo
            ANTES de chamar o LLM (mais barato, mais rápido e não depende do modelo obedecer).
Saída    -> confere se todo valor em R$ e todo percentual citado na resposta é rastreável até
            os dados fornecidos e se o texto não contém promessas proibidas.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from utils import extrair_dinheiro_detalhado, extrair_percentuais_detalhado, normalizar

# ---------------------------------------------------------------------------
# Entrada
# ---------------------------------------------------------------------------
PADROES_INJECAO = [
    r"ignor\w* (todas? )?(as |suas |o |seus )?(instruc|regra|prompt|orientac)",
    r"desconsider\w* (todas? )?(as |suas )?(instruc|regra)",
    r"esque[cç]\w* (tudo|as regras|suas instruc|suas regras)",
    r"(mostr|revel|repit|imprim|exib)\w* (o |seu |suas |as )?(system prompt|prompt do sistema|prompt|instruc)",
    r"system prompt|prompt do sistema|suas instrucoes",
    r"voce (agora )?e (um|uma) (?!educador|copiloto)",
    r"finja (que )?(voce )?(e|ser)",
    r"modo (desenvolvedor|deus|dan)|jailbreak|ignore previous|ignore all",
]

PADROES_SENSIVEIS = [
    r"\bsenha\b", r"\bcvv\b", r"codigo de seguranca", r"numero do cartao", r"token de acesso",
    r"\bcpf d[eo]\b", r"chave pix d[eo]",
    r"(dados|extrato|saldo|conta|transacoes) (do|de|da) (outro|outra|cliente [a-z]\b|terceiro)",
    r"cliente [xyz]\b",
]

PADROES_FORA_DE_ESCOPO = [
    r"previsao do tempo", r"\bclima\b", r"vai chover", r"horoscopo", r"\bsigno\b",
    r"\bfutebol\b", r"resultado do jogo", r"campeonato",
    r"receita de (bolo|comida|pizza|macarrao)", r"\bpiada\b", r"\bpoema\b", r"\bmusica\b",
    r"\bfilme\b", r"\bserie\b", r"escreva (um )?(codigo|programa|script)",
    r"\btraduz\w*", r"capital d[aeo]s? ", r"\bpolitic[ao]\b", r"quem vai ganhar",
    r"dever de casa", r"tema de redacao",
]

RESPOSTA_INJECAO = (
    "Não posso alterar minhas regras nem compartilhar minhas instruções internas. "
    "Mas posso te ajudar com suas finanças: quer ver como estão suas metas ou seus gastos?"
)
RESPOSTA_SENSIVEL = (
    "Não tenho acesso a senhas nem a dados de outras pessoas e não posso compartilhar esse tipo "
    "de informação. Como posso ajudar com as suas próprias finanças?"
)
RESPOSTA_FORA_ESCOPO = (
    "Sou especializado em finanças pessoais e não consigo ajudar com esse assunto. "
    "Posso te ajudar com seus gastos, suas metas ou dúvidas sobre investimentos. Por onde quer começar?"
)


@dataclass
class ResultadoEntrada:
    bloqueado: bool
    motivo: str = ""
    resposta: str = ""


def _casa_algum(padroes: list[str], texto_normalizado: str) -> bool:
    return any(re.search(p, texto_normalizado) for p in padroes)


def checar_entrada(mensagem: str) -> ResultadoEntrada:
    texto = normalizar(mensagem)
    if _casa_algum(PADROES_INJECAO, texto):
        return ResultadoEntrada(True, "injecao_de_prompt", RESPOSTA_INJECAO)
    if _casa_algum(PADROES_SENSIVEIS, texto):
        return ResultadoEntrada(True, "dado_sensivel", RESPOSTA_SENSIVEL)
    if _casa_algum(PADROES_FORA_DE_ESCOPO, texto):
        return ResultadoEntrada(True, "fora_de_escopo", RESPOSTA_FORA_ESCOPO)
    return ResultadoEntrada(False)


# ---------------------------------------------------------------------------
# Saída
# ---------------------------------------------------------------------------
FRASES_PROIBIDAS = [
    "lucro garantido", "rendimento garantido", "retorno garantido", "ganho garantido",
    "sem nenhum risco", "sem risco algum", "risco zero", "nao ha risco",
    "voce deve investir", "recomendo que voce invista", "invista tudo", "compre agora",
]


@dataclass
class ResultadoSaida:
    ok: bool
    problemas: list[dict] = field(default_factory=list)


def _rastreavel(valor: float, casas: int, permitidos: set[float]) -> bool:
    """A tolerância depende de como o número foi escrito.

    - Com casas decimais ('R$ 570,00', '22,9%'): precisa bater exatamente (a 1 casa a mais).
    - Inteiro ('R$ 2.476', '80%'): aceita apenas arredondamento, ou seja, diferença < 0,5.
    Assim 'R$ 999,00' NÃO é aceito só porque existe 'R$ 1.000,00' no contexto.
    """
    tolerancia = 0.5 if casas == 0 else 0.5 * 10 ** -casas + 1e-9
    return any(abs(valor - p) < tolerancia for p in permitidos)


def validar_saida(resposta: str, numeros_permitidos: set[float]) -> ResultadoSaida:
    """Heurística de rastreabilidade: valores em R$ e % citados precisam existir no contexto."""
    problemas: list[dict] = []

    for valor, casas in extrair_dinheiro_detalhado(resposta):
        if valor != 0 and not _rastreavel(valor, casas, numeros_permitidos):
            problemas.append({"tipo": "valor_nao_rastreavel", "valor": valor})

    for valor, casas in extrair_percentuais_detalhado(resposta):
        if valor != 0 and not _rastreavel(valor, casas, numeros_permitidos):
            problemas.append({"tipo": "percentual_nao_rastreavel", "valor": valor})

    texto = normalizar(resposta)
    for frase in FRASES_PROIBIDAS:
        if frase in texto:
            problemas.append({"tipo": "promessa_proibida", "trecho": frase})

    return ResultadoSaida(ok=not problemas, problemas=problemas)
