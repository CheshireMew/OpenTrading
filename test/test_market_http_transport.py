import logging

import httpx
import pytest

from app.infra.market_data.http import HttpPolicy, HttpxJsonTransport
from app.infra.structured_data import StructuredDataError


def test_feed_transport_retries_and_does_not_log_query_credentials(caplog):
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(503) if len(calls) == 1 else httpx.Response(200, json={"value": 42})

    client = HttpxJsonTransport(HttpPolicy(attempts=2, retry_delay_seconds=0), transport=httpx.MockTransport(respond))
    with caplog.at_level(logging.WARNING):
        assert client.get_json("https://feed.example/data", {"api_key": "private-test-key"}, {}) == {"value": 42}
    assert len(calls) == 2 and calls[0].url.params["api_key"] == "private-test-key"
    assert "private-test-key" not in caplog.text


def test_feed_transport_bounds_chunked_bytes_without_content_length():
    class Chunks(httpx.SyncByteStream):
        def __iter__(self):
            yield b"abcd"
            yield b"efgh"

    transport = httpx.MockTransport(lambda _: httpx.Response(200, stream=Chunks()))
    client = HttpxJsonTransport(HttpPolicy(max_response_bytes=5), transport=transport)
    with pytest.raises(StructuredDataError, match="exceeds"):
        client.get_bytes("https://feed.example/data")


def test_feed_transport_preserves_csv_and_rejects_malformed_json():
    client = HttpxJsonTransport(transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b"date,value\n2026-11-24,1\n")))
    assert client.get_bytes("https://feed.example/data").startswith(b"date,value\n")
    with pytest.raises(StructuredDataError):
        client.get_json("https://feed.example/data", {}, {})


def test_feed_transport_rejects_unrequested_compression_before_reading():
    class Unread(httpx.SyncByteStream):
        def __iter__(self):
            pytest.fail("Compressed body must not be decoded outside the byte budget")
            yield b""

    client = HttpxJsonTransport(transport=httpx.MockTransport(lambda _: httpx.Response(200,
        headers={"Content-Encoding": "gzip"}, stream=Unread())))
    with pytest.raises(StructuredDataError, match="identity encoding"):
        client.get_bytes("https://feed.example/data")
