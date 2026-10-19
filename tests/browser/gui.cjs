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
    await docs.click();
    const summary = page.getByRole("textbox", {
      name: "一句话简介",
      exact: true,
    });
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
    const original = JSON.parse(fs.readFileSync(manifestPath));
    const injection = "<img src=x onerror=alert(1)> 文档草稿";
    await summary.fill(injection);
    await page.waitForFunction(
      () => document.querySelector("#preview-state").textContent === "已同步",
    );
    assert.ok(
      (await page.locator("#reading-preview").innerText()).includes(injection),
    );
    assert.equal(await page.locator("#reading-preview img").count(), 0);
    assert.deepEqual(JSON.parse(fs.readFileSync(manifestPath)), original);
    await page.getByRole("button", { name: "CLI 文本", exact: true }).click();
    assert.ok(
      (await page.locator("#documentation-preview").innerText()).includes(
        injection,
      ),
    );
    // Cancelling a destructive navigation preserves the draft.
    page.once("dialog", (dialog) => dialog.dismiss());
    await page.getByRole("button", { name: "返回 Domains" }).click();
    assert.equal(await summary.inputValue(), injection);
    await page.getByRole("button", { name: "保存文档", exact: true }).click();
    await page.waitForFunction(
      () => document.querySelector("#dirty-state").textContent === "已保存",
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
      () => document.querySelector("#dirty-state").textContent === "未保存",
    );
    await page.getByRole("button", { name: "保存文档", exact: true }).click();
    await page.waitForFunction(
      () => document.querySelector("#dirty-state").textContent === "已保存",
    );
    assert.equal(
      JSON.parse(fs.readFileSync(manifestPath)).summary,
      "同一文档的第二次编辑",
    );
    await summary.fill(injection);
    await page.getByRole("button", { name: "保存文档", exact: true }).click();
    await page.waitForFunction(
      () => document.querySelector("#dirty-state").textContent === "已保存",
    );
    // Switch documents, then reject switching away from an unsaved draft.
    await page
      .getByLabel("选择文档")
      .selectOption(JSON.stringify(["payment", "sample_two"]));
    await page.waitForFunction(
      () =>
        document.querySelector("#editor-title").textContent === "sample_two",
    );
    assert.equal(await summary.inputValue(), "Second document");
    await page
      .getByLabel("选择文档")
      .selectOption(JSON.stringify(["payment", "sample"]));
    await page.waitForFunction(
      () => document.querySelector("#editor-title").textContent === "sample",
    );
    assert.equal(await summary.inputValue(), injection);
    await summary.fill("未保存的切换测试");
    page.once("dialog", (dialog) => dialog.dismiss());
    await page
      .getByLabel("选择文档")
      .selectOption(JSON.stringify(["payment", "sample_two"]));
    assert.equal(await summary.inputValue(), "未保存的切换测试");
    assert.equal(
      await page.getByLabel("选择文档").inputValue(),
      JSON.stringify(["payment", "sample"]),
    );
    await summary.fill(injection);
    // Add/remove editable array items without changing technical arrays.
    await page.getByRole("button", { name: "示例", exact: true }).click();
    await page.getByRole("button", { name: "添加示例", exact: true }).click();
    await page
      .getByRole("textbox", { name: "示例标题 2", exact: true })
      .fill("第二个示例");
    await page
      .getByRole("textbox", { name: "示例命令 2", exact: true })
      .fill("dogopencli payment get sample 2");
    await page.getByRole("button", { name: "移除示例 2", exact: true }).click();
    assert.equal(
      await page
        .getByRole("textbox", { name: "示例标题 2", exact: true })
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
        document.querySelector("#preview-state").textContent === "正在更新…",
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
    await page.getByRole("button", { name: "保存文档", exact: true }).click();
    await page.waitForFunction(() =>
      document.querySelector("#editor-status").textContent.includes("保存失败"),
    );
    assert.equal(await summary.inputValue(), "最新的草稿");
    assert.equal(await summary.isEnabled(), true);
    await page.unroute("**/save");
    // A competing write is rejected by the real revision contract.
    const external = JSON.parse(fs.readFileSync(manifestPath));
    external.summary = "另一个编辑器保存的内容";
    fs.writeFileSync(manifestPath, JSON.stringify(external));
    await page.getByRole("button", { name: "保存文档", exact: true }).click();
    await page.waitForFunction(() =>
      document.querySelector("#editor-status").textContent.includes("reload"),
    );
    assert.equal(await summary.inputValue(), "最新的草稿");
    assert.equal(
      JSON.parse(fs.readFileSync(manifestPath)).summary,
      external.summary,
    );
    page.once("dialog", (dialog) => dialog.accept());
    await page.getByRole("button", { name: "重新载入", exact: true }).click();
    await page.waitForFunction(
      () =>
        document.querySelector('[aria-label="一句话简介"]').value ===
        "另一个编辑器保存的内容",
    );
    // Mobile retains all toolbar controls and uses stacked edit/preview panes.
    await page.setViewportSize({ width: 390, height: 844 });
    assert.ok(
      await page
        .getByRole("button", { name: "保存文档", exact: true })
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
    await page.getByRole("button", { name: "返回 Domains" }).click();
    assert.ok(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    );
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
