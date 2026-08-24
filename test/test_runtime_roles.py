import pytest

from app.runtime import (
    AppRuntimeServices,
    BackgroundRuntimeServices,
    IndicatorRuntimeServices,
    InfraRuntimeServices,
)
from config import settings


def test_default_runtime_role_is_api():
    assert settings.APP_RUNTIME_ROLE == "api"


def test_background_runtime_role_excludes_api_market_io_services():
    services = AppRuntimeServices(
        infra=InfraRuntimeServices(object(), object()),
        indicators=IndicatorRuntimeServices(object(), object()),
        background=BackgroundRuntimeServices(object()),
    )

    assert services.require_background().market_scheduler is not None
    assert services.api is None
    with pytest.raises(RuntimeError, match="API runtime services"):
        services.require_api()
