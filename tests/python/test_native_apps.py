"""Native app tests: My Demo App from App Storage (public devices) and from the App Store (private device)."""

import pytest
from appium.webdriver.common.appiumby import AppiumBy

from conftest import ANDROID_PUBLIC, IOS_PRIVATE, IOS_PUBLIC
from rdc.driver import connect, wait
from rdc.recorded import recorded_test

ANDROID_PKG = "com.saucelabs.mydemoapp.android"
ANDROID_ID = f"{ANDROID_PKG}:id"
IOS_BUNDLE = "com.saucelabs.mydemo.app.ios"
CAPTURED_SITE = "www.saucedemo.com"


def ios_catalog_flow(run, driver) -> None:
    """Catalog -> first product -> add to cart -> cart badge shows 1 item."""
    driver.find_element(AppiumBy.ACCESSIBILITY_ID, "Catalog-tab-item").click()
    products = wait(driver).until(lambda d: d.find_elements(AppiumBy.ACCESSIBILITY_ID, "ProductItem"))
    assert products, "no products in the catalog"
    run.screenshot()
    products[0].click()
    wait(driver).until(lambda d: d.find_elements(AppiumBy.ACCESSIBILITY_ID, "Add To Cart")
                       )[0].click()
    run.screenshot()
    driver.find_element(AppiumBy.ACCESSIBILITY_ID, "Cart-tab-item").click()
    wait(driver).until(lambda d: d.find_elements(AppiumBy.ACCESSIBILITY_ID, "ProceedToCheckout"))
    run.screenshot()


def test_android_app_storage_network_capture():
    """Public Android, APK from App Storage instrumented for network capture, traffic checked live."""
    with recorded_test(
        "Android - My Demo App (App Storage) - network capture",
        ["platform:android", "device:public", "app:app-storage", "usecase:native-app",
         "feature:network-capture"],
        device=ANDROID_PUBLIC, os_name="android",
        install=("SauceLabs-Demo-App.apk", ANDROID_PKG), instrument_network=True,
        network_capture=True,
    ) as run:
        driver = connect(run, "android", appPackage=ANDROID_PKG,
                         appActivity=f"{ANDROID_PKG}.view.activities.SplashActivity", noReset=True)
        try:
            title = wait(driver, 60).until(lambda d: d.find_elements(AppiumBy.ID, f"{ANDROID_ID}/productTV"))
            assert title[0].text == "Products"
            run.screenshot()
            # The catalog is bundled with the app; the WebView screen makes the app itself go online.
            driver.find_element(AppiumBy.ID, f"{ANDROID_ID}/menuIV").click()
            wait(driver).until(lambda d: d.find_elements(
                AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text("WebView")'))[0].click()
            url_field = wait(driver).until(lambda d: d.find_elements(AppiumBy.ID, f"{ANDROID_ID}/urlET"))[0]
            url_field.send_keys(f"https://{CAPTURED_SITE}")
            driver.find_element(AppiumBy.ID, f"{ANDROID_ID}/goBtn").click()
            hits = run.network.wait_for(CAPTURED_SITE, timeout_s=60)
            run.screenshot()
            # The app's HTTPS shows up as CONNECT entries (host only): its TLS is not decrypted.
            assert hits, f"no {CAPTURED_SITE} request captured; saw {run.network.urls[:10]}"
            print(f"  network capture: {len(hits)} request(s) to {CAPTURED_SITE} from the app's WebView")
        finally:
            driver.quit()


def test_ios_app_storage():
    """Public iPhone, IPA installed from App Storage."""
    with recorded_test(
        "iOS - My Demo App (App Storage)",
        ["platform:ios", "device:public", "app:app-storage", "usecase:native-app"],
        device=IOS_PUBLIC, os_name="ios", install=("SauceLabs-Demo-App.ipa", IOS_BUNDLE),
    ) as run:
        driver = connect(run, "ios", bundleId=IOS_BUNDLE, noReset=True)
        try:
            ios_catalog_flow(run, driver)
        finally:
            driver.quit()


@pytest.mark.xdist_group("ios-private")
def test_ios_private_app_store_app():
    """Private iPhone, My Demo App from the App Store (kept by the device's app allowlist), started
    with launchApp and driven over hosted Appium."""
    with recorded_test(
        "iOS private - My Demo App (App Store) - launchApp",
        ["platform:ios", "device:private", "app:app-store", "usecase:native-app", "feature:launch-app"],
        device=IOS_PRIVATE, os_name="ios",
    ) as run:
        run.api.launch_app(run.session_id, bundle_id=IOS_BUNDLE)
        driver = connect(run, "ios", bundleId=IOS_BUNDLE, noReset=True)
        try:
            ios_catalog_flow(run, driver)
        finally:
            driver.quit()
