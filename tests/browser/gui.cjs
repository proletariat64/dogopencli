// Runs against a temporary installed leaf supplied by test_gui_browser.py.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const { chromium } = require(process.env.DOGOPENCLI_PLAYWRIGHT_MODULE);
const [url, manifestPath] = process.argv.slice(2);

(async () => {
  const browser = await chromium.launch({
    executablePath: process.env.DOGOPENCLI_CHROME || undefined,
    headless: true,
    args: ["--no-sandbox"],
  });
  try {
    const page = await browser.newPage({
      viewport: { width: 1600, height: 1000 },
    });
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto(url);
    const docs = page.getByRole("button", {
      name: "Edit documentation for sample",
      exact: true,
    });
    await docs.waitFor();
    assert.equal(await page.locator(".domain-card").count(), 4);
    const domainBox = await page.locator(".domain-nav").boundingBox();
    const leavesBox = await page.locator("#leaf-overview").boundingBox();
    assert.ok(domainBox.x + domainBox.width <= leavesBox.x + 1);
    assert.equal(await page.locator(".leaf").count(), 2);
    const sampleCard = page.locator(".leaf").filter({ has: docs });
    assert.ok((await sampleCard.innerText()).includes("2 · simulated"));
    assert.ok((await sampleCard.innerText()).includes("Success"));
    assert.ok((await sampleCard.innerText()).includes("Captured"));
    assert.ok(
      (await page.locator("#result-summary").innerText()).includes(
        "1 successful",
      ),
    );
    const shots = process.env.DOGOPENCLI_GUI_SCREENSHOTS;
    if (shots) {
      fs.mkdirSync(shots, { recursive: true });
      await page.screenshot({
        path: `${shots}/overview-desktop.png`,
        fullPage: true,
      });
    }
    // Navigation switches only the selected domain's leaves and preserves cards.
    await page
      .getByRole("button", { name: "View Collection queries", exact: true })
      .click();
    assert.equal(
      await page.locator("#selected-domain").innerText(),
      "Collection",
    );
    assert.equal(await page.locator(".leaf").count(), 1);
    assert.ok(
      (await page.locator("#leaves").innerText()).includes(
        "Collection-only summary",
      ),
    );
    assert.equal(await docs.count(), 0);
    await page
      .getByRole("button", { name: "Disable collection", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Enable collection", exact: true })
      .waitFor();
    assert.equal(
      await page.locator("#selected-domain").innerText(),
      "Collection",
    );
    assert.ok(
      (await page.locator("#leaves").innerText()).includes("Domain disabled"),
    );
    await page
      .getByRole("button", { name: "View FX queries", exact: true })
      .click();
    await page.locator("#no-matches").waitFor({ state: "visible" });
    assert.ok(
      (await page.locator("#no-matches").innerText()).includes(
        "No queries are installed",
      ),
    );
    assert.equal(await page.locator(".domain-card").count(), 4);
    await page
      .getByRole("button", { name: "View Payment queries", exact: true })
      .click();
    await docs.waitFor();
    // Search includes business descriptions, stays scoped to the selected domain.
    await page.getByRole("searchbox").fill("Second document");
    assert.equal(await page.locator(".leaf").count(), 1);
    assert.ok(
      (await page.locator("#leaves").innerText()).includes("No saved data"),
    );
    await page.getByRole("searchbox").fill("missing-leaf");
    await page.locator("#no-matches").waitFor({ state: "visible" });
    assert.equal(await docs.isVisible(), false);
    await page.getByRole("searchbox").fill("payment");
    await docs.waitFor({ state: "visible" });
    // Domain controls still persist through the existing service.
    await page.getByRole("button", { name: "Disable payment" }).click();
    await page.getByRole("button", { name: "Enable payment" }).waitFor();
    await page.getByRole("button", { name: "Enable payment" }).click();
    await page.getByRole("button", { name: "Disable payment" }).waitFor();
    assert.equal(await page.locator("#selected-domain").innerText(), "Payment");
    await docs.click();
    const summary = page.getByRole("textbox", {
      name: "Summary",
      exact: true,
    });
    await summary.waitFor();
    // Returning after a document switch clears a filter from the old domain.
    await page
      .getByLabel("Choose document")
      .selectOption(JSON.stringify(["collection", "sample_collection"]));
    await page.waitForFunction(
      () =>
        document.querySelector("#editor-title").textContent ===
        "sample_collection",
    );
    await page.getByRole("button", { name: "Back to domains" }).click();
    assert.equal(
      await page.locator("#selected-domain").innerText(),
      "Collection",
    );
    assert.equal(await page.getByRole("searchbox").inputValue(), "");
    const collectionDocs = page.getByRole("button", {
      name: "Edit documentation for sample_collection",
      exact: true,
    });
    assert.equal(
      await collectionDocs.evaluate(
        (button) => button === document.activeElement,
      ),
      true,
    );
    await page
      .getByRole("button", { name: "View Payment queries", exact: true })
      .click();
    await page.getByRole("searchbox").fill("Original summary");
    await docs.click();
    await summary.waitFor();
    const left = await page.locator(".edit-pane").boundingBox();
    const right = await page.locator(".preview-pane").boundingBox();
    assert.ok(left.x + left.width <= right.x + 1);
    assert.ok(Math.abs(left.width - right.width) < 80);
    assert.equal(await page.locator(".technical input").count(), 0);
    assert.ok(
      (await page.locator("#technical-declarations").textContent()).includes(
        "9007199254740993",
      ),
    );
    if (shots)
      await page.screenshot({
        path: `${shots}/editor-desktop.png`,
        fullPage: true,
      });
    const original = JSON.parse(fs.readFileSync(manifestPath));
    const injection = "<img src=x onerror=alert(1)> 文档草稿";
    await summary.fill(injection);
    await page.waitForFunction(
      () =>
        document.querySelector("#preview-state").textContent === "Up to date",
    );
    assert.ok(
      (await page.locator("#reading-preview").innerText()).includes(injection),
    );
    assert.equal(await page.locator("#reading-preview img").count(), 0);
    assert.deepEqual(JSON.parse(fs.readFileSync(manifestPath)), original);
    await page.getByRole("button", { name: "CLI text", exact: true }).click();
    assert.ok(
      (await page.locator("#documentation-preview").innerText()).includes(
        injection,
      ),
    );
    // Cancelling a destructive navigation preserves the draft.
    page.once("dialog", (dialog) => dialog.dismiss());
    await page.getByRole("button", { name: "Back to domains" }).click();
    assert.equal(await summary.inputValue(), injection);
    await page
      .getByRole("button", { name: "Save documentation", exact: true })
      .click();
    await page.waitForFunction(
      () => document.querySelector("#dirty-state").textContent === "Saved",
    );
    const saved = JSON.parse(fs.readFileSync(manifestPath));
    assert.equal(saved.summary, injection);
    for (const key of [
      "domain",
      "name",
      "adapter",
      "identity",
      "operations",
      "fields",
    ]) {
      assert.deepEqual(saved[key], original[key]);
    }
    // Saving returns a fresh manifest: subsequent inputs must edit that manifest.
    await summary.fill("同一文档的第二次编辑");
    await page.waitForFunction(
      () => document.querySelector("#dirty-state").textContent === "Unsaved",
    );
    await page
      .getByRole("button", { name: "Save documentation", exact: true })
      .click();
    await page.waitForFunction(
      () => document.querySelector("#dirty-state").textContent === "Saved",
    );
    assert.equal(
      JSON.parse(fs.readFileSync(manifestPath)).summary,
      "同一文档的第二次编辑",
    );
    await summary.fill(injection);
    await page
      .getByRole("button", { name: "Save documentation", exact: true })
      .click();
    await page.waitForFunction(
      () => document.querySelector("#dirty-state").textContent === "Saved",
    );
    // Overview uses the saved summary and renders it as text, never markup.
    await page.getByRole("button", { name: "Back to domains" }).click();
    await docs.waitFor();
    assert.ok((await sampleCard.innerText()).includes(injection));
    assert.equal(await page.locator("#leaves img").count(), 0);
    await docs.click();
    await summary.waitFor();
    // Switch documents, then reject switching away from an unsaved draft.
    await page
      .getByLabel("Choose document")
      .selectOption(JSON.stringify(["payment", "sample_two"]));
    await page.waitForFunction(
      () =>
        document.querySelector("#editor-title").textContent === "sample_two",
    );
    assert.equal(await summary.inputValue(), "Second document");
    await page
      .getByLabel("Choose document")
      .selectOption(JSON.stringify(["payment", "sample"]));
    await page.waitForFunction(
      () => document.querySelector("#editor-title").textContent === "sample",
    );
    assert.equal(await summary.inputValue(), injection);
    await summary.fill("Unsaved的切换测试");
    page.once("dialog", (dialog) => dialog.dismiss());
    await page
      .getByLabel("Choose document")
      .selectOption(JSON.stringify(["payment", "sample_two"]));
    assert.equal(await summary.inputValue(), "Unsaved的切换测试");
    assert.equal(
      await page.getByLabel("Choose document").inputValue(),
      JSON.stringify(["payment", "sample"]),
    );
    await summary.fill(injection);
    // Add/remove editable array items without changing technical arrays.
    await page.getByRole("button", { name: "Examples", exact: true }).click();
    await page
      .getByRole("button", { name: "Add example", exact: true })
      .click();
    await page
      .getByRole("textbox", { name: "Example title 2", exact: true })
      .fill("第二个示例");
    await page
      .getByRole("textbox", { name: "Example command 2", exact: true })
      .fill("dogopencli payment get sample 2");
    await page
      .getByRole("button", { name: "Remove example 2", exact: true })
      .click();
    assert.equal(
      await page
        .getByRole("textbox", { name: "Example title 2", exact: true })
        .count(),
      0,
    );
    // An older preview response must not replace a newer draft.
    let held = false;
    let markFirstPreviewStarted;
    const firstPreviewStarted = new Promise((resolve) => {
      markFirstPreviewStarted = resolve;
    });
    await page.route("**/preview", async (route) => {
      const response = await route.fetch();
      if (!held) {
        held = true;
        markFirstPreviewStarted();
        await new Promise((resolve) => setTimeout(resolve, 900));
      }
      await route.fulfill({ response });
    });
    await summary.fill("较早的草稿");
    await page.waitForFunction(
      () =>
        document.querySelector("#preview-state").textContent === "Updating…",
    );
    // Wait for the first request to enter the delayed route.
    await firstPreviewStarted;
    assert.ok(held);
    await summary.fill("最新的草稿");
    await page.waitForFunction(() =>
      document
        .querySelector("#documentation-preview")
        .textContent.includes("最新的草稿"),
    );
    await new Promise((resolve) => setTimeout(resolve, 1000));
    assert.ok(
      (await page.locator("#documentation-preview").textContent()).includes(
        "最新的草稿",
      ),
    );
    await page.unroute("**/preview");
    // Network failure keeps fields and draft editable, allowing a retry.
    await page.route("**/save", (route) =>
      route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ error: { message: "Temporary failure" } }),
      }),
    );
    await page
      .getByRole("button", { name: "Save documentation", exact: true })
      .click();
    await page.waitForFunction(() =>
      document
        .querySelector("#editor-status")
        .textContent.includes("Save failed"),
    );
    assert.equal(await summary.inputValue(), "最新的草稿");
    assert.equal(await summary.isEnabled(), true);
    await page.unroute("**/save");
    // A competing write is rejected by the real revision contract.
    const external = JSON.parse(fs.readFileSync(manifestPath));
    external.summary = "另一个编辑器保存的内容";
    fs.writeFileSync(manifestPath, JSON.stringify(external));
    await page
      .getByRole("button", { name: "Save documentation", exact: true })
      .click();
    await page.waitForFunction(() =>
      document.querySelector("#editor-status").textContent.includes("reload"),
    );
    assert.equal(await summary.inputValue(), "最新的草稿");
    assert.equal(
      JSON.parse(fs.readFileSync(manifestPath)).summary,
      external.summary,
    );
    page.once("dialog", (dialog) => dialog.accept());
    await page.getByRole("button", { name: "Reload", exact: true }).click();
    await page.waitForFunction(
      () =>
        document.querySelector('[aria-label="Summary"]').value ===
        "另一个编辑器保存的内容",
    );
    if (shots)
      await page.screenshot({
        path: `${shots}/editor-saved.png`,
        fullPage: true,
      });
    // Mobile retains all toolbar controls and uses stacked edit/preview panes.
    await page.setViewportSize({ width: 390, height: 844 });
    assert.ok(
      await page
        .getByRole("button", { name: "Save documentation", exact: true })
        .isVisible(),
    );
    assert.ok(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    );
    const mobileLeft = await page.locator(".edit-pane").boundingBox();
    const mobileRight = await page.locator(".preview-pane").boundingBox();
    assert.ok(mobileRight.y >= mobileLeft.y + mobileLeft.height - 1);
    await page.getByRole("button", { name: "Back to domains" }).click();
    assert.ok(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    );
    assert.equal(
      await page
        .getByRole("button", {
          name: "Edit documentation for sample",
          exact: true,
        })
        .evaluate((button) => button === document.activeElement),
      true,
    );
    assert.ok(
      (await page.locator("#leaves").innerText()).includes(external.summary),
    );
    if (shots)
      await page.screenshot({
        path: `${shots}/overview-mobile.png`,
        fullPage: true,
      });
    assert.deepEqual(errors, []);
    console.log(
      "GUI browser acceptance passed: search, domain toggles, split layout, safe text, draft preview, save, arrays, stale previews, failure recovery, conflicts, reload, mobile.",
    );
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
