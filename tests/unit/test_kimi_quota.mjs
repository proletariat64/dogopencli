import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import { checkKimiQuota, KIMI_BASE_URL, kimiQuotaDecision } from '../../scripts/kimi_quota.mjs';

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

test('current quota windows take precedence over legacy remaining-only compatibility fields', () => {
  const payload = {
    usage: { used: 0, limit: 0, remaining: 0 },
    limits: [{ detail: { limit: 100, remaining: 90 } }],
    usages: { limit_5h: { used_ratio: 0.1 }, limit_7d: { used_ratio: 0.2 } },
  };
  assert.equal(kimiQuotaDecision(payload), 'available');
  payload.usages.limit_7d.used_ratio = 1;
  assert.equal(kimiQuotaDecision(payload), 'exhausted');
  payload.usages.limit_7d.used_ratio = null;
  assert.equal(kimiQuotaDecision(payload), 'unknown');
});

test('usage preflight sends only a bounded usage GET, and keeps auth/network errors red', async t => {
  const logs = [];
  t.mock.method(console, 'log', (...args) => {
    logs.push(args.join(' '));
  });
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
    assert.equal(calls[0][1].method ?? 'GET', 'GET');
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
      }), { status })), error => {
        assert.match(error.message, new RegExp(`HTTP ${status}`));
        assert.ok(!error.message.includes('test-key'), 'error must not echo the API key');
        assert.ok(!error.message.includes('sensitive'), 'error must not echo the provider body');
        return true;
      });
    }
    await assert.rejects(checkKimiQuota(async () => { throw new Error('network timeout'); }), /network timeout/);
    delete process.env.KIMI_API_KEY;
    await assert.rejects(checkKimiQuota(() => assert.fail('must not fetch')), /KIMI_API_KEY is missing/);
  } finally {
    if (oldKey === undefined) delete process.env.KIMI_API_KEY; else process.env.KIMI_API_KEY = oldKey;
  }
});

test('preflight outputs start OCR only for available quota and records explicit skips', async t => {
  t.mock.method(console, 'log', () => {});
  const dir = mkdtempSync(join(tmpdir(), 'ocr-quota-'));
  const names = ['KIMI_API_KEY', 'GITHUB_OUTPUT', 'GITHUB_STEP_SUMMARY'];
  const saved = names.map(name => process.env[name]);
  process.env.KIMI_API_KEY = 'test-key';
  try {
    for (const [state, payload] of [
      ['available', { usages: { limit_5h: { used_ratio: 0.1 } } }],
      ['exhausted', { usages: { limit_5h: { used_ratio: 1 } } }],
      ['unknown', {}],
    ]) {
      process.env.GITHUB_OUTPUT = join(dir, `${state}-output`);
      process.env.GITHUB_STEP_SUMMARY = join(dir, `${state}-summary`);
      await checkKimiQuota(async () => new Response(JSON.stringify(payload)));
      const output = readFileSync(process.env.GITHUB_OUTPUT, 'utf8');
      assert.match(output, new RegExp(`quota_state=${state}\\n`));
      assert.match(output, new RegExp(`run_review=${state === 'available'}\\n`));
      const summary = readFileSync(process.env.GITHUB_STEP_SUMMARY, 'utf8');
      assert.match(summary, /OCR review:/);
      if (state !== 'available') assert.match(summary, /\*\*skipped\*\*.*no review was started/);
      assert.ok(!summary.includes('test-key'));
    }
  } finally {
    names.forEach((name, i) => {
      if (saved[i] === undefined) delete process.env[name]; else process.env[name] = saved[i];
    });
    rmSync(dir, { recursive: true, force: true });
  }
});
