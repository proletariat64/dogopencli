// Quota skips are explicit; configuration, authentication and other failures stay red.
import { spawn } from 'node:child_process';
import { appendFileSync, readFileSync, writeFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import { parseReview } from './ai_review.mjs';

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

export function report(status, reason, quotaState = status, provider = 'Qoder') {
  if (process.env.GITHUB_OUTPUT) {
    appendFileSync(process.env.GITHUB_OUTPUT,
      `status=${status}\nquota_state=${quotaState}\nrun_review=${status === 'available'}\n`);
  }
  if (process.env.GITHUB_STEP_SUMMARY) {
    appendFileSync(process.env.GITHUB_STEP_SUMMARY, `${provider} review: **${status}**. ${reason}\n\n`);
  }
  console.log(`${status === 'skipped' ? '::notice::' : ''}${provider} review: ${reason}`);
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
        : 'Quota unavailable; no review was started.', decision);
    }
  } finally {
    releaseInput?.();
    await q.close();
  }
}

export async function runReview(command = 'qodercli', {
  provider = 'Qoder', prompt = process.env.INPUT_PROMPT, reportPath,
} = {}) {
  const args = provider === 'Kimi' ? [
    '--model', 'k3', '--output-format', 'stream-json', '-p', prompt,
  ] : [
    '-w', process.env.GITHUB_WORKSPACE || process.cwd(),
    '-p', prompt,
    '--output-format', 'stream-json',
  ];
  const child = spawn(command, args, { stdio: ['ignore', 'pipe', 'pipe'] });
  let stderr = '';
  let pending = '';
  const errors = [];
  let assistantOutput = false;
  let finalText = '';
  function readLine(line) {
    try {
      const message = JSON.parse(line);
      if (message.role === 'assistant' && typeof message.content === 'string' && message.content.trim()) {
        assistantOutput = true;
        if (!message.tool_calls?.length) finalText = message.content;
      }
      if (message.type === 'assistant') {
        const content = message.message?.content;
        const text = typeof content === 'string' ? content : Array.isArray(content)
          ? content.filter(part => part.type === 'text').map(part => part.text).join('') : '';
        if (text.trim()) finalText = text;
      }
      // Only terminal error diagnostics establish quota failure, not review prose.
      if (message.type === 'result' && (message.is_error || message.subtype?.startsWith('error'))) {
        errors.push(JSON.stringify(message));
      } else if (message.type === 'result' && typeof message.result === 'string' && message.result.trim()) {
        finalText = message.result;
      }
      // Do not log tool arguments/results, which may contain credentials.
      console.log(`${provider} event: ${message.type || message.role} ${message.subtype || ''}`);
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
  if (code === 0 && errors.length === 0 && (provider !== 'Kimi' || assistantOutput)) {
    if (reportPath) {
      try {
        writeFileSync(reportPath, JSON.stringify(parseReview(finalText)), { mode: 0o600 });
      } catch (error) {
        // Report format only: no model response, source, tool payload or secret.
        const text = finalText.trim();
        const format = text.startsWith('{') ? 'object' : text.startsWith('```')
          ? 'fence' : text ? 'prose' : 'empty';
        const fences = (text.match(/^```(?:json)?\s*$/gmi) || []).length;
        throw new Error(`${error.message}; final format=${format}, characters=${text.length}, fences=${fences}`);
      }
    }
    report('completed', 'Review analysis completed; publishing is a separate workflow step.', 'completed', provider);
  } else if (isQuotaError(diagnostics)) {
    report('skipped', 'Credits exhausted during review; review was not completed.', 'exhausted', provider);
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
      if (!process.env.REVIEW_PROMPT || !process.env.REVIEW_REPORT) throw new Error('Review prompt/report paths are missing');
      await runReview('qodercli', {
        prompt: readFileSync(process.env.REVIEW_PROMPT, 'utf8'),
        reportPath: process.env.REVIEW_REPORT,
      });
    } else {
      throw new Error('Expected check or review');
    }
  } catch (error) {
    if (process.argv[2] === 'check' && isQuotaError(error.message)) {
      report('skipped', 'Credits exhausted; no review was started.', 'exhausted');
    } else {
      const safe = error.message.replaceAll('%', '%25').replaceAll('\r', '%0D').replaceAll('\n', '%0A');
      console.log(`::error::Qoder review: ${safe}`);
      process.exitCode = 1;
    }
  }
}
