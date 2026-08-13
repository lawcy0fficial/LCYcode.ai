"""
schema.py
Validates key.json's shape at startup so a typo or missing field
fails fast with a clear message instead of a confusing KeyError deep
inside a provider call three stages into a run.
"""
from typing import List, Optional

from pydantic import BaseModel, ValidationError, Field


class OpenRouterConfig(BaseModel):
    keys: List[str] = Field(default_factory=list)
    models: List[str] = Field(default_factory=list)


class SimpleProviderConfig(BaseModel):
    keys: List[str] = Field(default_factory=list)
    model: Optional[str] = None


class OllamaConfig(BaseModel):
    host: str = "http://127.0.0.1:11434"
    model: str = "deepseek-coder:1.3b"
    enabled: bool = True
    offline_only: bool = False
    auto_pull: bool = True


class RoutingConfig(BaseModel):
    order: List[str] = Field(default_factory=lambda: ["ollama", "openrouter", "deepseek", "grok"])
    max_iterations: int = 40
    tool_timeout_seconds: int = 60
    auto_continue: bool = True
    max_total_iterations: int = 1000


class KeyConfig(BaseModel):
    openrouter: OpenRouterConfig = Field(default_factory=OpenRouterConfig)
    grok: SimpleProviderConfig = Field(default_factory=SimpleProviderConfig)
    deepseek: SimpleProviderConfig = Field(default_factory=SimpleProviderConfig)
    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    routing: RoutingConfig = Field(default_factory=RoutingConfig)


def validate_config(raw: dict) -> KeyConfig:
    try:
        return KeyConfig(**raw)
    except ValidationError as e:
        raise ValueError(
            "key.json failed validation — check its shape against key.demo.json:\n" + str(e)
        ) from e
