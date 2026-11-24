"""Web app tests: public sites and a site on this machine reached through Sauce Connect."""

import pytest
from selenium.webdriver.common.by import By

from conftest import ANDROID_PRIVATE, ANDROID_PUBLIC, IOS_PRIVATE, IOS_PUBLIC
from rdc.driver import connect, navigate, wait
from rdc.recorded import recorded_test
from rdc.tunnel import LOCAL_SITE_HOST, LOCAL_SITE_URL

SAUCEDEMO = "https://www.saucedemo.com/"
# Browser contexts (chromedriver, Safari) speak W3C WebDriver: CSS selectors, not Appium's "id" strategy.


def saucedemo_login(run, driver) -> None:
    navigate(run, driver, SAUCEDEMO)
    wait(driver).until(lambda d: d.find_elements(By.CSS_SELECTOR, "#user-name"))[0].send_keys("standard_user")
    driver.find_element(By.CSS_SELECTOR, "#password").send_keys("secret_sauce")
    run.screenshot()
    driver.find_element(By.CSS_SELECTOR, "#login-button").click()
    wait(driver).until(lambda d: "inventory" in d.current_url)
    assert driver.find_elements(By.CSS_SELECTOR, ".inventory_item"), "no products after login"
    run.screenshot()


def check_local_site(run, driver, site) -> None:
    navigate(run, driver, LOCAL_SITE_URL)
    token = wait(driver, 60).until(lambda d: d.find_elements(By.CSS_SELECTOR, "#token"))[0].text
    run.screenshot()
    assert token == site.token, f"page came from somewhere else (token {token!r})"
    assert site.requests, "the local site saw no request"


def test_android_web_network_capture():
    """Public Android, Chrome, saucedemo.com login; the site's requests are checked in the capture."""
    with recorded_test(
        "Android web - saucedemo login - network capture",
        ["platform:android", "device:public", "browser:chrome", "usecase:web-app", "feature:network-capture"],
        device=ANDROID_PUBLIC, os_name="android", network_capture=True,
    ) as run:
        driver = connect(run, "android", browserName="Chrome")
        try:
            saucedemo_login(run, driver)
            hits = run.network.wait_for("saucedemo.com", timeout_s=30)
            assert hits, f"no saucedemo.com request captured; saw {run.network.urls[:10]}"
            print(f"  network capture: {len(hits)} saucedemo.com request(s)")
        finally:
            driver.quit()


@pytest.mark.xdist_group("ios-private")
def test_ios_private_web():
    """Private iPhone, Safari, saucedemo.com login."""
    with recorded_test(
        "iOS private web - saucedemo login",
        ["platform:ios", "device:private", "browser:safari", "usecase:web-app"],
        device=IOS_PRIVATE, os_name="ios",
    ) as run:
        driver = connect(run, "ios", browserName="Safari")
        try:
            saucedemo_login(run, driver)
        finally:
            driver.quit()


@pytest.mark.xdist_group("tunnel")
def test_android_private_web_tunnel_network_capture(tunnel):
    """Private Android, Chrome opens a site on this machine through Sauce Connect; the tunnelled
    request also shows up in the network capture."""
    sc, site = tunnel
    with recorded_test(
        "Android private web - local site via Sauce Connect - network capture",
        ["platform:android", "device:private", "browser:chrome", "usecase:web-app",
         "feature:sauce-connect", "feature:network-capture"],
        device=ANDROID_PRIVATE, os_name="android", tunnel_name=sc.name, network_capture=True,
    ) as run:
        driver = connect(run, "android", browserName="Chrome")
        try:
            check_local_site(run, driver, site)
            hits = run.network.wait_for(LOCAL_SITE_HOST, timeout_s=30)
            assert hits, f"no {LOCAL_SITE_HOST} request captured; saw {run.network.urls[:10]}"
            print(f"  network capture: {len(hits)} tunnelled request(s) to {LOCAL_SITE_HOST}")
        finally:
            driver.quit()


@pytest.mark.xdist_group("tunnel")
def test_ios_public_web_tunnel(tunnel):
    """Public iPhone, Safari opens a site on this machine through Sauce Connect."""
    sc, site = tunnel
    with recorded_test(
        "iOS web - local site via Sauce Connect",
        ["platform:ios", "device:public", "browser:safari", "usecase:web-app", "feature:sauce-connect"],
        device=IOS_PUBLIC, os_name="ios", tunnel_name=sc.name,
    ) as run:
        driver = connect(run, "ios", browserName="Safari")
        try:
            check_local_site(run, driver, site)
        finally:
            driver.quit()
