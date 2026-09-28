"""Garante que a documentação não ficou defasada em relação ao código."""
from pathlib import Path

from prompts import SYSTEM_PROMPT

RAIZ = Path(__file__).resolve().parent.parent


def test_system_prompt_esta_documentado_na_integra():
    doc = (RAIZ / "docs" / "03-prompts.md").read_text(encoding="utf-8")
    assert SYSTEM_PROMPT.strip() in doc


def test_entregaveis_do_desafio_existem():
    for caminho in ["README.md", "docs/01-documentacao-agente.md", "docs/02-base-conhecimento.md",
                    "docs/03-prompts.md", "docs/04-metricas.md", "docs/05-pitch.md",
                    "data/transacoes.csv", "data/historico_atendimento.csv",
                    "data/perfil_investidor.json", "data/produtos_financeiros.json",
                    "src/app.py", "requirements.txt"]:
        assert (RAIZ / caminho).exists(), caminho
