# Real Device Access API v2
> This API is currently under active development and is subject to change. Access is currently restricted to early adopters. If you would like access please get in contact with you Sauce Labs representative.

This repository contains documentation for the Sauce Labs Real Device API. This API provides remote access to our pool of real devices, allowing you to automate them using the provided HTTP and WebSocket interfaces.


## Test suite (this fork)

Tests that run on Sauce Labs real devices in the **EU DC** (`eu-central-1`) through the Access API. Each test
reserves a device, starts the hosted Appium server, and is recorded with `startTest`/`endTest`, so it shows up
in **Real Device Access API > Test Results** with video, screenshots, device log, Appium log and HAR file.

| Test | Device | App | Features |
|---|---|---|---|
| `test_android_app_storage_network_capture` | public Android | My Demo App APK from App Storage (instrumented) | network capture |
| `test_ios_app_storage` | public iPhone | My Demo App IPA from App Storage | |
| `test_ios_private_app_store_app` | private `iPhone_SE_2022_26_POC25_txl1` | My Demo App from the App Store, started with `launchApp` | |
| `test_android_web_network_capture` | public Android, Chrome | saucedemo.com | network capture |
| `test_ios_private_web` | private iPhone, Safari | saucedemo.com | |
| `test_android_private_web_tunnel_network_capture` | private `Google_Pixel_7_POC33`, Chrome | site on this machine | Sauce Connect, network capture |
| `test_ios_public_web_tunnel` | public iPhone, Safari | site on this machine | Sauce Connect |
| `samples/java/demo` `DemoAppiumTest` (2 tests) | public Android, Chrome | saucelabs.com, saucedemo.com | suite-per-session |

The Python tests are in [tests/python](tests/python) and the Java sample in [samples/java/demo](samples/java/demo).
Every job is tagged `repo:real-device-api` plus `platform:*`, `device:public|private`, `app:app-storage|app-store`,
`usecase:native-app|web-app`, `browser:*`, `lang:*` and, where they are used and checked,
`feature:network-capture` and `feature:sauce-connect`. Extra tags can be added with `SAUCE_TAGS`; the daily cron
run adds `ci:cron`.

```bash
export SAUCE_USERNAME=... SAUCE_ACCESS_KEY=...   # or `export` them in ~/.zshrc
scripts/run_sauce_tests.sh                        # Python suite + Java sample
scripts/run_sauce_tests.sh python                 # only the Python suite (or: java)
```

Requirements: Python 3.11+, Java 17+ with Maven, and Sauce Connect 5 (`sc`) for the tunnel tests.

Things to know:
- `startTest` must request every artifact (`video`, `screenshots`, `deviceLogs`, `networkCapture`, `appiumLogs`),
  otherwise the matching tab in Test Results stays empty. Start the hosted Appium server *before* `startTest` so its
  log is attached. The `networkCapture` artifact only attaches the HAR: capture itself needs `enableNetworkCapture`.
- The tests that use network capture check the captured traffic live on the session's events WebSocket, before
  `endTest`, so a test with no captured traffic fails. The native app's HTTPS shows up as `CONNECT` entries (host
  only); Chrome traffic is fully decrypted.
- Tunnel tests open `https://rdc-api.test/`. Only that host goes through the tunnel, and Sauce Connect hands it to a
  local server that serves a page with a per-run token. Devices never send `localhost` through a tunnel.
- On some iOS 26 devices Safari stays on its Start Page after `driver.get`; the tests then open the page with the
  Access API's `openUrl` and switch to the Safari webview that shows it.
- App Storage apps are picked by file name *and* bundle ID, because other suites upload files with the same name
  and a different app inside.
- Devices can be changed with `RDC_ANDROID_PUBLIC`, `RDC_IOS_PUBLIC`, `RDC_ANDROID_PRIVATE`, `RDC_IOS_PRIVATE`
  (regexes on the device descriptor).

## Overview
The API consists of:
- **HTTP API:** For session management and most device interactions.
- **WebSocket API:** For streaming live device data, such as logs, screen recordings, and network traffic.

## HTTP API
The HTTP API is used for creating and managing device sessions, as well as performing certain device operations. Full details are available in the [RDC Access API specification](open_api_specification.yaml).

## WebSocket API
The WebSocket API provides real-time streams of data from your device sessions. There are two primary WebSocket endpoints:

### AlternativeIO Socket
- **Purpose:** Streams live screen recordings from your device session.
- **Data format:** Each message is a screenshot in MJPEG format.
- **Usage:** Connect to this socket to receive a continuous stream of device screenshots for monitoring or recording purposes.

### Companion Socket
- **Purpose:** Streams device logs, appium logs and other real-time device events.
- **Data format:** JSON messages. Each message includes a `type` field to distinguish between log messages and other events. By default, you will receive `device.log.message` in this socket. If you start an appium server or network capture then `appium.log.message` or `device.har.entry` respectively will be written to the socket.
- **Usage:** Connect to this socket to receive live logs and event notifications from your device session.

#### Example: Log Message
```json
{
    "type":"device.log.message",
    "processId":876,
    "level":"INFO",
    "timestamp":"2025-05-07 18:11:20.000",
    "message":"2025-05-07 18:11:20.000 INFO: trustd(libxpc.dylib)[..]"
}
```

## Getting Started

For detailed usage examples and a step-by-step guide to interacting with the Sauce Labs Real Devices Access API v2, 
please see our [Integration Guide](INTEGRATION_GUIDE.md).

## Local Appium

For a quick start running Appium locally, please follow [our guide](./LOCAL_APPIUM.md) on the topic.

## Sauce Lab's Hosted Appium Server

Use your devices more efficiently and decrease the runtime of your Appium test suite. Our RDC Access API lets you allocate a device
**once** and run tests back-to-back, cutting out repetitive setup and wait times.

For a quick start, please see **[Faster, Smarter Appium Testing with RDC Access API Sessions.](./SAUCE_LABS_HOSTED_APPIUM.md)**.


## Real-Time Debugging

Tap into the device's live stream to see system logs, Appium logs, and network traffic in real-time.
Check out our **[Companion Socket Guide](./COMPANION_SOCKET.md)** to learn how to filter and capture exactly what you need.