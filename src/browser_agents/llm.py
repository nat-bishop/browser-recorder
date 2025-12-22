"""LLM factory for local Ollama models.

Uses ChatOpenAI pointed at Ollama's /v1 endpoint instead of ChatOllama.
This provides more reliable tool calling because:
1. ChatOpenAI's tool handling is more battle-tested
2. Ollama's OpenAI-compatible endpoint has better tool message formatting
3. Avoids ChatOllama's tool_call_id serialization bugs with Qwen/Llama models

Pattern from: ../ai-agents/src/core/llm.py
"""

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from browser_agents.config import settings


def get_llm(*, temperature: float = 0.0, **kwargs: Any) -> BaseChatModel:
    """Get an LLM instance configured for local Ollama.

    Args:
        temperature: Model temperature (0.0 = deterministic).
        **kwargs: Additional arguments passed to the model constructor.

    Returns:
        A LangChain chat model instance.

    Examples:
        >>> llm = get_llm()
        >>> llm = get_llm(temperature=0.7)
    """
    # Ollama exposes OpenAI-compatible API at /v1
    base_url = str(settings.ollama_url).rstrip("/") + "/v1"

    return ChatOpenAI(
        model=settings.local_model,
        base_url=base_url,
        api_key=SecretStr("ollama"),  # Required by ChatOpenAI but ignored by Ollama
        temperature=temperature,
        **kwargs,
    )


def get_structured_llm(
    schema: type,
    temperature: float = 0.0,
    **kwargs: Any,
) -> Any:
    """Get LLM configured for structured Pydantic output.

    Uses LangChain's with_structured_output() which leverages tool calling
    to guarantee output matches the Pydantic schema.

    Args:
        schema: Pydantic model class for output validation.
        temperature: Model temperature (0.0 = deterministic).
        **kwargs: Additional arguments for the LLM.

    Returns:
        A Runnable that outputs instances of `schema` when invoked.

    Examples:
        >>> from browser_agents.models import ActionDefinition
        >>> llm = get_structured_llm(ActionDefinition)
        >>> result = await llm.ainvoke(messages)  # Returns ActionDefinition
    """
    return get_llm(temperature=temperature, **kwargs).with_structured_output(schema)
