"""Appium clients connected to the hosted Appium server of an Access API session.

Hosted-Appium sessions do not create an extra job: the test started with ``startTest`` is the
single entry in Test Results, and its Appium log tab shows these commands.
"""

from __future__ import annotations

import certifi
from appium import webdriver
from appium.options.android import UiAutomator2Options
from appium.options.ios import XCUITestOptions
from appium.webdriver.client_config import AppiumClientConfig
from selenium.webdriver.support.ui import WebDriverWait

from .recorded import Run


def connect(run: Run, platform: str, **caps) -> webdriver.Remote:
    creds = run.api.creds
    config = AppiumClientConfig(remote_server_addr=run.appium_url, username=creds.username,
                                password=creds.access_key, ca_certs=certifi.where(), timeout=300)
    options = UiAutomator2Options() if platform == "android" else XCUITestOptions()
    options.set_capability("appium:newCommandTimeout", 300)
    for k, v in caps.items():
        options.set_capability(k if ":" in k or k == "browserName" else f"appium:{k}", v)
    return webdriver.Remote(command_executor=run.appium_url, options=options, client_config=config)


def wait(driver, timeout_s: int = 30) -> WebDriverWait:
    return WebDriverWait(driver, timeout_s, poll_frequency=1)


def navigate(run: Run, driver, url: str, timeout_s: int = 30) -> None:
    """Open ``url`` in the browser under test.

    On some iOS 26 devices Safari opens on its Start Page and ``driver.get`` leaves the webview
    on about:blank. Then the page is opened with the Access API's ``openUrl`` instead, and the
    driver switches to the Safari webview that shows it.
    """
    driver.get(url)
    if driver.current_url.startswith(url.rstrip("/")):
        return
    print(f"  driver.get left the browser on {driver.current_url!r}; using openUrl", flush=True)
    run.api.open_url(run.session_id, url)

    def on_page(d):
        for ctx in d.execute_script("mobile: getContexts", {"waitForWebviewMs": 2000}):
            if ctx.get("url", "").startswith(url.rstrip("/")):
                d.switch_to.context(ctx["id"])
                return True
        return False

    wait(driver, timeout_s).until(on_page)
