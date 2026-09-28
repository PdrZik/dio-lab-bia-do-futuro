"""Funções utilitárias: formatação em reais, normalização de texto e extração de números."""
from __future__ import annotations

import re
import unicodedata

MESES_PT = {
    1: "jan", 2: "fev", 3: "mar", 4: "abr", 5: "mai", 6: "jun",
    7: "jul", 8: "ago", 9: "set", 10: "out", 11: "nov", 12: "dez",
}

ROTULOS_CATEGORIA = {
    "moradia": "Moradia",
    "alimentacao": "Alimentação",
    "transporte": "Transporte",
    "saude": "Saúde",
    "lazer": "Lazer",
    "receita": "Receita",
}


def brl(valor: float) -> str:
    """1380 -> 'R$ 1.380,00'."""
    texto = f"{valor:,.2f}"
    return "R$ " + texto.replace(",", "X").replace(".", ",").replace("X", ".")


def pct(valor: float) -> str:
    """55.4 -> '55,4%'."""
    return f"{valor:.1f}".replace(".", ",") + "%"


def nome_mes(periodo: str) -> str:
    """'2025-10' -> 'out/2025'."""
    ano, mes = periodo.split("-")[:2]
    return f"{MESES_PT[int(mes)]}/{ano}"


def rotulo_categoria(cat: str) -> str:
    return ROTULOS_CATEGORIA.get(cat, cat.capitalize())


def normalizar(texto: str) -> str:
    """Minúsculas e sem acentos, para comparações robustas."""
    sem_acento = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return sem_acento.lower().strip()


# ---------------------------------------------------------------------------
# Extração de números (usada na validação anti-alucinação)
# ---------------------------------------------------------------------------
_RE_DINHEIRO = re.compile(r"R\$\s*(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d{1,2}))?")
_RE_PERCENTUAL = re.compile(r"(\d+(?:[.,]\d+)?)\s*%")
_RE_TOKEN_NUM = re.compile(r"\d+(?:[.,]\d+)*")


def extrair_dinheiro_detalhado(texto: str) -> list[tuple[float, int]]:
    """Valores em R$ (formato brasileiro) e quantas casas decimais foram escritas.

    'R$ 570' -> (570.0, 0) | 'R$ 55,9' -> (55.9, 1) | 'R$ 1.380,00' -> (1380.0, 2)
    """
    valores = []
    for inteiro, centavos in _RE_DINHEIRO.findall(texto):
        valor = float(inteiro.replace(".", ""))
        if centavos:
            valor += float(centavos) / (10 ** len(centavos))
        valores.append((valor, len(centavos)))
    return valores


def extrair_dinheiro(texto: str) -> list[float]:
    return [v for v, _ in extrair_dinheiro_detalhado(texto)]


def extrair_percentuais_detalhado(texto: str) -> list[tuple[float, int]]:
    """'22,9%' -> (22.9, 1) | '80%' -> (80.0, 0)."""
    resultado = []
    for m in _RE_PERCENTUAL.findall(texto):
        casas = len(m.replace(",", ".").split(".")[1]) if re.search(r"[.,]", m) else 0
        resultado.append((float(m.replace(",", ".")), casas))
    return resultado


def extrair_percentuais(texto: str) -> list[float]:
    return [v for v, _ in extrair_percentuais_detalhado(texto)]


def numeros_no_texto(texto: str) -> set[float]:
    """Todos os números presentes em um texto (CSV, JSON, formato BR ou US).

    Para tokens ambíguos como '1.380' geramos as duas leituras (1380 e 1.38); assim o
    conjunto de valores 'permitidos' nunca rejeita um número legítimo do contexto.
    """
    encontrados: set[float] = set()
    for token in _RE_TOKEN_NUM.findall(texto):
        candidatos = []
        if "." in token and "," in token:
            candidatos.append(token.replace(".", "").replace(",", "."))
        elif "," in token:
            candidatos.append(token.replace(",", "."))
            candidatos.append(token.replace(",", ""))
        elif "." in token:
            if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", token):
                candidatos.append(token.replace(".", ""))
            if token.count(".") == 1:
                candidatos.append(token)
        else:
            candidatos.append(token)
        for c in candidatos:
            try:
                encontrados.add(float(c))
            except ValueError:
                continue
    return encontrados
