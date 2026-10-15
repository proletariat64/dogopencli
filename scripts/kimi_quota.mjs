// Kimi subscription quota preflight for OCR; never sends a model prompt.
import { appendFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

function isQuotaError(text) {
  // Generic HTTP 429 rate limits are not proof of exhausted quota.
  return /\bcredit_exhausted\b|\b(?:credits?|quota)\s+(?:is\s+|are\s+|has been\s+)?(?:exhausted|depleted|exceeded|insufficient)\b|\binsufficient\s+(?:credits?|quota)\b|\b(?:out of|not enough|no remaining)\s+credits?\b/i.test(text);
}

function report(status, reason, quotaState = status, provider = 'OCR') {
  if (process.env.GITHUB_OUTPUT) {
    appendFileSync(process.env.GITHUB_OUTPUT,
      `status=${status}\nquota_state=${quotaState}\nrun_review=${status === 'available'}\n`);
  }
  if (process.env.GITHUB_STEP_SUMMARY) {
    appendFileSync(process.env.GITHUB_STEP_SUMMARY, `${provider} review: **${status}**. ${reason}\n\n`);
  }
  console.log(`${status === 'skipped' ? '::notice::' : ''}${provider} review: ${reason}`);
}

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
  let currentWindows = false;
  if (payload?.usages && typeof payload.usages === 'object') {
    for (const name of ['limit_5h', 'limit_7d', 'limit_month_total', 'limit_month_code']) {
      if (payload.usages[name] === undefined) continue;
      currentWindows = true;
      const ratio = nonnegativeNumber(payload.usages[name]?.used_ratio);
      if (ratio === null) invalid = true; else ratios.push(ratio);
    }
  }
  // The current API deliberately includes legacy compatibility fields too.
  // Its canonical usages windows are authoritative (matching the official client).
  if (currentWindows) {
    if (ratios.some(ratio => ratio >= 1)) return 'exhausted';
    return ratios.length && !invalid ? 'available' : 'unknown';
  }
  // Earlier usage responses use the usage + limits[].detail contract.
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
  let unavailableReason = `HTTP ${response.status}`;
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
    if (decision === 'unknown') {
      const allowed = new Set(['usage', 'limits', 'usages', 'data', 'result', 'used',
        'limit', 'remaining', 'detail', 'used_ratio', 'limit_5h', 'limit_7d',
        'limit_month_total', 'limit_month_code']);
      const fields = value => value && typeof value === 'object'
        ? Object.keys(value).filter(key => allowed.has(key)).sort() : [];
      unavailableReason += `; recognized fields ${JSON.stringify({
        root: fields(payload), usage: fields(payload?.usage),
        detail: fields(payload?.limits?.[0]?.detail),
        data: fields(payload?.data), usages: fields(payload?.usages),
      })}`;
    }
  }
  report(decision === 'available' ? 'available' : 'skipped', {
    available: 'Quota available; OCR review can start.',
    exhausted: 'Quota exhausted; no review was started.',
    unknown: `Quota unavailable (${unavailableReason}); no review was started.`,
  }[decision], decision, 'OCR');
  return decision;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    await checkKimiQuota();
  } catch {
    // Do not log provider payloads, credentials, or raw network exceptions.
    console.error('::error::OCR quota preflight failed; check KIMI_API_KEY and API connectivity.');
    process.exitCode = 1;
  }
}
