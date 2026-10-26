"""Public API schemas.

Unknown-field handling (spec 6.1): request fields outside the supported set
are REJECTED with a 422 response in the standard error envelope with code
``unsupported_field`` (see the RequestValidationError handler in main.py) —
never silently ignored, because several of them would materially change
model behaviour.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

SUPPORTED_FIELDS = {
    "model",
    "messages",
    "temperature",
    "top_p",
    "max_tokens",
    "stream",
    "stop",
    "presence_penalty",
    "frequency_penalty",
    "seed",
    "user",
}


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: str = Field(pattern="^(system|user|assistant|tool)$")
    content: str = Field(min_length=0, max_length=100_000)
    name: str | None = None


class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: str = Field(min_length=1, max_length=200)
    messages: list[ChatMessage] = Field(min_length=1, max_length=200)
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    max_tokens: int | None = Field(default=None, ge=1, le=100_000)
    stream: bool = False
    stop: list[str] | str | None = None
    presence_penalty: float | None = Field(default=None, ge=-2, le=2)
    frequency_penalty: float | None = Field(default=None, ge=-2, le=2)
    seed: int | None = None
    user: str | None = Field(default=None, max_length=200)

    @field_validator("messages")
    @classmethod
    def _roles_present(cls, v):
        if not any(m.role in ("user", "system") for m in v):
            raise ValueError("at least one system or user message is required")
        return v

    def messages_as_dicts(self) -> list[dict]:
        return [m.model_dump(exclude_none=True) for m in self.messages]
