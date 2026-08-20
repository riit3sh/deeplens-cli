"""Provider-neutral structured-output client for future LLM-assisted roles.

This module deliberately owns API compatibility details so research business logic
does not depend on a particular model vendor.
"""

from __future__ import annotations

from typing import Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class StructuredLLM(Protocol):
    async def complete(self, *, system: str, prompt: str, response_model: type[T]) -> T: ...


class UnconfiguredLLM:
    """Explicit failure mode that keeps unavailable credentials out of logs."""

    async def complete(self, *, system: str, prompt: str, response_model: type[T]) -> T:
        del system, prompt, response_model
        raise RuntimeError(
            "No LLM provider is configured. Set OPENAI_API_KEY and OPENAI_BASE_URL, "
            "or inject a StructuredLLM implementation."
        )


class OpenAILLM:
    def __init__(self, settings):
        import openai
        self.client = openai.AsyncClient(
            api_key=settings.openai_api_key or "mock",
            base_url=settings.openai_base_url
        )
        self.model = settings.deeplens_model or "gpt-4o-mini"

    async def complete(self, *, system: str, prompt: str, response_model: type[T]) -> T:
        # We prompt the model to return raw JSON matching the schema
        # (This is more universally supported by OpenAI-compatible backends like DeepInfra than structured outputs API)
        import json
        schema = response_model.model_json_schema()
        system_with_schema = (
            f"{system}\n\n"
            f"You MUST return ONLY a raw valid JSON object. Do not include markdown formatting like ```json. "
            f"The JSON object must strictly match this schema:\n{json.dumps(schema, indent=2)}"
        )
        
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_with_schema},
                {"role": "user", "content": prompt}
            ],
            temperature=0.0
        )
        content = response.choices[0].message.content or "{}"
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        return response_model.model_validate_json(content.strip())

