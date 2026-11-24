"""Live network traffic from the device, while the test is running.

Every Access API session exposes an *events* (companion) WebSocket
(``session["links"]["eventsWebsocketUrl"]``). Once network capture is enabled, each HTTP(S)
exchange is pushed on it as ``{"type": "device.har.entry", "value": {"event": <HAR entry>}}``.
Tests use the collected URLs to assert that capture works *before* ``endTest``, so the verdict
on the Sauce job reflects it.
"""

from __future__ import annotations

import base64
import json
import ssl
import threading
import time

import certifi
import websocket

from .client import Credentials

HAR_EVENT = "device.har.entry"


class LiveNetworkStream:
    def __init__(self, events_ws_url: str, creds: Credentials):
        self.url = events_ws_url
        self.creds = creds
        self.urls: list[str] = []  # request URLs, in arrival order (requests and responses both pushed)
        self._connected = threading.Event()
        self._stop = False
        self._ws: websocket.WebSocketApp | None = None

    def start(self, wait_s: int = 20) -> "LiveNetworkStream":
        token = base64.b64encode(f"{self.creds.username}:{self.creds.access_key}".encode()).decode()
        self._ws = websocket.WebSocketApp(
            self.url,
            header=[f"Authorization: Basic {token}"],
            on_open=lambda _ws: self._connected.set(),
            on_message=lambda _ws, msg: self._handle(msg),
        )
        threading.Thread(target=self._run, daemon=True).start()
        if not self._connected.wait(wait_s):
            raise RuntimeError("Could not connect to the session events WebSocket")
        return self

    def _run(self) -> None:
        while not self._stop:  # reconnect if the socket drops mid-test
            self._ws.run_forever(sslopt={"cert_reqs": ssl.CERT_REQUIRED, "ca_certs": certifi.where()},
                                 ping_interval=20, ping_timeout=10)
            if not self._stop:
                time.sleep(2)

    def stop(self) -> None:
        self._stop = True
        if self._ws:
            self._ws.close()

    def _handle(self, raw: str) -> None:
        try:
            msg = json.loads(raw)
        except ValueError:
            return
        if msg.get("type") != HAR_EVENT:
            return
        entry = (msg.get("value") or {}).get("event") or {}
        url = (entry.get("request") or {}).get("url")
        if url:
            self.urls.append(url)

    def wait_for(self, pattern: str, timeout_s: int = 30) -> list[str]:
        """Return the captured URLs containing ``pattern``, waiting up to ``timeout_s`` for one."""
        deadline = time.time() + timeout_s
        while True:
            hits = [u for u in self.urls if pattern in u]
            if hits or time.time() > deadline:
                return hits
            time.sleep(1)
