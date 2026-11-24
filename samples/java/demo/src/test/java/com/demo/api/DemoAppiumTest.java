package com.demo.api;

import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInfo;
import org.junit.jupiter.api.extension.ExtendWith;
import org.junit.jupiter.api.extension.ExtensionContext;
import org.junit.jupiter.api.extension.TestWatcher;

import java.io.IOException;
import java.net.URI;
import java.net.URL;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Base64;
import java.util.List;

import io.appium.java_client.android.AndroidDriver;

import org.openqa.selenium.MutableCapabilities;
import org.openqa.selenium.UsernameAndPassword;
import org.openqa.selenium.remote.http.ClientConfig;

import static org.junit.jupiter.api.Assertions.assertFalse;

/**
 * Suite-per-session: one device is reserved for the whole class, and each @Test is recorded as
 * its own job in Real Device Access API > Test Results (startTest / endTest), with video,
 * screenshots, device log, Appium log and HAR.
 *
 * Configuration (environment): SAUCE_USERNAME, SAUCE_ACCESS_KEY, SAUCE_REGION (default
 * eu-central-1), RDC_ANDROID_PUBLIC (device regex), SAUCE_BUILD, SAUCE_TAGS (extra tags, comma separated).
 */
@ExtendWith(DemoAppiumTest.Verdict.class)
public class DemoAppiumTest {

	private static String sessionId; // The ID for our reserved device session
	private static URL appiumUrl;    // The Appium URL, reused for all tests

	private static final String REGION = env("SAUCE_REGION", "eu-central-1");
	private static final String BASE_URL = "https://api." + REGION + ".saucelabs.com";
	private static final String SAUCE_USERNAME = env("SAUCE_USERNAME", null);
	private static final String SAUCE_ACCESS_KEY = env("SAUCE_ACCESS_KEY", null);
	private static final String DEVICE = env("RDC_ANDROID_PUBLIC", "Google_Pixel_[6-9].*_real");
	private static final String BUILD = env("SAUCE_BUILD", "real-device-api-" + LocalDate.now());

	private static final HttpClient client = HttpClient.newBuilder()
			.version(HttpClient.Version.HTTP_2)
			.connectTimeout(Duration.ofSeconds(20))
			.build();

	private AndroidDriver driver;

	/**
	 * Reserves a device via the Access API and starts a persistent Appium server for it.
	 * Runs once before any @Test methods.
	 */
	@BeforeAll
	public static void setupSuite() throws Exception {
		if (SAUCE_USERNAME == null || SAUCE_ACCESS_KEY == null) {
			throw new IllegalStateException("Set SAUCE_USERNAME and SAUCE_ACCESS_KEY");
		}
		var createSessionRequestBody = new JSONObject()
				.put("device", new JSONObject().put("os", "android").put("deviceName", DEVICE))
				.put("configuration", new JSONObject().put("sessionDuration", "PT1H"))
				.toString();
		sessionId = createSession(createSessionRequestBody);
		waitForSessionToBeActive(sessionId);

		var startAppiumServerResponse = POST("/rdc/v2/sessions/%s/appiumserver".formatted(sessionId),
				"{ \"appiumVersion\": \"latest\" }");
		appiumUrl = new URL(startAppiumServerResponse.getString("url"));
	}

	/** Releases the device after all tests are done. */
	@AfterAll
	public static void tearDownSuite() throws IOException, InterruptedException {
		if (sessionId != null) {
			System.out.println("Releasing Device Session: " + sessionId);
			DELETE("/rdc/v2/sessions/" + sessionId);
		}
	}

	/**
	 * Starts a recorded test. Every artifact has to be requested, otherwise its tab in Test Results
	 * stays empty. The Appium server is already running, so the Appium log is attached too.
	 */
	@BeforeEach
	public void startRecordedTest(TestInfo info) throws Exception {
		List<String> tags = new ArrayList<>(List.of("repo:real-device-api", "lang:java", "framework:appium",
				"framework:junit5", "api:access-api", "platform:android", "device:public", "browser:chrome",
				"usecase:web-app", "usecase:suite-per-session"));
		for (String t : env("SAUCE_TAGS", "").split(",")) {
			if (!t.isBlank()) tags.add(t.trim());
		}
		var body = new JSONObject()
				.put("testName", "Java suite-per-session - " + info.getDisplayName().replace("()", ""))
				.put("build", BUILD)
				.put("tags", new JSONArray(tags))
				.put("artifacts", new JSONObject()
						.put("video", true).put("screenshots", true).put("deviceLogs", true)
						.put("networkCapture", true).put("appiumLogs", true));
		var jobId = POST("/rdc/v2/sessions/%s/startTest".formatted(sessionId), body.toString()).getString("jobId");
		System.out.println("Test Results: " + BASE_URL.replace("://api.", "://app.") + "/tests/" + jobId);

		var capabilities = new MutableCapabilities();
		capabilities.setCapability("browserName", "Chrome");
		capabilities.setCapability("appium:newCommandTimeout", 300);
		var config = ClientConfig.defaultConfig()
				.baseUrl(appiumUrl)
				.readTimeout(Duration.ofMinutes(5))
				.authenticateAs(new UsernameAndPassword(SAUCE_USERNAME, SAUCE_ACCESS_KEY));
		driver = new AndroidDriver(config, capabilities);
	}

	/** Quits this test's Appium client; the device session stays open for the next test. */
	@AfterEach
	public void quitDriver() {
		if (driver != null) driver.quit();
	}

	// --- Rapid-Fire Tests ---
	// Each of these methods runs back-to-back on the SAME device.

	@Test
	public void first_test() throws Exception {
		driver.get("https://www.saucelabs.com");
		assertFalse(driver.getTitle().isBlank(), "page has no title");
		POST("/rdc/v2/sessions/%s/device/takeScreenshot".formatted(sessionId), "");
	}

	@Test
	public void second_test() throws Exception {
		driver.get("https://www.saucedemo.com");
		assertFalse(driver.findElements(org.openqa.selenium.By.cssSelector("#login-button")).isEmpty(),
				"no login button");
		POST("/rdc/v2/sessions/%s/device/takeScreenshot".formatted(sessionId), "");
	}

	/** Ends the recorded test with the JUnit verdict (runs after @AfterEach). */
	public static class Verdict implements TestWatcher {
		private static void end(boolean passed) {
			try {
				POST("/rdc/v2/sessions/%s/endTest".formatted(sessionId),
						new JSONObject().put("status", passed ? "passed" : "failed").toString());
				System.out.println("Recorded test ended: " + (passed ? "passed" : "failed"));
			} catch (Exception e) {
				System.out.println("endTest failed: " + e);
			}
		}

		@Override
		public void testSuccessful(ExtensionContext context) {
			end(true);
		}

		@Override
		public void testFailed(ExtensionContext context, Throwable cause) {
			end(false);
		}

		@Override
		public void testAborted(ExtensionContext context, Throwable cause) {
			end(false);
		}
	}

	// ... Helper methods

	private static String env(String name, String fallback) {
		var v = System.getenv(name);
		return v == null || v.isBlank() ? fallback : v;
	}

	/** Reserves a device, retrying while none matching is free. */
	private static String createSession(String body) throws Exception {
		for (int i = 0; i < 45; i++) {
			var response = send(request("/rdc/v2/sessions").header("Content-Type", "application/json")
					.POST(HttpRequest.BodyPublishers.ofString(body)));
			if (response.statusCode() == 200 || response.statusCode() == 201) {
				var id = new JSONObject(response.body()).getString("id");
				System.out.println("Device session: " + id);
				return id;
			}
			System.out.println("No device free yet (HTTP " + response.statusCode() + "), retrying in 20s");
			Thread.sleep(20000);
		}
		throw new Exception("No device became available");
	}

	private static void waitForSessionToBeActive(String sessionId) throws Exception {
		System.out.println("Waiting for session active...");
		for (int i = 0; i < 120; i++) {
			var currentState = GET("/rdc/v2/sessions/" + sessionId).getString("state");
			if ("ACTIVE".equals(currentState)) {
				System.out.println("Session is now ACTIVE.");
				return;
			}
			if ("ERRORED".equals(currentState) || "CLOSED".equals(currentState)) {
				throw new Exception("Session ended up " + currentState);
			}
			Thread.sleep(5000);
		}
		throw new Exception("Session did not become active");
	}

	private static HttpRequest.Builder request(String apiUrl) {
		String credentials = SAUCE_USERNAME + ":" + SAUCE_ACCESS_KEY;
		String encodedAuth = Base64.getEncoder().encodeToString(credentials.getBytes());
		return HttpRequest.newBuilder()
				.uri(URI.create(BASE_URL + apiUrl))
				.timeout(Duration.ofSeconds(120))
				.header("Authorization", "Basic " + encodedAuth);
	}

	private static HttpResponse<String> send(HttpRequest.Builder builder) throws IOException, InterruptedException {
		return client.send(builder.build(), HttpResponse.BodyHandlers.ofString());
	}

	private static JSONObject toJson(HttpRequest.Builder builder, String apiUrl) throws IOException, InterruptedException {
		var response = send(builder);
		if (response.statusCode() >= 300) {
			throw new IOException(apiUrl + " -> HTTP " + response.statusCode() + ": " + response.body());
		}
		var body = response.body();
		return body == null || body.isBlank() || !body.trim().startsWith("{") ? new JSONObject() : new JSONObject(body);
	}

	private static JSONObject POST(String apiUrl, String requestBody) throws IOException, InterruptedException {
		return toJson(request(apiUrl).header("Content-Type", "application/json")
				.POST(HttpRequest.BodyPublishers.ofString(requestBody)), apiUrl);
	}

	private static JSONObject GET(String apiUrl) throws IOException, InterruptedException {
		return toJson(request(apiUrl).GET(), apiUrl);
	}

	private static JSONObject DELETE(String apiUrl) throws IOException, InterruptedException {
		return toJson(request(apiUrl).DELETE(), apiUrl);
	}
}
