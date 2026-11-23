"""Upstream market websocket transport."""
import websockets


def connect(url, **options):
    return websockets.connect(url, **options)
