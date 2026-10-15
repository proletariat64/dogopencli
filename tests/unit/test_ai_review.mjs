import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import { buildPrompt, changedLines, parseReview, prepareContext, publishReview, reviewTarget } from '../../scripts/ai_review.mjs';
import { runReview } from '../../scripts/qoder_review.mjs';

delete process.env.GITHUB_OUTPUT;
delete process.env.GITHUB_STEP_SUMMARY;
const head = 'a'.repeat(40);
const target = reviewTarget({ GITHUB_REPOSITORY: 'owner/repo', PR_NUMBER: '12', EXPECTED_HEAD_SHA: head });
const file = { filename: 'src/example.py', status: 'modified',
  patch: '@@ -10,3 +10,3 @@\n context\n-old\n+new\n context\n@@ -30,0 +31,1 @@\n+second' };
const report = { summary: '## 👋 Review Summary\nA concrete review.', comments: [
  { path: file.filename, line: 11, side: 'RIGHT', body: 'When x is absent, this branch fails.' },
] };

function fakeApi({ sha = head, reviews = [], files = [file] } = {}) {
  const writes = [];
  const api = (args, input) => {
    if (input) { writes.push(input); return { id: 99 }; }
    if (args[0] === target.endpoint) return { head: { sha }, base: { sha: 'b'.repeat(40) }, title: 'Change', body: 'Intent' };
    if (args.at(-1).includes('/files?')) return [files];
    if (args.at(-1).includes('/reviews?')) return [reviews];
    assert.fail(`Unexpected API call ${args}`);
  };
  return { api, writes };
}

test('prepare context freezes expected head, captures paginated files and shares prompt', () => {
  const { api, writes } = fakeApi();
  const context = prepareContext(target, api);
  assert.deepEqual(context.files, [file]);
  assert.equal(context.head, head);
  const prompt = buildPrompt('Shared review instructions', context);
  assert.match(prompt, /^Shared review instructions/);
  assert.ok(prompt.includes(JSON.stringify(context)));
  assert.equal(writes.length, 0);
  assert.throws(() => prepareContext(target, fakeApi({ sha: 'c'.repeat(40) }).api), /head changed/);
  assert.throws(() => prepareContext(target, fakeApi({ files: [] }).api), /inventory/);
  assert.throws(() => reviewTarget({ GITHUB_REPOSITORY: '../bad', PR_NUMBER: '1', EXPECTED_HEAD_SHA: head }), /Invalid review target/);
});

test('parse report rejects incomplete schema and strips untrusted additional fields', () => {
  assert.deepEqual(parseReview(JSON.stringify({ ...report, event: 'APPROVE', commit_id: 'untrusted' })), report);
  assert.deepEqual(parseReview('```json\n'+JSON.stringify(report)+'\n```'), report);
  for (const bad of ['not-json', '{}', JSON.stringify({ summary: '', comments: [] }),
    JSON.stringify({ ...report, comments: [{ ...report.comments[0], line: 0 }] }),
    JSON.stringify({ ...report, comments: [{ ...report.comments[0], line: '11' }] }),
    JSON.stringify({ ...report, comments: [{ ...report.comments[0], side: 'OTHER' }] }),
    JSON.stringify({ ...report, comments: Array(51).fill(report.comments[0]) }),
  ]) assert.throws(() => parseReview(bad), /invalid|valid JSON/);
});

test('publisher allows changed LEFT/RIGHT source lines and writes a single COMMENT review', () => {
  assert.deepEqual([...changedLines(file.patch)], ['LEFT:11', 'RIGHT:11', 'RIGHT:31']);
  const { api, writes } = fakeApi();
  assert.equal(publishReview(target, report, api), 'published');
  assert.equal(writes.length, 1);
  assert.equal(writes[0].commit_id, head);
  assert.equal(writes[0].event, 'COMMENT');
  assert.deepEqual(writes[0].comments, report.comments);
  assert.match(writes[0].body, /dogopencli-ai-review:/);
  const left = { ...report, comments: [{ ...report.comments[0], side: 'LEFT' }] };
  assert.equal(publishReview(target, left, fakeApi().api), 'published');
});

test('publisher refuses stale heads, invalid locations and duplicate comments before any POST', () => {
  for (const comments of [
    [{ ...report.comments[0], path: 'unrelated.py' }],
    [{ ...report.comments[0], line: 10 }],
    [{ ...report.comments[0], line: 999 }],
    [report.comments[0], report.comments[0]],
  ]) {
    const { api, writes } = fakeApi();
    assert.throws(() => publishReview(target, { ...report, comments }, api), /diff lines|duplicated/);
    assert.equal(writes.length, 0);
  }
  const { api, writes } = fakeApi({ sha: 'c'.repeat(40) });
  assert.throws(() => publishReview(target, report, api), /head changed/);
  assert.equal(writes.length, 0);
});

test('reruns skip existing submitted bot review, but not user-forged or pending markers', () => {
  const marker = `<!-- dogopencli-ai-review:${head} -->`;
  const review = { state: 'COMMENTED', body: marker, user: { login: 'github-actions[bot]' } };
  const { api, writes } = fakeApi({ reviews: [review] });
  assert.equal(publishReview(target, report, api), 'already_published');
  assert.equal(writes.length, 0);
  for (const other of [{ ...review, state: 'PENDING' }, { ...review, user: { login: 'author' } }]) {
    const fake = fakeApi({ reviews: [other] });
    assert.equal(publishReview(target, report, fake.api), 'published');
    assert.equal(fake.writes.length, 1);
  }
});

test('both CLI protocols produce the same validated report and reject prose or empty success', async t => {
  t.mock.method(console, 'log', () => {});
  const dir = mkdtempSync(join(tmpdir(), 'ai-review-output-'));
  const command = join(dir, 'fake-reviewer');
  const reportPath = join(dir, 'report.json');
  const content = JSON.stringify(report);
  try {
    for (const [provider, output] of [
      ['Qoder', { type: 'assistant', message: { content: [{ type: 'text', text: content }] } }],
      ['Qoder', { type: 'result', subtype: 'success', result: content }],
      ['Kimi', { role: 'assistant', content }],
    ]) {
      writeFileSync(command, `#!/usr/bin/env node
        require('node:assert/strict').equal(process.argv[process.argv.indexOf('-p')+1], 'exact shared prompt');
        console.log(${JSON.stringify(JSON.stringify(output))});`, { mode: 0o700 });
      await runReview(command, { provider, prompt: 'exact shared prompt', reportPath });
      assert.deepEqual(JSON.parse(readFileSync(reportPath, 'utf8')), report);
    }
    rmSync(reportPath);
    writeFileSync(command, '#!/usr/bin/env node\nconsole.log(JSON.stringify({role:"assistant",content:"Looks good"}));', { mode: 0o700 });
    await assert.rejects(runReview(command, { provider: 'Kimi', prompt: 'p', reportPath }), /valid JSON/);
    assert.throws(() => readFileSync(reportPath), /ENOENT/);
    assert.throws(() => readFileSync(`${reportPath}.response.txt`), /ENOENT/);
    writeFileSync(command, '#!/usr/bin/env node\n', { mode: 0o700 });
    await assert.rejects(runReview(command, { provider: 'Qoder', prompt: 'p', reportPath }), /valid JSON/);
  } finally { rmSync(dir, { recursive: true, force: true }); }
});
