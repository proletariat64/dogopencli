import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import { checkQuota, isQuotaError, quotaDecision, runReview } from '../../scripts/qoder_review.mjs';

// Tests run inside Actions too; simulated skips must not change the real summary.
delete process.env.GITHUB_OUTPUT;
delete process.env.GITHUB_STEP_SUMMARY;

test('exhaustion overrides other buckets; paid and available org credits permit review', () => {
  assert.equal(quotaDecision({ isQuotaExceeded: true, userQuota: { remaining: 10 } }), 'exhausted');
  assert.equal(quotaDecision({ userQuota: { remaining: 1 } }), 'available');
  assert.equal(quotaDecision({ userQuota: { remaining: 0 }, addOnQuota: { remaining: 5 } }), 'available');
  assert.equal(quotaDecision({ orgResourcePackage: { available: true, remaining: 10 } }), 'available');
  assert.equal(quotaDecision({ orgResourcePackage: { available: false, remaining: 10 } }), 'unknown');
  assert.equal(quotaDecision({ isQuotaExceeded: false }), 'available');
});

test('absent, session-only and invalid quota data never start a paid task', () => {
  for (const usage of [null, {}, { session: { total_credits: 0 } },
    { userQuota: { remaining: '10' } }, { userQuota: { remaining: NaN } },
    { userQuota: { remaining: 0 } }]) {
    assert.equal(quotaDecision(usage), 'unknown');
  }
});

test('only explicit credit/quota exhaustion is eligible for a skip', () => {
  for (const message of ['insufficient credits', 'quota exceeded', 'Credits are exhausted',
    'out of credits', 'not enough credits', 'no remaining credits', 'credit_exhausted']) {
    assert.equal(isQuotaError(message), true, message);
  }
  for (const message of ['no valid model config found', 'invalid personal access token',
    'HTTP 429 rate limit exceeded', 'QUOTA_EXCEEDED', 'network timeout', 'quota service unavailable']) {
    assert.equal(isQuotaError(message), false, message);
  }
});

test('preflight keeps an empty prompt stream and always closes the SDK session', async t => {
  t.mock.method(console, 'log', () => {});
  let closed = false;
  let initialized = false;
  await checkQuota({
    accessTokenFromEnv: () => ({ type: 'accessToken' }),
    query: ({ prompt }) => {
      assert.equal(typeof prompt[Symbol.asyncIterator], 'function');
      return {
        initializationResult: async () => { initialized = true; },
        getUsageInfo: async () => {
          assert.equal(initialized, true);
          return { isQuotaExceeded: true };
        },
        close: async () => { closed = true; },
      };
    },
  });
  assert.equal(closed, true);
  closed = false;
  await assert.rejects(checkQuota({
    accessTokenFromEnv: () => ({}),
    query: () => ({
      initializationResult: async () => { throw new Error('invalid token'); },
      close: async () => { closed = true; },
    }),
  }), /invalid token/);
  assert.equal(closed, true);
});

test('runner skips quota failures, rejects config failures and detects zero-exit error results', async t => {
  t.mock.method(console, 'log', () => {});
  const dir = mkdtempSync(join(tmpdir(), 'qoder-guard-test-'));
  const oldOutput = process.env.GITHUB_OUTPUT;
  const oldSummary = process.env.GITHUB_STEP_SUMMARY;
  const oldPrompt = process.env.INPUT_PROMPT;
  const executable = join(dir, 'fake-qoder');
  process.env.GITHUB_OUTPUT = join(dir, 'output');
  process.env.GITHUB_STEP_SUMMARY = join(dir, 'summary');
  process.env.INPUT_PROMPT = '/review-pr';
  const fake = body => writeFileSync(executable, `#!/usr/bin/env node\n${body}\n`, { mode: 0o700 });
  try {
    fake('console.error("insufficient credits"); process.exitCode = 1;');
    await runReview(executable);
    assert.match(readFileSync(process.env.GITHUB_OUTPUT, 'utf8'), /status=skipped/);
    assert.match(readFileSync(process.env.GITHUB_OUTPUT, 'utf8'), /quota_state=exhausted/);
    assert.match(readFileSync(process.env.GITHUB_STEP_SUMMARY, 'utf8'), /not completed/);
    fake('console.error("no valid model config found"); process.exitCode = 1;');
    await assert.rejects(runReview(executable), /no valid model config found/);
    fake('console.log(JSON.stringify({type:"result", is_error:true, errors:["quota exceeded"]}));');
    await runReview(executable);
    fake('console.log(JSON.stringify({type:"result", is_error:true, errors:["invalid token"]}));');
    await assert.rejects(runReview(executable), /invalid token/);
    fake('console.log(JSON.stringify({type:"assistant", text:"insufficient credits"})); process.exitCode = 1;');
    await assert.rejects(runReview(executable), /No error details/);
    fake('console.log(JSON.stringify({type:"result", subtype:"success", is_error:false}));');
    await runReview(executable);
    assert.match(readFileSync(process.env.GITHUB_OUTPUT, 'utf8'), /status=completed/);
  } finally {
    for (const [name, value] of Object.entries({
      GITHUB_OUTPUT: oldOutput, GITHUB_STEP_SUMMARY: oldSummary, INPUT_PROMPT: oldPrompt,
    })) {
      if (value === undefined) delete process.env[name]; else process.env[name] = value;
    }
    rmSync(dir, { recursive: true, force: true });
  }
});

test('preflight exposes exhaustion separately from unknown quota for fallback routing', async t => {
  t.mock.method(console, 'log', () => {});
  const dir = mkdtempSync(join(tmpdir(), 'qoder-routing-'));
  const oldOutput = process.env.GITHUB_OUTPUT;
  process.env.GITHUB_OUTPUT = join(dir, 'output');
  try {
    for (const [usage, expected, run] of [
      [{ isQuotaExceeded: true }, 'exhausted', false],
      [{}, 'unknown', false],
      [{ isQuotaExceeded: false }, 'available', true],
    ]) {
      writeFileSync(process.env.GITHUB_OUTPUT, '');
      await checkQuota({
        accessTokenFromEnv: () => ({}),
        query: () => ({ initializationResult: async () => {},
          getUsageInfo: async () => usage, close: async () => {} }),
      });
      const output = readFileSync(process.env.GITHUB_OUTPUT, 'utf8');
      assert.ok(output.includes(`quota_state=${expected}\n`));
      assert.ok(output.includes(`run_review=${run}\n`));
    }
  } finally {
    if (oldOutput === undefined) delete process.env.GITHUB_OUTPUT; else process.env.GITHUB_OUTPUT = oldOutput;
    rmSync(dir, { recursive: true, force: true });
  }
});
