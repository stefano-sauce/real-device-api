"""A site on this machine that a real device opens through a Sauce Connect 5 tunnel.

Devices never send ``localhost`` / ``127.0.0.1`` through the tunnel, so the site uses a made-up
host (``rdc-api.test``). Only that host goes through the tunnel (``--tunnel-domains``), and sc
hands those requests to the local server here as its upstream proxy (``--proxy``): nothing has to
resolve the name. The site is HTTPS (iOS Safari upgrades plain HTTP), with a self-signed
certificate that sc trusts through ``--cacert-file`` and re-signs for the device. The page carries
a per-run token, so a test can prove it got *this* page.
"""

from __future__ import annotations

import os
import shutil
import socket
import ssl
import subprocess
import tempfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import requests

LOCAL_SITE_HOST = "rdc-api.test"
LOCAL_SITE_URL = f"https://{LOCAL_SITE_HOST}/"
SC_REGIONS = {"eu-central-1": "eu-central", "us-west-1": "us-west"}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class LocalSite:
    """Upstream proxy for sc that answers every request with one page.

    Plain proxied requests (``GET http://rdc-api.test/``) are answered directly; ``CONNECT
    rdc-api.test:443`` is accepted and the connection is switched to TLS with the site's own
    certificate, then served the same way.
    """

    def __init__(self):
        self.token = uuid.uuid4().hex[:12]
        self.requests: list[str] = []
        self.dir = tempfile.mkdtemp(prefix="rdc-api-site-")
        self.cert = os.path.join(self.dir, "cert.pem")
        key = os.path.join(self.dir, "key.pem")
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2",
                        "-keyout", key, "-out", self.cert, "-subj", f"/CN={LOCAL_SITE_HOST}",
                        "-addext", f"subjectAltName=DNS:{LOCAL_SITE_HOST}"],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls.load_cert_chain(self.cert, key)
        token, seen = self.token, self.requests

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"  # keep-alive: requests after CONNECT arrive on the same socket

            def do_CONNECT(self):  # noqa: N802
                # sc tunnels HTTPS (and some devices' HTTP) as CONNECT host:port. Accept it, switch
                # to TLS for :443, and let the request that follows on this socket reach do_GET.
                self.send_response(200, "Connection Established")
                self.end_headers()
                self.wfile.flush()
                if self.path.endswith(":443"):
                    self.connection = tls.wrap_socket(self.connection, server_side=True)
                    self.rfile = self.connection.makefile("rb")
                    self.wfile = self.connection.makefile("wb")
                self.close_connection = False

            def do_GET(self):  # noqa: N802
                seen.append(self.path)
                if self.path.endswith("favicon.ico"):
                    self.send_response(404)
                    self.end_headers()
                    return
                body = (f"<!doctype html><html><head><meta name=viewport content='width=device-width'>"
                        f"<title>Served through Sauce Connect</title></head><body>"
                        f"<h1 id='heading'>Served through Sauce Connect</h1>"
                        f"<p id='token'>{token}</p></body></html>").encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_):
                pass

        self.port = _free_port()
        self.server = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def stop(self):
        self.server.shutdown()
        shutil.rmtree(self.dir, ignore_errors=True)


class SauceConnect:
    """Starts ``sc run`` and waits until the tunnel is ready (sc's /readyz endpoint)."""

    def __init__(self, site: LocalSite, region: str, tunnel_name: str | None = None):
        sc = shutil.which("sc") or "/opt/homebrew/bin/sc"
        self.name = tunnel_name or f"real-device-api-{uuid.uuid4().hex[:8]}"
        self.api_port = _free_port()
        self.log = tempfile.NamedTemporaryFile(prefix="sc-", suffix=".log", delete=False).name
        env = {**os.environ}
        cmd = [sc, "run",
               "--region", SC_REGIONS.get(region, region),
               "--tunnel-name", self.name,
               "--tunnel-domains", LOCAL_SITE_HOST.replace(".", r"\."),
               "--proxy", f"127.0.0.1:{site.port}",
               "--cacert-file", site.cert,
               "--proxy-localhost", "allow",
               "--api-address", f"127.0.0.1:{self.api_port}",
               "--log-file", self.log]
        # Credentials go through the environment (SAUCE_USERNAME / SAUCE_ACCESS_KEY), not argv.
        self.proc = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def wait_ready(self, timeout_s: int = 120) -> None:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(f"Sauce Connect exited ({self.proc.returncode}): {self.tail()}")
            try:
                if requests.get(f"http://127.0.0.1:{self.api_port}/readyz", timeout=3).status_code == 200:
                    return
            except requests.RequestException:
                pass
            time.sleep(2)
        self.stop()
        raise RuntimeError(f"Sauce Connect not ready after {timeout_s}s: {self.tail()}")

    def tail(self, n: int = 15) -> str:
        try:
            with open(self.log) as f:
                return "".join(f.readlines()[-n:])
        except OSError:
            return ""

    def stop(self) -> None:
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(30)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        try:
            os.unlink(self.log)
        except OSError:
            pass
