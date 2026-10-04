import base64
import logging
import time
from typing import Any

import openai
from openai import OpenAI
from pydantic import ValidationError

from app.features.extraction.providers.base import (
    LLMProvider,
    ProviderPermanentError,
    ProviderTransientError,
)
from app.features.extraction.providers.prompts import (
    SYSTEM_PROMPT,
    TEXT_USER_PROMPT,
    VISION_USER_PROMPT,
)
from app.features.extraction.schemas import ExtractedInvoice

logger = logging.getLogger("app.extraction.openai")


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(
        self,
        api_key: str,
        text_model: str,
        vision_model: str,
        timeout_seconds: float = 60.0,
        client: OpenAI | None = None,
    ) -> None:
        self.text_model = text_model
        self.vision_model = vision_model
        self._client = client or OpenAI(api_key=api_key, timeout=timeout_seconds, max_retries=2)

    def extract_from_text(self, text: str) -> ExtractedInvoice:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": TEXT_USER_PROMPT.format(text=text)},
        ]
        return self._call(self.text_model, messages)

    def extract_from_images(self, images: list[bytes]) -> ExtractedInvoice:
        content: list[dict[str, Any]] = [{"type": "text", "text": VISION_USER_PROMPT}]
        for image in images:
            encoded = base64.b64encode(image).decode()
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{encoded}", "detail": "high"},
                }
            )
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ]
        return self._call(self.vision_model, messages)

    def _call(self, model: str, messages: list[dict[str, Any]]) -> ExtractedInvoice:
        started = time.perf_counter()
        try:
            completion = self._client.chat.completions.parse(
                model=model,
                messages=messages,  # type: ignore[arg-type]
                response_format=ExtractedInvoice,
                temperature=0,
            )
        except (
            openai.APITimeoutError,
            openai.APIConnectionError,
            openai.RateLimitError,
            openai.InternalServerError,
        ) as exc:
            logger.warning("openai transient error", extra={"error": type(exc).__name__})
            raise ProviderTransientError(f"AI service unavailable: {type(exc).__name__}") from exc
        except openai.APIStatusError as exc:
            if exc.status_code >= 500 or exc.status_code == 429:
                raise ProviderTransientError(f"AI service error {exc.status_code}") from exc
            raise ProviderPermanentError(
                f"AI service rejected the request ({exc.status_code})"
            ) from exc
        except (
            ValidationError,
            openai.LengthFinishReasonError,
            openai.ContentFilterFinishReasonError,
        ) as exc:
            raise ProviderPermanentError("AI service returned an unusable response") from exc

        message = completion.choices[0].message
        if message.refusal or message.parsed is None:
            raise ProviderPermanentError("AI service could not read this invoice")
        usage = completion.usage
        logger.info(
            "openai extraction call",
            extra={
                "model": model,
                "duration_ms": round((time.perf_counter() - started) * 1000),
                "prompt_tokens": usage.prompt_tokens if usage else None,
                "completion_tokens": usage.completion_tokens if usage else None,
            },
        )
        return message.parsed
