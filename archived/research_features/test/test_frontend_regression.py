from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.main import create_app


ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT_DIR / "frontend" / "src"
CONTRACT_APP = create_app("api")


def read_frontend(path: str) -> str:
    return (FRONTEND_DIR / path).read_text(encoding="utf-8")


def extract_backend_routes() -> set[str]:
    return {
        route.path
        for route in CONTRACT_APP.routes
        if hasattr(route, "path")
    }


def normalize_frontend_path(path: str) -> str:
    if path.startswith("/tools/"):
        return f"/api/v1{path}"
    return f"/api/v1{path}"


def extract_request_calls(source: str) -> list[tuple[str, str]]:
    pattern = re.compile(r"(request)\.(get|post|delete)\(\s*([`'])(.+?)\3", re.DOTALL)
    return [(client, path) for client, _, _, path in pattern.findall(source)]


def extract_api_route_calls(source: str) -> list[str]:
    return re.findall(r"apiRoute\(\s*['\"]([a-z0-9_]+)['\"]", source)


def strip_api_prefix(path: str) -> str:
    return path.removeprefix("/api/v1")


def test_frontend_api_paths_match_fastapi_routes():
    backend_routes = {
        route.name: strip_api_prefix(route.path)
        for route in CONTRACT_APP.routes
        if hasattr(route, "path") and getattr(route, "path").startswith("/api/v1")
    }
    generated_routes = read_frontend("api/routes.ts")
    api_files = [
        "modules/market/api.ts",
        "modules/tools/api.ts",
        "modules/backtest/api.ts",
        "modules/factors/api.ts",
        "modules/system/api.ts",
    ]

    used_routes = set()
    for file_path in api_files:
        source = read_frontend(file_path)
        assert not extract_request_calls(source), f"{file_path} still hard-codes request URLs"
        used_routes.update(extract_api_route_calls(source))

    for route_name in used_routes:
        assert route_name in backend_routes, route_name
        assert f"{route_name}: {backend_routes[route_name]!r}".replace("'", '"') in generated_routes


@pytest.mark.parametrize(
    ("file_path", "route_name"),
    [
        ("modules/backtest/api.ts", "start_backtest"),
        ("modules/backtest/api.ts", "start_paper_run"),
        ("modules/factors/api.ts", "analyze_factors"),
        ("modules/factors/api.ts", "start_factor_backtest"),
        ("modules/factors/api.ts", "start_factor_paper_run"),
    ],
)
def test_frontend_long_tasks_use_dedicated_client(file_path: str, route_name: str):
    source = read_frontend(file_path)
    assert f"apiPost('{route_name}'" in source
    assert "client: 'longTask'" in source
    assert "longTaskRequest" not in source
    assert ".post(apiRoute(" not in source


def test_page_snapshot_registry_and_helpers_are_stable():
    source = read_frontend("composables/pageSnapshot.ts")

    assert "const PAGE_SNAPSHOT_PREFIX = 'heimdall_page_snapshot:'" in source
    for key in ["dca", "compare", "factorResearch", "halving", "backtest", "backtestEditor"]:
        assert re.search(rf"\b{key}:", source), key
    assert "readStringArray" in source
    assert "readEnum" in source
    assert "createPersistentPageSnapshot" in source
    assert "bind(sources:" in source
    assert "data: normalize(snapshot, fallback)" in source
    assert "{ deep: true, immediate: true }" in source


def test_generated_frontend_contracts_include_route_models():
    backtest_types = read_frontend("modules/backtest/generatedContracts.ts")
    factor_types = read_frontend("modules/factors/generatedContracts.ts")
    market_types = read_frontend("modules/market/generatedContracts.ts")

    assert "interface BacktestDeleteResponse" in backtest_types
    assert "interface FactorResearchRunListItemResponse" in factor_types
    assert "interface MarketHistoryResponse" in market_types
    assert "interface MarketHistoryBatchResponse" in market_types
    assert "interface OhlcvPointResponse" in market_types
    assert "interface GetMarketFullHistoryQueryParams" in market_types
    assert "GetMarketFullHistoryBatchQueryParamsMeta" not in market_types
    assert not (FRONTEND_DIR / "types").exists()


def test_frontend_business_code_uses_module_contract_boundaries():
    offenders = []
    for path in FRONTEND_DIR.rglob("*"):
        if path.suffix not in {".ts", ".vue"}:
            continue
        if path.name in {"contracts.ts", "generatedContracts.ts"}:
            continue
        source = path.read_text(encoding="utf-8")
        if "@/types" in source or re.search(r"from\s+['\"](?:\.\./)+types/", source):
            offenders.append(path.relative_to(FRONTEND_DIR).as_posix())

    assert offenders == []


def test_frontend_components_do_not_import_generated_types_directly():
    offenders = []
    for root in [FRONTEND_DIR / "components", FRONTEND_DIR / "views"]:
        for path in root.rglob("*"):
            if path.suffix not in {".ts", ".vue"}:
                continue
            source = path.read_text(encoding="utf-8")
            if re.search(r"from\s+['\"](?:\.\./)+types/", source) or "@/types" in source:
                offenders.append(path.relative_to(FRONTEND_DIR).as_posix())

    assert offenders == []


def test_market_cache_stores_have_resource_boundaries():
    assert not (FRONTEND_DIR / "modules" / "market" / "store.ts").exists()
    kline_source = read_frontend("modules/market/klineStore.ts")
    indicator_source = read_frontend("modules/market/indicatorStore.ts")

    for source in [kline_source, indicator_source]:
        assert "localStorage" not in source
        assert "sessionStorage" not in source
    assert "readKlineSlice" in kline_source
    assert "cachedData.length >= limit" in kline_source
    assert "return this.readKlineSlice(cachedData, limit)" in kline_source
    assert "MARKET_CACHE_TTL_MS.klineLive" in kline_source
    assert "MARKET_CACHE_TTL_MS.marketIndicators" in indicator_source
    assert "MARKET_CACHE_TTL_MS.sentimentFresh" in indicator_source
    assert "MARKET_CACHE_TTL_MS.sentimentRefresh" in indicator_source
    assert "marketHistoryApi.getLatestKlines" in kline_source
    assert "marketInsightApi.getIndicators" in indicator_source
    assert "Extreme Greed" in indicator_source


def test_kline_series_does_not_block_crypto_load_on_symbol_catalog():
    source = read_frontend("modules/market/useKlineSeries.ts")

    assert "ensureSymbolCatalogLoaded" not in source
    assert "klineStore.getKlineData(requestSymbol, requestTimeframe, 1000, options)" in source
    assert "isIndexSymbol(requestSymbol)" in source


def test_trading_view_chart_uses_adaptive_price_axis_precision():
    source = read_frontend("components/TradingViewChart.vue")

    assert "const resolvePricePrecision = () => {" in source
    assert "Math.ceil(Math.abs(Math.log10(minPrice))) + 3" in source
    assert "priceFormat: buildMainPriceFormat()" in source
    assert "syncMainPriceFormat()" in source


def test_symbol_search_supports_usd_equivalent_cash_assets():
    catalog_source = read_frontend("modules/market/symbolCatalog.ts")
    portfolio_source = read_frontend("views/tools/PortfolioBalance.vue")
    asset_source = read_frontend("modules/tools/portfolioBalance/assets.ts")
    generator_source = (ROOT_DIR / "scripts" / "generate_frontend_contracts.py").read_text(encoding="utf-8")

    assert "marketCatalogApi.getSymbols" in catalog_source
    assert "readCashSymbolPrices" in catalog_source
    assert "baseSymbolCatalog" not in catalog_source
    assert not any(path.name.startswith("generated") and path.name.endswith("Catalog.ts") for path in (FRONTEND_DIR / "modules" / "market").glob("*.ts"))
    assert not (FRONTEND_DIR / "modules" / "market" / "baseSymbolCatalog.ts").exists()

    assert "list_market_search_items" not in generator_source
    assert "readCashSymbolPrices" in asset_source
    assert "['crypto', 'index', 'cash']" in portfolio_source


def test_portfolio_backtest_history_uses_page_cache():
    source = read_frontend("modules/tools/portfolioBalance/data.ts")

    assert "portfolioHistoryCache" in source
    assert "portfolioHistoryMapCache" in source
    assert "loadIndexHistory(item.marketSymbol, startText)" in source
    assert "loadCryptoHistoryMap(" in source


def test_market_history_api_requests_do_not_keep_a_second_cache():
    source = read_frontend("modules/market/api.ts")

    assert "historyResponseCache" not in source
    for route_name in [
        "get_market_full_history",
        "get_market_full_history_batch",
        "get_index_history",
        "get_index_pricing_history",
    ]:
        assert route_name in source


def test_market_api_timeout_policy_matches_backend_wait_boundaries():
    source = read_frontend("modules/market/api.ts")

    assert "const MARKET_API_TIMEOUT_MS = {" in source
    assert "macroLiquidity: 60000" in source
    assert "liveMarket: 30000" in source
    assert "externalMarket: 30000" in source
    assert "aiTradeSetup: 180000" in source
    assert not re.search(r"timeout:\s*(?:15000|30000|60000|180000)", source)

    for route_name, timeout_key in [
        ("get_dli_liquidity", "macroLiquidity"),
        ("get_realtime_analysis", "liveMarket"),
        ("get_latest_klines", "liveMarket"),
        ("get_kline_tail", "liveMarket"),
        ("get_current_price", "liveMarket"),
        ("get_binance_market_page", "externalMarket"),
        ("get_binance_web3_heat_rank", "externalMarket"),
    ]:
        assert re.search(
            rf"apiGet\('{route_name}'[^\n]*timeout: MARKET_API_TIMEOUT_MS\.{timeout_key}",
            source,
        ), route_name


def test_backtest_paper_history_polling_has_single_non_overlapping_owner():
    history_source = read_frontend("modules/backtest/useBacktestRunHistory.ts")
    page_source = read_frontend("modules/backtest/useBacktestPage.ts")
    detail_source = read_frontend("modules/backtest/useBacktestDetailPage.ts")

    assert "paperHistoryPromise" in history_source
    assert "paperSelectionRefreshPromise" in history_source
    assert "startPaperHistoryPolling" in history_source
    assert "stopPaperHistoryPolling" in history_source
    assert "window.setInterval" in history_source
    assert "window.setInterval" not in page_source
    assert "window.setInterval" not in detail_source
    assert "paperRefreshTimer" not in page_source
    assert "paperRefreshTimer" not in detail_source


def test_binance_market_frontend_does_not_persist_server_response_cache():
    assert not (FRONTEND_DIR / "modules" / "market" / "binanceMarketCache.ts").exists()

    offenders = []
    for path in (FRONTEND_DIR / "modules" / "market").rglob("*"):
        if path.suffix not in {".ts", ".vue"}:
            continue
        source = path.read_text(encoding="utf-8")
        if "heimdall_binance_market_cache" in source or "readBinance" in source or "writeBinance" in source:
            offenders.append(path.relative_to(FRONTEND_DIR).as_posix())

    assert offenders == []


def test_binance_market_frontend_uses_warm_start_snapshot_boundary():
    snapshot_source = read_frontend("modules/market/binanceMarketWarmSnapshot.ts")
    web3_snapshot_source = read_frontend("modules/market/web3MarketWarmSnapshot.ts")
    monitor_source = read_frontend("modules/market/useBinanceMarketMonitor.ts")
    api_source = read_frontend("modules/market/api.ts")
    web3_source = read_frontend("modules/market/useWeb3HeatRankPanel.ts")

    assert "heimdall_binance_market_warm_snapshot" in snapshot_source
    assert "heimdall_web3_market_rank_warm_snapshot" in web3_snapshot_source
    assert "createWarmSnapshotStore" in snapshot_source
    assert "createWarmSnapshotStore" in web3_snapshot_source
    assert "binanceMarketWarmSnapshot.read" in monitor_source
    assert "binanceMarketWarmSnapshot.write" in monitor_source
    assert "getBinanceMarketPage" in monitor_source
    assert "getBinanceMarketBoards" not in monitor_source
    assert "getBinanceBreakoutMonitor" not in monitor_source
    assert "getBinanceMarketBoards(" not in api_source
    assert "getBinanceBreakoutMonitor(" not in api_source
    assert "get_binance_market_boards" not in read_frontend("api/routes.ts")
    assert "get_binance_market_breakout_monitor" not in read_frontend("api/routes.ts")
    assert "web3HeatRankWarmSnapshot.read" in web3_source
    assert "web3HeatRankWarmSnapshot.write" in web3_source
    assert "restoreBinanceMarketWarmSnapshot" not in monitor_source
    assert "saveBinanceMarketWarmSnapshot" not in monitor_source
    assert "restoreWeb3HeatRankWarmSnapshot" not in web3_source
    assert "saveWeb3HeatRankWarmSnapshot" not in web3_source
    assert "binanceMarketCache" not in snapshot_source
    assert "readBinance" not in snapshot_source
    assert "writeBinance" not in snapshot_source


def test_market_warm_snapshot_requests_discard_stale_parameter_responses():
    monitor_source = read_frontend("modules/market/useBinanceMarketMonitor.ts")
    web3_heat_source = read_frontend("modules/market/useWeb3HeatRankPanel.ts")
    web3_page_source = read_frontend("modules/market/useWeb3MarketRankPage.ts")

    assert "let fetchState: { key: string; task: Promise<void> } | null = null" in monitor_source
    assert "const requestMinRisePct = minRisePct.value" in monitor_source
    assert "if (requestKey !== marketPageRequestKey()) return" in monitor_source
    assert "binanceMarketWarmSnapshot.write(response, requestMinRisePct, requestQuoteAsset)" in monitor_source
    assert "min_rise_pct: minRisePct.value" not in monitor_source
    assert "binanceMarketWarmSnapshot.write(response.data, minRisePct.value" not in monitor_source

    assert "let heatRankFetchState: { key: string; task: Promise<void> } | null = null" in web3_heat_source
    assert "const requestChainId = chainId.value" in web3_heat_source
    assert "if (requestKey !== heatRankRequestKey()) return" in web3_heat_source
    assert "web3HeatRankWarmSnapshot.write(response, requestChainId, WEB3_HEAT_RANK_SIZE)" in web3_heat_source
    assert "web3HeatRankWarmSnapshot.write(response.data, chainId.value" not in web3_heat_source

    assert "let addressPnlFetchState: { key: string; task: Promise<void> } | null = null" in web3_page_source
    assert "const requestChainId = chainId.value" in web3_page_source
    assert "if (requestKey !== addressPnlRequestKey()) return" in web3_page_source
    assert "const selectedChainId = web3ApiChainId(requestChainId)" in web3_page_source
    assert "const selectedChainId = web3ApiChainId(chainId.value)" not in web3_page_source


def test_binance_market_rank_tables_use_i18n_headers_and_sortable_volume_metrics():
    view_source = read_frontend("views/indicators/BinanceMarket.vue")
    zh_source = read_frontend("i18n/zh-CN.json")
    en_source = read_frontend("i18n/en.json")
    shared_source = read_frontend("modules/market/binanceMarketShared.ts")
    monitor_source = read_frontend("modules/market/useBinanceMarketMonitor.ts")

    for key in ["binanceMarket.columns.asset", "binanceMarket.columns.price", "binanceMarket.columns.quoteVolume"]:
        assert key in view_source
    for label in ["标的", "价格", "成交额"]:
        assert label in zh_source
    for label in ["Asset", "Price", "Quote Volume"]:
        assert label in en_source
    for removed_web3_label in ["Web3 热度榜", "代币", "热度", "市值", "流动性", "聪明钱"]:
        assert removed_web3_label not in view_source
    for english_label in [">Symbol<", ">Quote Vol<"]:
        assert english_label not in view_source

    assert "toggleContractSort('quote_volume')" in view_source
    assert "toggleSpotSort('quote_volume')" in view_source
    assert "type SpotSortField = 'price_change_pct' | 'quote_volume'" in shared_source
    assert "type ContractSortField = 'price_change_pct' | 'funding_rate_pct' | 'quote_volume'" in shared_source
    assert "const spotSort = ref<SpotSortState>" in monitor_source
    assert "payload.spot_boards" in monitor_source
    assert "payload.contract_boards" in monitor_source
    assert "payload.spot_ticker" not in monitor_source
    assert "mergeDerivatives" not in shared_source


def test_web3_heat_rank_lives_on_web3_rank_page_only():
    binance_market_view = read_frontend("views/indicators/BinanceMarket.vue")
    web3_rank_view = read_frontend("views/indicators/Web3MarketRank.vue")
    web3_page_source = read_frontend("modules/market/useWeb3MarketRankPage.ts")
    web3_heat_source = read_frontend("modules/market/useWeb3HeatRankPanel.ts")

    assert not (FRONTEND_DIR / "modules" / "market" / "useBinanceWeb3Panel.ts").exists()
    assert "useWeb3HeatRankPanel(chainId)" in web3_page_source
    assert "web3HeatRank" in web3_rank_view
    assert "BinanceWeb3TokenDialog" in web3_rank_view
    assert "toggleWeb3Sort('percent_change_24h')" in web3_rank_view
    assert "toggleWeb3Sort('market_cap')" in web3_rank_view
    assert "toggleWeb3Sort('liquidity')" in web3_rank_view
    for removed_board in ["Social Hype", "Unified Rank", "Smart Money Inflow", "Meme Rank"]:
        assert removed_board not in web3_rank_view
    for removed_fetch in [
        "getBinanceWeb3SocialHype",
        "getBinanceWeb3UnifiedTokenRank",
        "getBinanceWeb3SmartMoneyInflow",
        "getBinanceWeb3MemeRank",
    ]:
        assert removed_fetch not in web3_page_source
    assert "const web3Sort = ref<Web3HeatRankSortState>" in web3_heat_source
    assert "getBinanceWeb3HeatRankBoards" in web3_heat_source
    assert "compareNullableNumber" not in web3_heat_source
    assert "web3HeatRank" not in binance_market_view
    assert "BinanceWeb3TokenDialog" not in binance_market_view


def test_frontend_navigation_uses_single_manifest():
    app_source = read_frontend("App.vue")
    router_source = read_frontend("router/index.ts")
    navigation_source = read_frontend("app/navigation.ts")

    assert "APP_ROUTE_DEFINITIONS" in navigation_source
    assert "APP_NAV_ITEMS" in navigation_source
    assert "APP_KEEP_ALIVE_ROUTE_NAMES" in navigation_source
    assert "APP_ROUTE_DEFINITIONS.map" in router_source
    assert "APP_NAV_SECTIONS.map" in app_source
    assert "APP_NAV_ITEMS.filter" in app_source


def test_market_frontend_uses_generated_query_contracts():
    market_types = read_frontend("modules/market/generatedContracts.ts")
    contracts_source = read_frontend("modules/market/contracts.ts")
    api_source = read_frontend("modules/market/api.ts")
    request_source = read_frontend("api/request.ts")
    routes_source = read_frontend("api/routes.ts")

    assert "interface GetMarketFullHistoryQueryParams" in market_types
    assert "interface GetMarketFullHistoryBatchQueryParams" in market_types
    assert "GetMarketFullHistoryBatchQueryParamsMeta" not in market_types
    assert "repeatedKeys" in routes_source
    assert "GetRealtimeAnalysisQueryParams" not in contracts_source
    assert "GetMarketFullHistoryQueryParams" not in contracts_source
    assert "interface FullHistoryParams" not in contracts_source
    assert "CURRENT_PRICE_BATCH_QUERY_META" not in contracts_source
    assert "FULL_HISTORY_BATCH_QUERY_META" not in contracts_source
    assert "serializeEndpointQuery" in request_source
    assert "API_QUERY_META" not in api_source
    assert "normalizePriceHistoryParams" not in api_source
    assert "serializeBatchFullHistoryParams" not in api_source
    assert "get_current_price_batch" in api_source
    assert "get_market_full_history_batch" in api_source


def test_frontend_api_client_uses_route_response_type_map():
    request_source = read_frontend("api/request.ts")
    routes_source = read_frontend("api/routes.ts")
    module_api_sources = [
        read_frontend("modules/market/api.ts"),
        read_frontend("modules/tools/api.ts"),
        read_frontend("modules/backtest/api.ts"),
        read_frontend("modules/factors/api.ts"),
        read_frontend("modules/system/api.ts"),
    ]

    assert "ApiRouteResponse<TRoute>" in request_source
    assert "ApiRouteBody<TRoute>" in request_source
    assert "ApiRouteQuery<TRoute>" in request_source
    assert "export type ApiRouteResponseMap" in routes_source
    assert "export type ApiRouteBodyMap" in routes_source
    assert "export type ApiRouteQueryMap" in routes_source
    assert "<TResponse = unknown>" not in request_source
    assert "AxiosResponse" in request_source
    assert all("AxiosResponse" not in source for source in module_api_sources)


def test_frontend_has_no_global_generated_types_or_js_sources():
    assert not (FRONTEND_DIR / "types").exists()
    assert not list(FRONTEND_DIR.rglob("*.js"))
    offenders = []
    for path in FRONTEND_DIR.rglob("*"):
        if path.suffix not in {".ts", ".vue"}:
            continue
        source = path.read_text(encoding="utf-8")
        if "@/types" in source or re.search(r"from\s+['\"](?:\.\./)+types/", source):
            offenders.append(path.relative_to(FRONTEND_DIR).as_posix())
    assert offenders == []


def test_backtest_and_factor_formatting_entry_points_are_present():
    backtest_source = read_frontend("modules/backtest/useBacktestRunFormatting.ts")
    factor_source = read_frontend("modules/factors/useFactorResearchFormatting.ts")

    for token in [
        "latestRunsByVersion",
        "versionCompareOptions",
        "toggleCompareRun",
        "toggleVersionCompare",
        "paper_live",
        "compareRunLabel",
    ]:
        assert token in backtest_source

    for token in [
        "factorChipClass",
        "categoryChipClass",
        "scoreClass",
        "correlationClass",
        "formatPct",
        "formatNumber",
        "formatDate",
    ]:
        assert token in factor_source


def test_factor_research_does_not_auto_run_heavy_analysis_on_mount():
    source = read_frontend("modules/factors/useFactorResearchData.ts")

    assert "await initializeContract()" in source
    assert "await Promise.all([fetchCatalog(), fetchRuns()])" in source
    assert "if (!state.summary.value) await runAnalysis()" not in source


def test_backtest_detail_history_panel_exposes_delete_action():
    source = read_frontend("modules/backtest/useBacktestDetailPage.ts")

    assert "const deleteRun = async (runId: number, mode: BacktestRunMode) => {" in source
    assert "await runs.deleteRun(runId, mode)" in source
    assert "deleteRun," in source
