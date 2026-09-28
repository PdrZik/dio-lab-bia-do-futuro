"""Configurações centrais do Fin (lidas de variáveis de ambiente / arquivo .env)."""
from __future__ import annotations

import os
from pathlib import Path

try:  # python-dotenv é opcional: sem ele, usamos apenas variáveis de ambiente
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

RAIZ = Path(__file__).resolve().parent.parent
if load_dotenv:
    load_dotenv(RAIZ / ".env")

DATA_DIR = Path(os.getenv("DATA_DIR", RAIZ / "data"))

# Os dados mockados vão até out/2025. Fixamos a "data de hoje" nos cálculos para que
# prazos e metas façam sentido (e os testes sejam reproduzíveis).
DATA_REFERENCIA = os.getenv("DATA_REFERENCIA", "2025-11-01")

# Provedores suportados: anthropic | openai | ollama | offline
def provider_padrao() -> str:
    explicito = os.getenv("LLM_PROVIDER")
    if explicito:
        return explicito.lower()
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    return "offline"


ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gpt-oss")

MAX_TOKENS = int(os.getenv("MAX_TOKENS", "700"))
MAX_TURNOS_HISTORICO = int(os.getenv("MAX_TURNOS_HISTORICO", "6"))
MAX_REESCRITAS = int(os.getenv("MAX_REESCRITAS", "1"))
