// Real GUI with task-owned synthetic storage, never a signed-in browser profile.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const { chromium } = require(process.env.DOGOPENCLI_PLAYWRIGHT_MODULE);
const [url, scenario] = process.argv.slice(2);
(async () => {
  const browser = await chromium.launch({
    executablePath: process.env.DOGOPENCLI_CHROME,
    headless: true,
    args: ["--no-sandbox"],
  });
  try {
    const page = await browser.newPage({
      viewport: { width: 1440, height: 1050 },
    });
    const errors = [];
    const external = [];
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("request", (request) => {
      if (!request.url().startsWith(url + "/")) external.push(request.url());
    });
    await page.goto(url);
    await page.locator(".domain-card").first().waitFor();
    assert.equal(
      await page.locator("#system-entry").innerText(),
      "System\ninfo & storage",
    );
    assert.equal(
      await page.locator(".console-section>p").innerText(),
      "Console",
    );
    assert.equal(
      await page.locator("#system-entry svg,#system-entry img").count(),
      0,
    );
    await page
      .getByRole("button", { name: "System info & storage", exact: true })
      .click();
    await page
      .getByRole("heading", { name: "System overview", exact: true })
      .waitFor();
    assert.equal(await page.locator("#leaf-overview").isVisible(), false);
    assert.equal(
      await page.locator("#system-entry").getAttribute("aria-pressed"),
      "true",
    );
    assert.equal(await page.locator(".system-sections>section").count(), 4);
    const body = await page.locator("#system-content").innerText();
    for (const secret of [
      "hidden-secret",
      "private-business-record",
      "cached-private-record",
      "unrelated-private-record",
      "secret-scope",
    ])
      assert.ok(!body.includes(secret));
    assert.ok(body.includes("catalog estimates"));
    assert.equal(await page.locator("#system-refresh").isEnabled(), true);
    if (scenario === "populated") {
      await page.getByText("Leaf snapshots", { exact: true }).click();
      const cache = page.getByRole("table", {
        name: "Leaf snapshots",
        exact: true,
      });
      assert.match(await cache.innerText(), /payment\.sample/);
      assert.match(await cache.innerText(), /Expired/);
      await page
        .getByRole("combobox", { name: "Leaf snapshots status" })
        .selectOption("fresh");
      assert.match(await cache.innerText(), /No matching metadata/);
      await page
        .getByRole("combobox", { name: "Leaf snapshots status" })
        .selectOption("stale");
      await page.getByText("Dataset metadata", { exact: true }).click();
      const datasets = page.getByRole("table", {
        name: "Dataset metadata",
        exact: true,
      });
      assert.match(await datasets.innerText(), /payment\.retired/);
      await page
        .getByRole("combobox", { name: "Dataset metadata status" })
        .selectOption("retained");
      assert.ok(!(await datasets.innerText()).includes("payment.sample"));
      await page
        .getByRole("searchbox", { name: "Dataset metadata search" })
        .fill("not-present");
      assert.match(await datasets.innerText(), /No matching metadata/);
      await page
        .getByRole("searchbox", { name: "Dataset metadata search" })
        .fill("");
    } else if (scenario === "busy") {
      assert.match(body, /Busy/);
      assert.match(body, /metadata is unavailable/);
    } else {
      assert.match(body, /No List snapshots/);
      assert.match(body, /No registered datasets/);
    }
    const response = page.waitForResponse(
      (r) => r.url() === url + "/api/system",
    );
    await page
      .getByRole("button", { name: "Reload information", exact: true })
      .click();
    await response;
    await page.getByText("Read-only · updated", { exact: true }).waitFor();
    const shots = process.env.DOGOPENCLI_GUI_SCREENSHOTS;
    if (shots) {
      fs.mkdirSync(shots, { recursive: true });
      await page.screenshot({
        path: shots + "/system-" + scenario + "-desktop.png",
        fullPage: true,
      });
    }
    await page
      .getByRole("button", { name: "View Payment queries", exact: true })
      .click();
    assert.equal(await page.locator("#system-overview").isVisible(), false);
    assert.equal(await page.locator("#leaf-overview").isVisible(), true);
    if (scenario !== "empty") {
      await page
        .getByRole("button", {
          name: "Edit documentation for sample",
          exact: true,
        })
        .click();
      await page
        .getByRole("button", { name: "Back to domains", exact: true })
        .click();
      assert.equal(await page.locator("#leaf-overview").isVisible(), true);
    }
    await page
      .getByRole("button", { name: "System info & storage", exact: true })
      .click();
    await page.getByText("Read-only · updated", { exact: true }).waitFor();
    await page.setViewportSize({ width: 390, height: 844 });
    assert.ok(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    );
    if (shots)
      await page.screenshot({
        path: shots + "/system-" + scenario + "-mobile.png",
        fullPage: true,
      });
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    console.log(
      "System " +
        scenario +
        ": navigation, safe metadata, reload, layout and documentation return passed",
    );
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
