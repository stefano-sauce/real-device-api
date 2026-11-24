"""One pytest test = one Access API session = one recorded job in Test Results.

Order of calls (each one matters for what ends up in Test Results):

    1. POST /sessions (with configuration.tunnel when a tunnel is used) -> wait ACTIVE
    2. installApp (App Storage) when the test needs an app from storage
    3. POST /appiumserver                -> before startTest, so the Appium log is attached
    4. POST /startTest (all artifacts)   -> video, screenshots, device log, Appium log, HAR
    5. enableNetworkCapture              -> only when the test checks network traffic
    6. ... the test drives the device; takeScreenshot fills the Screenshots tab ...
    7. POST /endTest {"status": passed|failed}
    8. DELETE /sessions/{id}             -> release the device
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime

from .client import AccessApiClient
from .live_network import LiveNetworkStream

REPO_TAG = "repo:real-device-api"


def base_tags() -> list[str]:
    tags = [REPO_TAG, "lang:python", "framework:appium", "api:access-api"]
    extra = os.environ.get("SAUCE_TAGS", "")
    tags += [t.strip() for t in extra.split(",") if t.strip()]
    return tags


def build_name() -> str:
    return os.environ.get("SAUCE_BUILD") or f"real-device-api-{datetime.now():%Y-%m-%d}"


@dataclass
class Run:
    api: AccessApiClient
    session_id: str
    session: dict
    job_id: str
    appium_url: str | None
    network: LiveNetworkStream | None
    log: list[str] = field(default_factory=list)

    def screenshot(self) -> None:
        """Adds a screenshot to the test's Screenshots tab."""
        try:
            self.api.take_screenshot(self.session_id)
        except Exception as exc:  # a missing screenshot must not fail the test
            print(f"  (screenshot failed: {exc})")


@contextmanager
def recorded_test(name: str, tags: list[str], *, device: str | None, os_name: str,
                  tunnel_name: str | None = None, install: str | tuple[str, str] | None = None,
                  instrument_network: bool = False, network_capture: bool = False,
                  appium: bool = True):
    api = AccessApiClient()
    all_tags = base_tags() + tags
    print(f"\n=== {name}\n  tags: {','.join(all_tags)}", flush=True)
    session_id = api.create_session(device, os_name, tunnel_name=tunnel_name)["id"]
    network = None
    job_id = None
    passed = False
    try:
        session = api.wait_until_active(session_id)
        dev = session["device"]
        print(f"  device: {dev['descriptor']} ({dev['os']} {dev.get('osVersion')})  session {session_id}", flush=True)
        if install:
            if isinstance(install, tuple):  # (filename, bundle ID / package) -> storage:<id>
                install = api.storage_app(*install)
            api.install_app(session_id, install, network_capture=instrument_network)
            api.wait_for_installations(session_id)
            print(f"  installed {install}", flush=True)
        appium_url = api.start_appium_server(session_id) if appium else None
        job_id = api.start_test(session_id, name, build=build_name(), tags=all_tags)
        print(f"  results: {api.test_url(job_id)}", flush=True)
        if network_capture:
            network = LiveNetworkStream(session["links"]["eventsWebsocketUrl"], api.creds).start()
            api.enable_network_capture(session_id)
        run = Run(api, session_id, session, job_id, appium_url, network)
        yield run
        passed = True
    finally:
        try:
            if job_id:
                if network:
                    api.disable_network_capture(session_id)
                api.end_test(session_id, passed)
                print(f"  {'PASSED' if passed else 'FAILED'}: {api.test_url(job_id)}", flush=True)
        finally:
            if network:
                network.stop()
            api.close_session(session_id)

