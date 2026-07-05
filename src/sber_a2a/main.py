import uvicorn

from sber_a2a.config import get_settings


def run() -> None:
    settings = get_settings()
    uvicorn.run(
        "sber_a2a.api:app",
        host=settings.app_host,
        port=settings.app_port,
        log_level=settings.log_level.lower(),
        reload=False,
    )


if __name__ == "__main__":
    run()
