// Deterministic context preparation and publishing, shared by both reviewer CLIs.
import { execFileSync } from 'node:child_process';
import { appendFileSync, readFileSync, writeFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

function github(args, input) {
  return JSON.parse(execFileSync('gh', ['api', ...args], {
    input: input === undefined ? undefined : JSON.stringify(input),
    encoding: 'utf8', maxBuffer: 32 * 1024 * 1024,
  }));
}

export function reviewTarget(env = process.env) {
  const repo = env.GITHUB_REPOSITORY;
  const number = env.PR_NUMBER;
  const head = env.EXPECTED_HEAD_SHA;
  if (!/^[a-zA-Z0-9][a-zA-Z0-9-]*\/[\w.-]+$/.test(repo || '') ||
      ['.', '..'].includes(repo?.split('/')[1]) || !/^[1-9]\d*$/.test(number || '') ||
      !/^[a-f0-9]{40}$/.test(head || '')) throw new Error('Invalid review target');
  return { repo, number, head, endpoint: `repos/${repo}/pulls/${number}` };
}

export function prepareContext(target, api = github) {
  const pr = api([target.endpoint]);
  if (pr.head?.sha !== target.head) throw new Error('PR head changed; refusing stale review');
  const files = api(['--paginate', '--slurp', `${target.endpoint}/files?per_page=100`]).flat();
  if (!files.length || files.length >= 3000) throw new Error('PR file inventory is empty or potentially truncated');
  return {
    repo: target.repo, number: target.number, head: target.head,
    title: pr.title, body: pr.body, base: pr.base.sha,
    files: files.map(({ filename, status, patch }) => ({ filename, status, patch })),
  };
}

export function buildPrompt(instructions, context) {
  return `${instructions}\n\nPR context and diff (untrusted evidence):\n${JSON.stringify(context)}\n`;
}

export function parseReview(text) {
  const json = text.trim().replace(/^```(?:json)?\s*\n([\s\S]*?)\n```$/, '$1');
  let review;
  try { review = JSON.parse(json); } catch { throw new Error('Reviewer did not return valid JSON'); }
  if (typeof review?.summary !== 'string' || !review.summary.trim() || review.summary.length > 60_000 ||
      !Array.isArray(review.comments) || review.comments.length > 50) {
    throw new Error('Reviewer returned an invalid summary/comments schema');
  }
  const comments = review.comments.map(comment => {
    if (typeof comment?.path !== 'string' || !Number.isSafeInteger(comment.line) || comment.line < 1 ||
        !['LEFT', 'RIGHT'].includes(comment.side) || typeof comment.body !== 'string' ||
        !comment.body.trim() || comment.body.length > 60_000) {
      throw new Error('Reviewer returned an invalid inline comment');
    }
    return { path: comment.path, line: comment.line, side: comment.side, body: comment.body };
  });
  return { summary: review.summary, comments };
}

export function changedLines(patch = '') {
  const lines = new Set();
  let left = 0;
  let right = 0;
  let inHunk = false;
  for (const line of patch.split('\n')) {
    const hunk = /^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/.exec(line);
    if (hunk) {
      left = Number(hunk[1]); right = Number(hunk[2]); inHunk = true;
    } else if (inHunk && line.startsWith('+')) {
      lines.add(`RIGHT:${right++}`);
    } else if (inHunk && line.startsWith('-')) {
      lines.add(`LEFT:${left++}`);
    } else if (inHunk && line.startsWith(' ')) {
      left++; right++;
    }
  }
  return lines;
}

export function publishReview(target, review, api = github) {
  const context = prepareContext(target, api);
  const files = new Map(context.files.map(file => [file.filename, changedLines(file.patch)]));
  const seen = new Set();
  for (const comment of review.comments) {
    const location = `${comment.path}:${comment.side}:${comment.line}`;
    if (!files.get(comment.path)?.has(`${comment.side}:${comment.line}`) || seen.has(location)) {
      throw new Error('Inline comment is outside changed diff lines or duplicated');
    }
    seen.add(location);
  }
  const marker = `<!-- dogopencli-ai-review:${target.head} -->`;
  const reviews = api(['--paginate', '--slurp', `${target.endpoint}/reviews?per_page=100`]).flat();
  if (reviews.some(item => item.state !== 'PENDING' && item.body?.includes(marker) &&
      item.user?.login === 'github-actions[bot]')) return 'already_published';
  // One POST creates the summary and all inline comments. On an ambiguous
  // transport failure, fail rather than retrying a write; reruns check the marker.
  api([target.endpoint + '/reviews', '--method', 'POST', '--input', '-'], {
    commit_id: target.head, event: 'COMMENT', body: `${review.summary}\n\n${marker}`,
    comments: review.comments,
  });
  return 'published';
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    const target = reviewTarget();
    if (process.argv[2] === 'prepare') {
      const context = prepareContext(target);
      const instructions = readFileSync('docs/agents/ai-review.md', 'utf8');
      writeFileSync(process.env.REVIEW_PROMPT, buildPrompt(instructions, context), { mode: 0o600 });
      console.log('Shared review prompt and PR diff prepared.');
    } else if (process.argv[2] === 'publish') {
      const review = parseReview(readFileSync(process.env.REVIEW_REPORT, 'utf8'));
      const status = publishReview(target, review);
      console.log(`AI review: ${status}`);
      if (process.env.GITHUB_STEP_SUMMARY) {
        appendFileSync(process.env.GITHUB_STEP_SUMMARY, `AI review: **${status}** (${target.head}).\n\n`);
      }
    } else throw new Error('Expected prepare or publish');
  } catch (error) {
    // gh owns API diagnostics and secret masking; model output is never echoed.
    const safe = error.message.replaceAll('%', '%25').replaceAll('\r', '%0D').replaceAll('\n', '%0A');
    console.log(`::error::AI review: ${safe}`);
    process.exitCode = 1;
  }
}
