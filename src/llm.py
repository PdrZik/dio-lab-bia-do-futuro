"""Camada de acesso ao LLM. Troque de provedor mudando apenas LLM_PROVIDER no .env."""
from __future__ import annotations

from typing import Protocol

import requests

import config


class LLM(Protocol):
    nome: str

    def gerar(self, system: str, mensagens: list[dict]) -> str: ...


class LLMIndisponivelError(RuntimeError):
    """Provedor mal configurado (ex.: chave ausente) ou inacessível."""


class AnthropicLLM:
    def __init__(self, modelo: str | None = None):
        import os

        if not os.getenv("ANTHROPIC_API_KEY"):
            raise LLMIndisponivelError("Defina ANTHROPIC_API_KEY no arquivo .env.")
        try:
            import anthropic
        except ImportError as e:  # pragma: no cover
            raise LLMIndisponivelError("Instale o pacote: pip install anthropic") from e
        self.modelo = modelo or config.ANTHROPIC_MODEL
        self.nome = f"anthropic:{self.modelo}"
        self._client = anthropic.Anthropic()

    def gerar(self, system: str, mensagens: list[dict]) -> str:
        resp = self._client.messages.create(
            model=self.modelo,
            max_tokens=config.MAX_TOKENS,
            system=system,
            messages=mensagens,
        )
        return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()


class OpenAILLM:
    def __init__(self, modelo: str | None = None):
        import os

        self._key = os.getenv("OPENAI_API_KEY")
        if not self._key:
            raise LLMIndisponivelError("Defina OPENAI_API_KEY no arquivo .env.")
        self.modelo = modelo or config.OPENAI_MODEL
        self.nome = f"openai:{self.modelo}"

    def gerar(self, system: str, mensagens: list[dict]) -> str:
        r = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {self._key}"},
            json={
                "model": self.modelo,
                "max_tokens": config.MAX_TOKENS,
                "messages": [{"role": "system", "content": system}, *mensagens],
            },
            timeout=60,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()


class OllamaLLM:
    """Modelo local (100% privado). Requer `ollama serve` e `ollama pull <modelo>`."""

    def __init__(self, modelo: str | None = None):
        self.modelo = modelo or config.OLLAMA_MODEL
        self.nome = f"ollama:{self.modelo}"

    def gerar(self, system: str, mensagens: list[dict]) -> str:
        try:
            r = requests.post(
                f"{config.OLLAMA_URL}/api/chat",
                json={
                    "model": self.modelo,
                    "stream": False,
                    "messages": [{"role": "system", "content": system}, *mensagens],
                },
                timeout=180,
            )
            r.raise_for_status()
        except requests.ConnectionError as e:
            raise LLMIndisponivelError(
                f"Não consegui conectar ao Ollama em {config.OLLAMA_URL}. Execute `ollama serve`."
            ) from e
        return r.json()["message"]["content"].strip()


PROVEDORES = ("anthropic", "openai", "ollama", "offline")


def criar_llm(provider: str | None = None, base=None, data_ref: str | None = None) -> LLM:
    provider = (provider or config.provider_padrao()).lower()
    if provider == "anthropic":
        return AnthropicLLM()
    if provider == "openai":
        return OpenAILLM()
    if provider == "ollama":
        return OllamaLLM()
    if provider == "offline":
        from offline import OfflineLLM

        return OfflineLLM(base, data_ref)
    raise LLMIndisponivelError(f"Provedor desconhecido: {provider}. Use um destes: {PROVEDORES}")
