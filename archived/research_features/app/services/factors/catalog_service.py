from __future__ import annotations

from app.domain.market.symbol_catalog import get_supported_crypto_symbols
from app.services.persistence_ports import IndicatorRepositoryPort

from .contracts import (
    DEFAULT_CLEANING,
    DEFAULT_FORWARD_HORIZONS,
    SUPPORTED_CATEGORIES,
    SUPPORTED_TIMEFRAMES,
    FactorDefinition,
    DERIVED_FACTORS,
    factor_from_meta,
    serialize_factor,
)


class FactorCatalogService:
    def __init__(self, indicator_repository: IndicatorRepositoryPort) -> None:
        self.indicator_repository = indicator_repository

    def get_catalog(self) -> dict:
        factor_list = sorted(
            self._list_all_factors(),
            key=lambda item: (SUPPORTED_CATEGORIES.index(item.category), item.name.lower()),
        )
        return {
            "symbols": get_supported_crypto_symbols(),
            "timeframes": list(SUPPORTED_TIMEFRAMES),
            "categories": list(SUPPORTED_CATEGORIES),
            "factors": [serialize_factor(item) for item in factor_list],
            "forward_horizons": list(DEFAULT_FORWARD_HORIZONS),
            "cleaning": dict(DEFAULT_CLEANING),
        }

    def select_factors(self, categories: list[str], factor_ids: list[str]) -> list[FactorDefinition]:
        selected_categories = {item for item in categories if item in SUPPORTED_CATEGORIES}
        selected_ids = {item for item in factor_ids if item}
        catalog = self._list_all_factors()
        if not selected_categories and not selected_ids:
            return catalog
        result = []
        for definition in catalog:
            if selected_categories and definition.category not in selected_categories:
                continue
            if selected_ids and definition.factor_id not in selected_ids:
                continue
            result.append(definition)
        return result

    def _list_all_factors(self) -> list[FactorDefinition]:
        external_factors = [factor_from_meta(meta) for meta in self.indicator_repository.list_active_meta()]
        return [*external_factors, *DERIVED_FACTORS]
