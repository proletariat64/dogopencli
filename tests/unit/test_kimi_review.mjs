import assert from 'node:assert/strict';
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import { checkKimiQuota, KIMI_BASE_URL, kimiQuotaDecision, prepareKimi } from '../../scripts/kimi_review.mjs';
import { runReview } from '../../scripts/qoder_review.mjs';

delete process.env.GITHUB_OUTPUT;
delete process.env.GITHUB_STEP_SUMMARY;

test('every supplied Kimi quota window must allow review; wallet does not bypass exhaustion', () => {
  for (const payload of [
    { usage: { used: 20, limit: 100 }, limits: [{ detail: { used: '2', limit: '10' } }] },
    { usages: { limit_5h: { used_ratio: 0 }, limit_7d: { used_ratio: '0.8' } } },
  ]) assert.equal(kimiQuotaDecision(payload), 'available');
  for (const payload of [
    { usage: { used: 100, limit: 100 } },
    { usage: { used: 1, limit: 100 }, limits: [{ detail: { used: 11, limit: 10 } }] },
    { usages: { limit_5h: { used_ratio: 0.1 }, limit_7d: { used_ratio: 1 } } },
    { usages: { limit_month_code: { used_ratio: 1.01 } }, boosterWallet: { balance: { amountLeft: 100 } } },
  ]) assert.equal(kimiQuotaDecision(payload), 'exhausted');
});

test('missing, malformed and partial malformed quota windows never start a review', () => {
  for (const payload of [null, {}, { usages: {} }, { usage: {} },
    { usage: { used: 0, limit: 0 } }, { usage: { used: 0 } },
    { usage: { used: -1, limit: 10 } }, { usage: { used: true, limit: 10 } },
    { usage: { used: '', limit: '100' } }, { usage: { used: NaN, limit: 10 } },
    { usages: { limit_5h: { used_ratio: null } } },
    { usages: { limit_5h: { used_ratio: 0.1 }, limit_7d: {} } },
    { usage: { used: 1, limit: 100 }, limits: [null] },
    { usage: { used: 1, limit: 100 }, limits: {} },
    { boosterWallet: { balance: { amountLeft: 100 } } },
  ]) assert.equal(kimiQuotaDecision(payload), 'unknown', JSON.stringify(payload));
});

test('usage preflight sends only a bounded usage GET, and keeps auth/network errors red', async t => {
  t.mock.method(console, 'log', () => {});
  const oldKey = process.env.KIMI_API_KEY;
  process.env.KIMI_API_KEY = 'test-key';
  try {
    const calls = [];
    assert.equal(await checkKimiQuota(async (url, options) => {
      calls.push([url, options]);
      return new Response(JSON.stringify({ usage: { used: 1, limit: 10 } }));
    }), 'available');
    assert.equal(calls.length, 1);
    assert.equal(calls[0][0], `${KIMI_BASE_URL}/usages`);
    assert.equal(calls[0][1].headers.Authorization, 'Bearer test-key');
    assert.equal(calls[0][1].body, undefined);
    assert.equal(calls[0][1].redirect, 'error');
    assert.ok(calls[0][1].signal instanceof AbortSignal);
    assert.equal(await checkKimiQuota(async () => new Response('', { status: 404 })), 'unknown');
    assert.equal(await checkKimiQuota(async () => new Response('not-json')), 'unknown');
    assert.equal(await checkKimiQuota(async () => new Response(JSON.stringify({
      error: { message: 'quota is exhausted' },
    }), { status: 403 })), 'exhausted');
    for (const status of [401, 403, 429, 500]) {
      await assert.rejects(checkKimiQuota(async () => new Response(JSON.stringify({
        error: { message: 'sensitive test-key; generic rate limit' },
      }), { status })), new RegExp(`HTTP ${status}`));
    }
    await assert.rejects(checkKimiQuota(async () => { throw new Error('network timeout'); }), /network timeout/);
    delete process.env.KIMI_API_KEY;
    await assert.rejects(checkKimiQuota(() => assert.fail('must not fetch')), /KIMI_API_KEY is missing/);
  } finally {
    if (oldKey === undefined) delete process.env.KIMI_API_KEY; else process.env.KIMI_API_KEY = oldKey;
  }
});

test('Kimi config uses k3/high for primary and children without GitHub MCP or stored keys', () => {
  const dir = mkdtempSync(join(tmpdir(), 'kimi-resources-'));
  try {
    const home = join(dir, 'home');
    prepareKimi(home);
    const config = readFileSync(join(home, 'config.toml'), 'utf8');
    assert.match(config, /model = "k3"/);
    assert.match(config, /\[thinking\]\nenabled = true\neffort = "high"/);
    assert.match(config, /\[secondary_model\]\ndefault_model = "k3"\ndefault_effort = "high"\nforce = true/);
    assert.match(config, /api_key_env = "KIMI_API_KEY"/);
    assert.equal(existsSync(join(home, 'mcp.json')), false);
    assert.throws(() => prepareKimi(), /KIMI_CODE_HOME is missing/);
  } finally { rmSync(dir, { recursive: true, force: true }); }
});

test('Kimi CLI receives model/prompt without incompatible auto flag; quota vs errors stay separate', async t => {
  t.mock.method(console, 'log', () => {});
  const dir = mkdtempSync(join(tmpdir(), 'kimi-runner-'));
  const oldOutput = process.env.GITHUB_OUTPUT;
  process.env.GITHUB_OUTPUT = join(dir, 'output');
  const executable = join(dir, 'fake-kimi');
  const fake = body => writeFileSync(executable, `#!/usr/bin/env node\n${body}\n`, { mode: 0o700 });
  const options = { provider: 'Kimi', prompt: 'exact shared review prompt' };
  try {
    fake(`const assert = require('node:assert/strict');
      assert.deepEqual(process.argv.slice(2), ['--model','k3','--output-format','stream-json','-p','exact shared review prompt']);
      console.log(JSON.stringify({role:'assistant',content:'Review submitted.'}));`);
    await runReview(executable, options);
    assert.match(readFileSync(process.env.GITHUB_OUTPUT, 'utf8'), /status=completed/);
    fake('console.error("quota is exhausted"); process.exitCode=1;');
    await runReview(executable, options);
    assert.match(readFileSync(process.env.GITHUB_OUTPUT, 'utf8'), /quota_state=exhausted/);
    fake('console.error("HTTP 429 rate limit exceeded"); process.exitCode=1;');
    await assert.rejects(runReview(executable, options), /HTTP 429/);
    fake('console.error("invalid API key"); process.exitCode=1;');
    await assert.rejects(runReview(executable, options), /invalid API key/);
    fake('console.log(JSON.stringify({role:"assistant",content:"quota is exhausted"})); process.exitCode=1;');
    await assert.rejects(runReview(executable, options), /No error details/);
    fake('console.log(JSON.stringify({role:"tool", content:"sensitive tool response"}));');
    await assert.rejects(runReview(executable, options), /No error details/);
    fake('console.log("not json");');
    await assert.rejects(runReview(executable, options), /No error details/);
  } finally {
    if (oldOutput === undefined) delete process.env.GITHUB_OUTPUT; else process.env.GITHUB_OUTPUT = oldOutput;
    rmSync(dir, { recursive: true, force: true });
  }
});
