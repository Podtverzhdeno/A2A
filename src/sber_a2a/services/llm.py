import asyncio
from typing import Any

from sber_a2a.config import Settings
from sber_a2a.domain.models import Comparison, ParsedIntentDraft


class LLMUnavailableError(RuntimeError):
    pass


class LanguageModelService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._model: Any | None = None

    @property
    def enabled(self) -> bool:
        return self._settings.llm_ready

    @property
    def provider(self) -> str:
        return self._settings.llm_provider

    def _get_model(self) -> Any:
        if not self.enabled:
            raise LLMUnavailableError(
                "LLM provider is disabled or incomplete. Configure LLM_PROVIDER "
                "and provider credentials/model in .env."
            )
        if self._model is None:
            if self._settings.llm_provider == "openrouter":
                from langchain_openrouter import ChatOpenRouter

                self._model = ChatOpenRouter(
                    model=self._settings.openrouter_model,
                    api_key=self._settings.openrouter_api_key.get_secret_value(),
                    temperature=0,
                    max_tokens=800,
                    max_retries=2,
                    app_url=self._settings.openrouter_app_url,
                    app_title=self._settings.openrouter_app_title,
                )
            elif self._settings.llm_provider == "gigachat":
                from langchain_gigachat.chat_models import GigaChat

                credentials = (
                    self._settings.gigachat_credentials.get_secret_value()
                    if self._settings.gigachat_credentials
                    else None
                )
                access_token = (
                    self._settings.gigachat_access_token.get_secret_value()
                    if self._settings.gigachat_access_token
                    else None
                )
                self._model = GigaChat(
                    credentials=credentials,
                    access_token=access_token,
                    model=self._settings.gigachat_model,
                    scope=self._settings.gigachat_scope,
                    base_url=self._settings.gigachat_base_url,
                    ca_bundle_file=self._settings.gigachat_ca_bundle_file,
                    verify_ssl_certs=self._settings.gigachat_verify_ssl_certs,
                    temperature=0,
                    max_tokens=800,
                    max_retries=2,
                )
            else:
                raise LLMUnavailableError("Unsupported LLM provider")
        return self._model

    async def parse_intent(self, text: str) -> ParsedIntentDraft:
        model = self._get_model().with_structured_output(ParsedIntentDraft)
        return await model.ainvoke(
            [
                (
                    "system",
                    "Извлеки только явно указанные параметры B2B-закупки. "
                    "Не выдумывай SKU, бюджет, город или срок. "
                    "Категория по умолчанию mro.standardized.",
                ),
                ("human", text),
            ]
        )

    async def explain_comparison(self, comparison: Comparison) -> str:
        if not self.enabled:
            return comparison.explanation
        compact = [
            {
                "supplier": item.quote.supplier_name,
                "eligible": item.eligible,
                "reasons": item.rejection_reasons,
                "total_cost": str(item.quote.total_cost),
                "delivery_days": item.quote.delivery_days,
                "warranty_months": item.quote.warranty_months,
                "score": str(item.total_score) if item.total_score is not None else None,
            }
            for item in comparison.evaluated_quotes
        ]
        try:
            async with asyncio.timeout(8):
                response = await self._get_model().ainvoke(
                    [
                        (
                            "system",
                            "Кратко объясни корпоративному закупщику результат "
                            "сравнения. Не меняй рейтинг и числа. Укажи, что "
                            "окончательное решение требует подтверждения человеком.",
                        ),
                        ("human", str(compact)),
                    ]
                )
        except Exception:
            return comparison.explanation
        content = response.content
        if isinstance(content, str):
            return content
        return " ".join(
            str(block.get("text", ""))
            for block in content
            if isinstance(block, dict)
        ).strip() or comparison.explanation
