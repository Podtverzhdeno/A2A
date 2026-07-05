from sber_a2a.config import Settings
from sber_a2a.services.llm import LanguageModelService


def test_llm_is_disabled_without_provider_configuration() -> None:
    settings = Settings(llm_provider="disabled", _env_file=None)

    assert settings.llm_ready is False
    assert LanguageModelService(settings).enabled is False


def test_openrouter_requires_model_from_environment() -> None:
    incomplete = Settings(
        llm_provider="openrouter",
        openrouter_api_key="secret",
        openrouter_model=None,
        _env_file=None,
    )
    complete = incomplete.model_copy(
        update={"openrouter_model": "provider/model-from-env"}
    )

    assert incomplete.llm_ready is False
    assert complete.llm_ready is True


def test_gigachat_provider_can_be_constructed_from_settings() -> None:
    settings = Settings(
        llm_provider="gigachat",
        gigachat_credentials="authorization-key",
        gigachat_model="model-from-env",
        _env_file=None,
    )
    service = LanguageModelService(settings)

    assert service.enabled is True
    assert service.provider == "gigachat"
    assert service._get_model().model == "model-from-env"
