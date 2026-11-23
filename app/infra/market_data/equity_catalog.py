"""HTTP transport and upstream response validation for exchange equity catalogs."""
import httpx


class EquityCatalogClient:
    def __init__(self, transport=None):
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(25, connect=10), transport=transport,
            headers={"Accept": "application/json", "User-Agent": "OpenTrading/2.0 (public market catalog)"},
            limits=httpx.Limits(max_connections=12, max_keepalive_connections=6),
            follow_redirects=True,
        )

    async def get(self, url, **params):
        response = await self._client.get(url, params=params or None)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Exchange catalog has an unexpected schema")
        code = str(payload.get("code", ""))
        if code not in {"", "0", "00000", "000000"} or payload.get("success") is False:
            raise ValueError(f"Exchange rejected market catalog request ({code})")
        return payload

    async def aclose(self):
        await self._client.aclose()
