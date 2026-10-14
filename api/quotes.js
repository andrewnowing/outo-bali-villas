// Vercel serverless: 共享報價收集器。
// 裝了「Outo Villa 報價」擴充功能的同事查到的 Villa Finder 報價，會 POST 到這裡，
// 這裡再寫進 GitHub 的 data 分支 vfquotes.json；查詢頁每 2 分鐘讀一次，沒裝擴充功能的人也看得到。
// POST /api/quotes  body: { k: <OUTO_QUOTE_TOKEN>, q: { "slug|YYYY-MM-DD|YYYY-MM-DD": { av, o, at } } }
// 需要 Vercel 環境變數：OUTO_QUOTE_TOKEN（擴充功能上傳金鑰）、GH_DATA_TOKEN（可寫此 repo contents 的 fine-grained token）。
const REPO = 'andrewnowing/outo-bali-villas', BRANCH = 'data', FILE = 'vfquotes.json';
const TTL = 7 * 86400e3, MAX_IN = 300, MAX_BYTES = 2.5e6;
const KEY_RE = /^[a-z0-9-]{2,80}\|\d{4}-\d{2}-\d{2}\|\d{4}-\d{2}-\d{2}$/;

function cors(res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
}
function clean(q) {
  // 只保留格式正確的項目；報價物件壓成 {av, o:{br:[orig,disc,rate,agent,pax]}, at}
  const out = {}; let n = 0;
  for (const [k, v] of Object.entries(q || {})) {
    if (n >= MAX_IN) break;
    if (!KEY_RE.test(k) || !v || typeof v !== 'object') continue;
    const at = +v.at; if (!(at > 0) || at > Date.now() + 600e3 || Date.now() - at > TTL) continue;
    const o = {};
    for (const [b, a] of Object.entries(v.o || {})) {
      if (!/^\d{1,2}$/.test(b) || !Array.isArray(a)) continue;
      const num = x => (x == null || x === '' ? null : (Number.isFinite(+x) ? Math.round(+x * 100) / 100 : null));
      o[b] = [num(a[0]), num(a[1]), num(a[2]) || 0, null, num(a[4])]; // 同業價一律不存（公開 repo）
    }
    const av = v.av === 'unavailable' ? 'unavailable' : (v.av === 'available' ? 'available' : '');
    if (!Object.keys(o).length && av !== 'unavailable') continue;
    out[k] = { av, o, at: Math.round(at) }; n++;
  }
  return out;
}
async function gh(path, opt = {}) {
  const r = await fetch('https://api.github.com/repos/' + REPO + '/contents/' + path, {
    ...opt,
    headers: { 'Authorization': 'Bearer ' + process.env.GH_DATA_TOKEN, 'Accept': opt.accept || 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'outo-quotes', ...(opt.headers || {}) },
  });
  return r;
}
async function readStore() {
  const meta = await gh(FILE + '?ref=' + BRANCH);
  if (meta.status === 404) return { sha: null, data: { updatedAt: '', by: {} } };
  if (!meta.ok) throw new Error('gh read ' + meta.status);
  const m = await meta.json();
  let txt;
  if (m.content && m.encoding === 'base64') txt = Buffer.from(m.content, 'base64').toString('utf8');
  else { const raw = await gh(FILE + '?ref=' + BRANCH, { accept: 'application/vnd.github.raw' }); txt = await raw.text(); }
  let data; try { data = JSON.parse(txt); } catch { data = { by: {} }; }
  if (!data || typeof data !== 'object') data = { by: {} };
  if (!data.by) data.by = {};
  return { sha: m.sha, data };
}
function merge(store, incoming) {
  const by = store.by; let added = 0; const now = Date.now();
  for (const [k, v] of Object.entries(incoming)) {
    const old = by[k];
    if (!old || v.at > old.at) { by[k] = v; added++; }
  }
  for (const [k, v] of Object.entries(by)) {
    const ci = k.split('|')[1];
    if (now - v.at > TTL || ci < new Date(now - 86400e3).toISOString().slice(0, 10)) delete by[k];
  }
  // 檔案太大就從最舊的開始丟
  let txt = JSON.stringify(store);
  if (txt.length > MAX_BYTES) {
    const keys = Object.keys(by).sort((a, b) => by[a].at - by[b].at);
    while (txt.length > MAX_BYTES && keys.length) { delete by[keys.shift()]; txt = JSON.stringify(store); }
  }
  return added;
}
module.exports = async (req, res) => {
  cors(res);
  if (req.method === 'OPTIONS') { res.status(204).end(); return; }
  if (req.method !== 'POST') { res.status(405).json({ error: 'POST only' }); return; }
  const tok = process.env.OUTO_QUOTE_TOKEN, ght = process.env.GH_DATA_TOKEN;
  if (!tok || !ght) { res.status(503).json({ error: 'server not configured' }); return; }
  let body = req.body;
  if (typeof body === 'string') { try { body = JSON.parse(body); } catch { body = null; } }
  if (!body || body.k !== tok) { res.status(401).json({ error: 'bad token' }); return; }
  const incoming = clean(body.q);
  const n = Object.keys(incoming).length;
  if (!n) { res.status(200).json({ ok: true, n: 0, total: null }); return; }
  let lastErr = '';
  for (let i = 0; i < 4; i++) {
    try {
      const { sha, data } = await readStore();
      const added = merge(data, incoming);
      if (!added) { res.status(200).json({ ok: true, n: 0, total: Object.keys(data.by).length }); return; }
      data.updatedAt = new Date().toISOString();
      const put = await gh(FILE, {
        method: 'PUT',
        body: JSON.stringify({ message: 'vfquotes: +' + added + ' ' + data.updatedAt.slice(0, 16) + 'Z', branch: BRANCH, sha: sha || undefined,
          content: Buffer.from(JSON.stringify(data)).toString('base64'), committer: { name: 'outo-bot', email: 'andrew@outo.co' } }),
      });
      if (put.ok) { res.status(200).json({ ok: true, n: added, total: Object.keys(data.by).length }); return; }
      lastErr = 'gh put ' + put.status;
      if (put.status !== 409 && put.status !== 422) break;
      await new Promise(r => setTimeout(r, 400 + Math.random() * 800));
    } catch (e) { lastErr = String(e && e.message || e); }
  }
  res.status(502).json({ error: lastErr || 'store failed' });
};
