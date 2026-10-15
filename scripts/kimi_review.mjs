// Kimi CLI fallback only: usage preflight does not send a model prompt.
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { isQuotaError, report, runReview } from './qoder_review.mjs';

export const KIMI_BASE_URL = 'https://api.kimi.com/coding/v1';

function nonnegativeNumber(value) {
  if (typeof value !== 'number' && typeof value !== 'string') return null;
  if (typeof value === 'string' && !value.trim()) return null;
  const number = Number(value);
  return Number.isFinite(number) && number >= 0 ? number : null;
}

export function kimiQuotaDecision(payload) {
  const ratios = [];
  let invalid = false;
  if (payload?.usages && typeof payload.usages === 'object') {
    for (const name of ['limit_5h', 'limit_7d', 'limit_month_total', 'limit_month_code']) {
      if (payload.usages[name] === undefined) continue;
      const ratio = nonnegativeNumber(payload.usages[name]?.used_ratio);
      if (ratio === null) invalid = true; else ratios.push(ratio);
    }
  }
  // The pinned CLI also handles the earlier usage + limits[].detail contract.
  const rows = [];
  if (payload?.usage !== undefined) rows.push(payload.usage);
  if (payload?.limits !== undefined) {
    if (!Array.isArray(payload.limits)) invalid = true;
    else rows.push(...payload.limits.map(row => row?.detail));
  }
  for (const row of rows) {
    const used = nonnegativeNumber(row?.used);
    const limit = nonnegativeNumber(row?.limit);
    if (used === null || limit === null || limit === 0) invalid = true;
    else ratios.push(used / limit);
  }
  if (ratios.some(ratio => ratio >= 1)) return 'exhausted';
  // Do not infer availability from wallet money or an absent quota window.
  return ratios.length && !invalid ? 'available' : 'unknown';
}

export async function checkKimiQuota(fetchUsage = fetch) {
  const key = process.env.KIMI_API_KEY;
  if (!key) throw new Error('KIMI_API_KEY is missing');
  const response = await fetchUsage(`${KIMI_BASE_URL}/usages`, {
    headers: { Authorization: `Bearer ${key}`, Accept: 'application/json' },
    signal: AbortSignal.timeout(10_000),
    redirect: 'error',
  });
  let decision;
  if (response.status === 404) {
    decision = 'unknown';
  } else if (!response.ok) {
    // Authentication and generic 429s remain failures; never echo response bodies.
    const payload = await response.json().catch(() => null);
    const diagnostic = payload?.error?.message;
    if ([403, 429].includes(response.status) && typeof diagnostic === 'string' && isQuotaError(diagnostic)) {
      decision = 'exhausted';
    } else {
      throw new Error(`Kimi quota request failed (HTTP ${response.status})`);
    }
  } else {
    let payload;
    try { payload = await response.json(); } catch { payload = null; }
    decision = kimiQuotaDecision(payload);
  }
  report(decision === 'available' ? 'available' : 'skipped', {
    available: 'Quota available; fallback review can start.',
    exhausted: 'Quota exhausted; no review was started.',
    unknown: 'Quota unavailable; no review was started.',
  }[decision], decision, 'Kimi');
  return decision;
}

export function prepareKimi(home) {
  if (!home) throw new Error("KIMI_CODE_HOME is missing");
  mkdirSync(home, { recursive: true, mode: 0o700 });
  writeFileSync(join(home, 'config.toml'), `
default_model = "k3"
telemetry = false

[providers.kimi]
type = "kimi"
base_url = "${KIMI_BASE_URL}"
api_key_env = "KIMI_API_KEY"

[models.k3]
provider = "kimi"
model = "k3"
max_context_size = 1048576
capabilities = ["thinking", "always_thinking", "image_in", "tool_use"]
support_efforts = ["low", "high", "max"]
default_effort = "high"

[thinking]
enabled = true
effort = "high"

[secondary_model]
default_model = "k3"
default_effort = "high"
force = true
`, { mode: 0o600 });
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    if (process.argv[2] === 'check') {
      await checkKimiQuota();
    } else if (process.argv[2] === 'review') {
      prepareKimi(process.env.KIMI_CODE_HOME);
      if (!process.env.REVIEW_PROMPT || !process.env.REVIEW_REPORT) throw new Error("Review prompt/report paths are missing");
      await runReview("kimi", {
        provider: "Kimi",
        prompt: readFileSync(process.env.REVIEW_PROMPT, "utf8"),
        reportPath: process.env.REVIEW_REPORT,
      });
    } else {
      throw new Error('Expected check or review');
    }
  } catch (error) {
    let safe = error.message;
    for (const key of ['KIMI_API_KEY', 'GITHUB_TOKEN', 'QODER_PERSONAL_ACCESS_TOKEN']) {
      if (process.env[key]) safe = safe.replaceAll(process.env[key], '[REDACTED]');
    }
    safe = safe.replaceAll('%', '%25').replaceAll('\r', '%0D').replaceAll('\n', '%0A');
    console.log(`::error::Kimi review: ${safe}`);
    process.exitCode = 1;
  }
}
