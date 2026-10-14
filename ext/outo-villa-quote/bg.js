// 背景程式：替 Outo 查詢頁向 Villa Finder 的報價 API 拿「指定日期、所有房數」的實際報價。
// 只做 GET，不登入、不送表單；一律以美元回傳（currency=usd）。
// 拿到的報價會再送到 Outo 的共享報價收集器（/api/quotes），讓沒裝擴充功能的同事也看得到。
const BASE = 'https://www.villa-finder.com/en/api/offer/';
const SHARE_URL = 'https://outo-bali-villas.vercel.app/api/quotes';
const CONC = 3, GAP = 120;
async function one(slug, from, to) {
  const u = `${BASE}${encodeURIComponent(slug)}.json?from=${from}&to=${to}&currency=usd`;
  try {
    const r = await fetch(u, { credentials: 'include', headers: { 'Accept': 'application/json' } });
    if (r.status !== 200) return { err: 'http' + r.status };
    const j = await r.json();
    const o = {};
    for (const [b, v] of Object.entries(j.offers || {})) {
      const p = v.price || {};
      o[b] = [p.originalPrice ?? null, p.discountedPrice ?? null, p.discountRate ?? 0, v.travelAgentPrice ?? null, v.pax ?? null];
    }
    return { av: j.availability || '', o, at: Date.now() };
  } catch (e) { return { err: String(e && e.message || e) }; }
}
async function getToken() {
  try { const s = await chrome.storage.sync.get('token'); return (s && s.token || '').trim(); } catch { return ''; }
}
// 把這批報價送到共享收集器。回傳 'ok' / 'notoken' / 'http4xx' / 'err'
async function share(from, to, res) {
  const k = await getToken(); if (!k) return 'notoken';
  const q = {};
  for (const [s, r] of Object.entries(res)) {
    if (!r || !r.o) continue;
    // 同業價（travelAgentPrice）不上傳：共享檔放在公開的 GitHub data 分支
    const o = {}; for (const [b, a] of Object.entries(r.o)) o[b] = [a[0], a[1], a[2], null, a[4]];
    q[`${s}|${from}|${to}`] = { av: r.av, o, at: r.at };
  }
  if (!Object.keys(q).length) return 'ok';
  try {
    const r = await fetch(SHARE_URL, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ k, q }) });
    return r.ok ? 'ok' : 'http' + r.status;
  } catch { return 'err'; }
}
chrome.runtime.onMessage.addListener((msg, sender, send) => {
  if (!msg) return;
  if (msg.type === 'OUTO_QUOTE_STATUS') { getToken().then(k => send({ token: !!k, version: chrome.runtime.getManifest().version })); return true; }
  if (msg.type !== 'OUTO_QUOTE') return;
  (async () => {
    const out = {}; const jobs = (msg.slugs || []).slice(0, 200); let i = 0;
    async function worker() {
      while (i < jobs.length) { const s = jobs[i++]; out[s] = await one(s, msg.from, msg.to); await new Promise(r => setTimeout(r, GAP)); }
    }
    await Promise.all(Array.from({ length: CONC }, worker));
    const shared = await share(msg.from, msg.to, out);
    send({ ok: true, from: msg.from, to: msg.to, res: out, shared });
  })();
  return true;
});
