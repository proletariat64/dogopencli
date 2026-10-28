'use strict';
const $ = (selector) => document.querySelector(selector);
let releases = [], domain = 'all';
const names = {liquidity:'资金管理', payment:'付款', collection:'收款', fx:'外汇'};
const glyphs = {liquidity:'≋', payment:'↗', collection:'⊞', fx:'⇄'};
function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function latest() {
  const seen = new Set();
  return releases.filter(item => { if (seen.has(item.id)) return false; seen.add(item.id); return true; });
}
function command(item) { return `dogopencli plugins install ${new URL(item.download, location.origin).href}`; }
async function copy(text, button) {
  try { await navigator.clipboard.writeText(text); button.textContent = '已复制'; }
  catch { button.textContent = '请选中上方命令复制'; }
}
function showDetail(item) {
  const body = $('#detail-body'); body.replaceChildren();
  body.append(element('p','eyebrow',`${names[item.domain] || item.domain} / ${item.version}`), element('h2','',item.name), element('p','',item.summary));
  body.append(element('p','hint','静态校验通过 · 未声明生产业务验收 · 安装插件会加载其 Python 代码，请确认来源可信。'));
  const versions = element('select'); versions.setAttribute('aria-label','发布版本');
  releases.filter(release => release.id === item.id).forEach(release => {
    const option = element('option','',release.version); option.value = release.version;
    option.selected = release.version === item.version; versions.append(option);
  });
  versions.onchange = () => showDetail(releases.find(release => release.id === item.id && release.version === versions.value));
  body.append(versions,element('h3','','安装'),element('pre','',command(item)));
  const row = element('div','download-row');
  const download = element('a','primary','下载 ZIP ↓'); download.href = item.download; download.download = `${item.id}-${item.version}.zip`;
  const button = element('button','outline','复制安装命令'); button.onclick = () => copy(command(item),button);
  row.append(download,button); body.append(row);
  body.append(element('p','hint',`${(item.bytes / 1024).toFixed(1)} KiB · 发布于 ${new Date(item.published_at).toLocaleString('zh-CN')}`));
  body.append(element('h3','','SHA256'),element('pre','',item.sha256));
  body.append(element('h3','','能力与使用边界'),element('p','',item.manifest.purpose));
  const operations = element('ul'); Object.entries(item.manifest.operations).forEach(([name, value]) => operations.append(element('li','',`${name} — ${value.description}`))); body.append(operations);
  const limits = element('ul'); item.manifest.limitations.forEach(text => limits.append(element('li','',text))); body.append(limits);
  const details = element('details'); details.append(element('summary','','查看 leaf.json'),element('pre','',JSON.stringify(item.manifest,null,2))); body.append(details);
  if (!$('#detail').open) $('#detail').showModal();
}
function render() {
  const query = $('#search').value.trim().toLowerCase();
  const items = latest().filter(item => (domain === 'all' || item.domain === domain) && `${item.id} ${item.summary} ${names[item.domain]}`.toLowerCase().includes(query));
  items.sort($('#sort').value === 'recent' ? (a,b) => b.published_at.localeCompare(a.published_at) : (a,b) => a.id.localeCompare(b.id));
  $('#total').textContent = latest().length;
  $('#results').textContent = `${items.length} 项能力 · ${releases.length} 个发布版本`;
  $('#empty').hidden = items.length !== 0; $('#grid').replaceChildren();
  items.forEach(item => {
    const card = element('article','card');
    const top = element('div','card-top'); top.append(element('span','glyph',glyphs[item.domain] || '◇'),element('span','tag',item.domain));
    card.append(top,element('h3','',item.name),element('p','',item.summary));
    const bottom = element('div','card-bottom'); bottom.append(element('span','',`${item.operations.join(' / ')} · ${item.version}`));
    const button = element('button','','详情 / 下载 ↗'); button.setAttribute('aria-label',`查看 ${item.id}`); button.onclick = () => showDetail(item); bottom.append(button); card.append(bottom); $('#grid').append(card);
  });
}
async function load() {
  const response = await fetch('api/catalog');
  if (!response.ok) throw new Error('目录加载失败');
  const result = await response.json(); releases = result.releases; render();
  $('#open-publish').title = result.publishing ? '发布插件' : '发布未启用，请联系站点管理员';
}
$('#search').addEventListener('input', render); $('#sort').addEventListener('change',render);
$('.filters').addEventListener('click', event => {
  const button = event.target.closest('button'); if (!button) return;
  domain = button.dataset.domain;
  document.querySelectorAll('.filters button').forEach(node => node.classList.toggle('selected',node === button)); render();
});
document.addEventListener('keydown',event => { if (event.key === '/' && !['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName) && !document.querySelector('dialog[open]')) { event.preventDefault(); $('#search').focus(); } });
document.querySelectorAll('dialog .close').forEach(button => button.onclick = () => { button.closest('dialog').close(); $('#token').value = ''; });
$('#publish').addEventListener('close',() => { $('#token').value = ''; });
$('#open-publish').onclick = () => { $('#publish-status').textContent = ''; $('#publish').showModal(); };
$('#publish-form').onsubmit = async event => {
  event.preventDefault();
  const file = $('#archive').files[0], status = $('#publish-status'), button = $('#publish-form button[type=submit]');
  status.className = ''; if (!file || file.size > 50 * 1024 * 1024) { status.textContent = '请选择不超过 50 MiB 的 ZIP'; return; }
  button.disabled = true; status.textContent = '正在上传并校验…';
  let published = false;
  try {
    const response = await fetch(`api/releases/${encodeURIComponent($('#version').value)}`, {method:'PUT',headers:{'Authorization':`Bearer ${$('#token').value}`,'Content-Type':'application/zip'},body:file});
    const result = await response.json(); if (!response.ok) throw new Error(result.error || '发布失败');
    published = true; status.textContent = `已发布 ${result.id} · ${result.version}`; $('#publish-form').reset();
    try { await load(); } catch { status.textContent += '；目录刷新失败，请刷新页面查看。'; }
  } catch (error) { status.textContent = error.message; status.className = 'status-error'; }
  finally { button.disabled = false; $('#token').value = ''; if (!published) status.textContent += '。请检查后重试。'; }
};
load().catch(error => { $('#results').textContent = `${error.message}，请刷新重试。`; $('#results').className = 'status-error'; });
