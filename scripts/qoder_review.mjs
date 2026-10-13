// Quota skips are explicit; configuration, authentication and other failures stay red.
import { spawn } from 'node:child_process';
import { appendFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

export function quotaDecision(usage) {
  if (usage?.isQuotaExceeded === true) return 'exhausted';
  const buckets = [usage?.userQuota, usage?.addOnQuota];
  if (usage?.orgResourcePackage?.available === true) {
    buckets.push(usage.orgResourcePackage);
  }
  if (buckets.some(bucket => Number.isFinite(bucket?.remaining) && bucket.remaining > 0)) {
    return 'available';
  }
  if (usage?.isQuotaExceeded === false) return 'available';
  // Missing quota fields are not zero. Do not start a paid task without a check.
  return 'unknown';
}

export function isQuotaError(text) {
  // credit_exhausted is a Qoder terminal-credit notification. QUOTA_EXCEEDED
  // alone is ambiguous: the CLI also uses it for generic HTTP 429 responses.
  return /\bcredit_exhausted\b|\b(?:credits?|quota)\s+(?:is\s+|are\s+|has been\s+)?(?:exhausted|depleted|exceeded|insufficient)\b|\binsufficient\s+(?:credits?|quota)\b|\b(?:out of|not enough|no remaining)\s+credits?\b/i.test(text);
}

function report(status, reason) {
  if (process.env.GITHUB_OUTPUT) {
    appendFileSync(process.env.GITHUB_OUTPUT,
      `status=${status}\nrun_review=${status === 'available'}\n`);
  }
  if (process.env.GITHUB_STEP_SUMMARY) {
    appendFileSync(process.env.GITHUB_STEP_SUMMARY, `Qoder review: **${status}**. ${reason}\n\n`);
  }
  console.log(`${status === 'skipped' ? '::notice::' : ''}Qoder review: ${reason}`);
}

export async function checkQuota(sdk) {
  let releaseInput;
  async function* noPrompt() {
    await new Promise(resolve => { releaseInput = resolve; });
  }
  const q = sdk.query({
    prompt: noPrompt(),
    options: { auth: sdk.accessTokenFromEnv() },
  });
  try {
    await q.initializationResult();
    const decision = quotaDecision(await q.getUsageInfo());
    if (decision === 'available') {
      report('available', 'Credits available; review can start.');
    } else {
      report('skipped', decision === 'exhausted'
        ? 'Credits exhausted; no review was started.'
        : 'Quota unavailable; no review was started.');
    }
  } finally {
    releaseInput?.();
    await q.close();
  }
}

export async function runReview(command = 'qodercli') {
  const child = spawn(command, [
    '-w', process.env.GITHUB_WORKSPACE || process.cwd(),
    '-p', process.env.INPUT_PROMPT,
    '--output-format', 'stream-json',
  ], { stdio: ['ignore', 'pipe', 'pipe'] });
  let stderr = '';
  let pending = '';
  const errors = [];
  function readLine(line) {
    try {
      const message = JSON.parse(line);
      // Only terminal error diagnostics establish quota failure, not review prose.
      if (message.type === 'result' && (message.is_error || message.subtype?.startsWith('error'))) {
        errors.push(JSON.stringify(message));
      }
      // Do not log tool arguments/results, which may contain credentials.
      console.log(`Qoder event: ${message.type} ${message.subtype || ''}`);
    } catch { /* Non-JSON stdout is not a terminal error diagnostic. */ }
  }
  child.stdout.setEncoding('utf8');
  child.stdout.on('data', chunk => {
    pending += chunk;
    const lines = pending.split('\n');
    pending = lines.pop();
    lines.forEach(readLine);
  });
  child.stderr.setEncoding('utf8');
  child.stderr.on('data', chunk => { stderr += chunk; });
  const code = await new Promise((resolve, reject) => {
    child.on('error', reject);
    child.on('close', resolve);
  });
  if (pending) readLine(pending);
  const diagnostics = [stderr, ...errors].join('\n');
  if (code === 0 && errors.length === 0) {
    report('completed', 'Review completed.');
  } else if (isQuotaError(diagnostics)) {
    report('skipped', 'Credits exhausted during review; review was not completed.');
  } else {
    // Do not turn model configuration/authentication/network errors into quota skips.
    throw new Error(`Review failed (exit ${code}): ${diagnostics || 'No error details returned'}`);
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    if (process.argv[2] === 'check') {
      if (!process.env.QODER_PERSONAL_ACCESS_TOKEN) throw new Error('Qoder PAT is missing');
      const sdk = await import(pathToFileURL(process.env.QODER_SDK_PATH).href);
      await checkQuota(sdk);
    } else if (process.argv[2] === 'review') {
      if (!process.env.INPUT_PROMPT) throw new Error('Review prompt is missing');
      await runReview();
    } else {
      throw new Error('Expected check or review');
    }
  } catch (error) {
    if (process.argv[2] === 'check' && isQuotaError(error.message)) {
      report('skipped', 'Credits exhausted; no review was started.');
    } else {
      const safe = error.message.replaceAll('%', '%25').replaceAll('\r', '%0D').replaceAll('\n', '%0A');
      console.log(`::error::Qoder review: ${safe}`);
      process.exitCode = 1;
    }
  }
}
