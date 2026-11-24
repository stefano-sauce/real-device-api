"""Thin client for the Sauce Labs Real Device Access API (rdc/v2).

Every method maps 1:1 to a REST endpoint (see open_api_specification.yaml):

    POST   /rdc/v2/sessions                                   reserve a device (optionally with a tunnel)
    GET    /rdc/v2/sessions/{id}                              poll until ACTIVE
    POST   /rdc/v2/sessions/{id}/startTest                    start a recorded test (video, logs, HAR, ...)
    POST   /rdc/v2/sessions/{id}/endTest                      stop it, set passed/failed
    POST   /rdc/v2/sessions/{id}/device/enableNetworkCapture  route device traffic through the capture proxy
    POST   /rdc/v2/sessions/{id}/device/installApp            install from App Storage
    POST   /rdc/v2/sessions/{id}/device/launchApp             launch an installed app (e.g. from the App Store)
    POST   /rdc/v2/sessions/{id}/appiumserver                 start a hosted Appium server next to the device
    DELETE /rdc/v2/sessions/{id}                              release the device

Credentials come from SAUCE_USERNAME / SAUCE_ACCESS_KEY. The region defaults to EU (eu-central-1).
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

import requests

REGIONS = {
    "eu-central-1": "https://api.eu-central-1.saucelabs.com",
    "us-west-1": "https://api.us-west-1.saucelabs.com",
}


class AccessApiError(RuntimeError):
    pass


@dataclass
class Credentials:
    username: str
    access_key: str
    region: str

    @classmethod
    def from_env(cls) -> "Credentials":
        missing = [v for v in ("SAUCE_USERNAME", "SAUCE_ACCESS_KEY") if not os.environ.get(v)]
        if missing:
            raise SystemExit(f"Missing environment variable(s): {', '.join(missing)}")
        region = os.environ.get("SAUCE_REGION") or "eu-central-1"
        if region not in REGIONS:
            raise SystemExit(f"Unknown SAUCE_REGION '{region}'. Use one of: {', '.join(REGIONS)}")
        return cls(os.environ["SAUCE_USERNAME"], os.environ["SAUCE_ACCESS_KEY"], region)

    @property
    def api_base(self) -> str:
        return REGIONS[self.region]


class AccessApiClient:
    def __init__(self, creds: Credentials | None = None, timeout: int = 90):
        self.creds = creds or Credentials.from_env()
        self.base = f"{self.creds.api_base}/rdc/v2"
        self.http = requests.Session()
        self.http.auth = (self.creds.username, self.creds.access_key)
        self.timeout = timeout

    def _call(self, method: str, path: str, json: Any = None, ok=(200, 201, 204)) -> Any:
        r = self.http.request(method, f"{self.base}{path}", json=json, timeout=self.timeout)
        if r.status_code not in ok:
            raise AccessApiError(f"{method} {path} -> HTTP {r.status_code}: {r.text[:500]}")
        if r.status_code == 204 or not r.content:
            return None
        try:
            return r.json()
        except ValueError:
            return r.text

    # ----------------------------------------------------------------- sessions
    def create_session(self, device_name: str | None = None, os_name: str | None = None,
                       tunnel_name: str | None = None, duration: str = "PT1H",
                       wait_for_device_s: int = 900) -> dict:
        """Reserve a device. If it is busy or still being cleaned, retry for up to ``wait_for_device_s``."""
        device: dict[str, Any] = {}
        if os_name:
            device["os"] = os_name
        if device_name:
            device["deviceName"] = device_name
        configuration: dict[str, Any] = {"sessionDuration": duration}
        if tunnel_name:
            configuration["tunnel"] = {"name": tunnel_name}
        body = {"device": device, "configuration": configuration}
        deadline = time.time() + wait_for_device_s
        while True:
            try:
                return self._call("POST", "/sessions", json=body)
            except AccessApiError as exc:
                retryable = "un-available" in str(exc) or "unavailable" in str(exc).lower() or "HTTP 429" in str(exc)
                if not retryable or time.time() > deadline:
                    raise
                print(f"  no device free for {device_name or os_name}, retrying in 20s ...", flush=True)
                time.sleep(20)

    def get_session(self, session_id: str) -> dict:
        return self._call("GET", f"/sessions/{session_id}")

    def wait_until_active(self, session_id: str, timeout_s: int = 600) -> dict:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            s = self.get_session(session_id)
            if s["state"] == "ACTIVE":
                return s
            if s["state"] in ("ERRORED", "CLOSED", "CLOSING"):
                raise AccessApiError(f"Session {session_id} ended up {s['state']}: {s.get('error', '')}")
            time.sleep(4)
        raise AccessApiError(f"Session {session_id} not ACTIVE after {timeout_s}s")

    def close_session(self, session_id: str) -> None:
        self._call("DELETE", f"/sessions/{session_id}")

    # -------------------------------------------------------- recorded tests
    def start_test(self, session_id: str, name: str, build: str | None = None,
                   tags: list[str] | None = None) -> str:
        """Start a recorded test (Real Device Access API > Test Results).

        Every artifact must be requested explicitly, otherwise the matching tab in Test Results
        stays empty. ``networkCapture`` only attaches the HAR: capturing itself needs
        :meth:`enable_network_capture`. The hosted Appium server has to be started *before*
        this call for its log to be attached.
        """
        body: dict[str, Any] = {
            "testName": name,
            "artifacts": {
                "video": True,
                "screenshots": True,
                "deviceLogs": True,
                "networkCapture": True,
                "appiumLogs": True,
            },
        }
        if build:
            body["build"] = build
        if tags:
            body["tags"] = tags
        return self._call("POST", f"/sessions/{session_id}/startTest", json=body)["jobId"]

    def end_test(self, session_id: str, passed: bool | None = None) -> dict:
        body = {} if passed is None else {"status": "passed" if passed else "failed"}
        return self._call("POST", f"/sessions/{session_id}/endTest", json=body)

    def test_url(self, job_id: str) -> str:
        return self.creds.api_base.replace("://api.", "://app.") + f"/tests/{job_id}"

    def har_url(self, job_id: str) -> str:
        return f"{self.creds.api_base}/v1/rdc/jobs/{job_id}/network.har"

    def download_har(self, job_id: str, timeout_s: int = 120) -> bytes:
        """The HAR on the test's Network tab. Artifacts are collected after endTest, so poll."""
        deadline = time.time() + timeout_s
        while True:
            r = self.http.get(self.har_url(job_id), timeout=self.timeout)
            if r.status_code == 200 and r.content:
                return r.content
            if time.time() > deadline:
                return b""
            time.sleep(5)

    # -------------------------------------------------------- network capture
    def enable_network_capture(self, session_id: str) -> None:
        self._call("POST", f"/sessions/{session_id}/device/enableNetworkCapture")

    def disable_network_capture(self, session_id: str) -> None:
        self._call("POST", f"/sessions/{session_id}/device/disableNetworkCapture")

    # ------------------------------------------------------- device actions
    def take_screenshot(self, session_id: str) -> bytes:
        """PNG of the screen. During a recorded test it is also added to the Screenshots tab."""
        r = self.http.post(f"{self.base}/sessions/{session_id}/device/takeScreenshot", timeout=self.timeout)
        if r.status_code != 200:
            raise AccessApiError(f"takeScreenshot -> HTTP {r.status_code}: {r.text[:200]}")
        return r.content

    def open_url(self, session_id: str, url: str) -> None:
        self._call("POST", f"/sessions/{session_id}/device/openUrl", json={"url": url})

    def launch_app(self, session_id: str, bundle_id: str | None = None,
                   package: str | None = None, activity: str | None = None) -> None:
        """Launch an app that is already on the device: an App Store / Play Store app kept by the
        org's cleaning settings, a system app, or one installed with :meth:`install_app`.
        Note: the call also succeeds for a bundle ID that is not installed."""
        body: dict[str, str] = {}
        if bundle_id:
            body["bundleId"] = bundle_id
        if package:
            body["packageName"] = package
        if activity:
            body["activityName"] = activity
        self._call("POST", f"/sessions/{session_id}/device/launchApp", json=body)

    def storage_app(self, filename: str, identifier: str) -> str:
        """``storage:<id>`` of the newest App Storage file called ``filename`` with bundle ID / package
        ``identifier``. Other suites re-upload files with the same name but a different app inside,
        so ``storage:filename=...`` alone is not stable."""
        r = self.http.get(f"{self.creds.api_base}/v1/storage/files",
                          params={"q": filename, "per_page": 100}, timeout=self.timeout)
        r.raise_for_status()
        items = [i for i in r.json().get("items", [])
                 if i["name"] == filename and i.get("metadata", {}).get("identifier") == identifier]
        if not items:
            raise AccessApiError(f"No App Storage file {filename} with identifier {identifier}")
        return "storage:" + max(items, key=lambda i: i["upload_timestamp"])["id"]

    def install_app(self, session_id: str, app: str, network_capture: bool = False,
                    launch_after_install: bool = False) -> None:
        """Install from Sauce App Storage (e.g. ``storage:filename=SauceLabs-Demo-App.apk``).

        ``features.networkCapture`` instruments the app so it trusts the capture proxy, which is
        what makes a native app's HTTPS traffic readable in the HAR.
        """
        self._call("POST", f"/sessions/{session_id}/device/installApp", json={
            "app": app,
            "enableInstrumentation": True,
            "launchAfterInstall": launch_after_install,
            "features": {"networkCapture": network_capture},
        })

    def wait_for_installations(self, session_id: str, timeout_s: int = 600) -> None:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            items = (self._call("POST", f"/sessions/{session_id}/device/listAppInstallations") or {}) \
                .get("appInstallations", []) or []
            states = [i.get("status") for i in items]
            if states and all(s == "FINISHED" for s in states):
                return
            if any(s == "ERROR" for s in states):
                raise AccessApiError(f"App installation failed: {items}")
            time.sleep(5)
        raise AccessApiError("App installation timed out")

    # --------------------------------------------------------- hosted Appium
    def start_appium_server(self, session_id: str, version: str = "latest", timeout_s: int = 180) -> str:
        """Start (or reuse) the hosted Appium server next to the device and return its URL."""
        try:
            info = self._call("GET", f"/sessions/{session_id}/appiumserver") or {}
        except AccessApiError:
            info = {}
        if not info.get("url"):
            info = self._call("POST", f"/sessions/{session_id}/appiumserver", json={"appiumVersion": version})
        deadline = time.time() + timeout_s
        while not info.get("url") and time.time() < deadline:
            time.sleep(3)
            info = self._call("GET", f"/sessions/{session_id}/appiumserver")
        if not info.get("url"):
            raise AccessApiError(f"Hosted Appium server did not start: {info}")
        return info["url"]
