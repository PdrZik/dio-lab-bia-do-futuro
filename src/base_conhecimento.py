"""Carga e validação da base de conhecimento (pasta data/)."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from config import DATA_DIR
from utils import normalizar

COLUNAS_TRANSACOES = {"data", "descricao", "categoria", "valor", "tipo"}
COLUNAS_HISTORICO = {"data", "canal", "tema", "resumo", "resolvido"}
CHAVES_PERFIL = {
    "nome", "idade", "renda_mensal", "perfil_investidor", "objetivo_principal",
    "patrimonio_total", "reserva_emergencia_atual", "aceita_risco", "metas",
}


class BaseInvalidaError(ValueError):
    """Arquivo da base de conhecimento ausente ou com formato inesperado."""


@dataclass
class BaseConhecimento:
    perfil: dict
    transacoes: pd.DataFrame
    historico: pd.DataFrame
    produtos: list[dict]
    glossario: list[dict]


def _ler_csv(caminho: Path, colunas: set[str]) -> pd.DataFrame:
    if not caminho.exists():
        raise BaseInvalidaError(f"Arquivo não encontrado: {caminho}")
    df = pd.read_csv(caminho)
    faltando = colunas - set(df.columns)
    if faltando:
        raise BaseInvalidaError(f"{caminho.name}: colunas ausentes {sorted(faltando)}")
    return df


def _ler_json(caminho: Path):
    if not caminho.exists():
        raise BaseInvalidaError(f"Arquivo não encontrado: {caminho}")
    with open(caminho, encoding="utf-8") as f:
        return json.load(f)


def carregar(data_dir: Path | str = DATA_DIR) -> BaseConhecimento:
    data_dir = Path(data_dir)

    perfil = _ler_json(data_dir / "perfil_investidor.json")
    faltando = CHAVES_PERFIL - set(perfil)
    if faltando:
        raise BaseInvalidaError(f"perfil_investidor.json: chaves ausentes {sorted(faltando)}")

    transacoes = _ler_csv(data_dir / "transacoes.csv", COLUNAS_TRANSACOES)
    transacoes["data"] = pd.to_datetime(transacoes["data"])
    transacoes["valor"] = transacoes["valor"].astype(float)
    transacoes["mes"] = transacoes["data"].dt.strftime("%Y-%m")

    historico = _ler_csv(data_dir / "historico_atendimento.csv", COLUNAS_HISTORICO)
    historico["data"] = pd.to_datetime(historico["data"])
    historico = historico.sort_values("data").reset_index(drop=True)

    produtos = _ler_json(data_dir / "produtos_financeiros.json")

    caminho_glossario = data_dir / "glossario_financeiro.json"
    glossario = _ler_json(caminho_glossario) if caminho_glossario.exists() else []

    return BaseConhecimento(perfil, transacoes, historico, produtos, glossario)


def buscar_glossario(base: BaseConhecimento, texto: str, limite: int = 3) -> list[dict]:
    """Recupera verbetes cujo termo/sinônimo aparece no texto (busca lexical simples).

    Os resultados são ordenados pelo tamanho da chave casada: 'tesouro selic' (mais
    específico) vem antes de 'selic'.
    """
    alvo = normalizar(texto)
    achados: list[tuple[int, dict]] = []
    for verbete in base.glossario:
        melhor = 0
        for chave in [verbete["termo"], *verbete.get("sinonimos", [])]:
            chave_norm = normalizar(chave)
            if re.search(r"\b" + re.escape(chave_norm) + r"\b", alvo):
                melhor = max(melhor, len(chave_norm))
        if melhor:
            achados.append((melhor, verbete))
    achados.sort(key=lambda t: -t[0])
    return [v for _, v in achados[:limite]]
