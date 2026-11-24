import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))

from rdc.client import Credentials  # noqa: E402
from rdc.tunnel import LocalSite, SauceConnect  # noqa: E402

# Devices (regexes on the device descriptor). Public devices in the EU DC end in "_real".
ANDROID_PUBLIC = os.environ.get("RDC_ANDROID_PUBLIC", r"Google_Pixel_[6-9].*_real")
IOS_PUBLIC = os.environ.get("RDC_IOS_PUBLIC", r"iPhone_1[3-6].*_real")
ANDROID_PRIVATE = os.environ.get("RDC_ANDROID_PRIVATE", "Google_Pixel_7_POC33")
# Has My Demo App (com.saucelabs.mydemo.app.ios) from the App Store in its app allowlist.
IOS_PRIVATE = os.environ.get("RDC_IOS_PRIVATE", "iPhone_SE_2022_26_POC25_txl1")


@pytest.fixture(scope="session")
def tunnel():
    """A local HTTPS site and a Sauce Connect 5 tunnel to it, shared by the tunnel tests."""
    site = LocalSite()
    sc = SauceConnect(site, Credentials.from_env().region)
    try:
        sc.wait_ready()
        print(f"\n  Sauce Connect tunnel '{sc.name}' is up", flush=True)
        yield sc, site
    finally:
        sc.stop()
        site.stop()
