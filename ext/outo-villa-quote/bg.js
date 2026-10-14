// 背景程式：替 Outo 查詢頁向 Villa Finder 的報價 API 拿「指定日期、所有房數」的實際報價。
// 只做 GET，不登入、不送表單；一律以美元回傳（currency=usd）。
const BASE = 'https://www.villa-finder.com/en/api/offer/';
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
chrome.runtime.onMessage.addListener((msg, sender, send) => {
  if (!msg || msg.type !== 'OUTO_QUOTE') return;
  (async () => {
    const out = {}; const jobs = (msg.slugs || []).slice(0, 200); let i = 0;
    async function worker() {
      while (i < jobs.length) { const s = jobs[i++]; out[s] = await one(s, msg.from, msg.to); await new Promise(r => setTimeout(r, GAP)); }
    }
    await Promise.all(Array.from({ length: CONC }, worker));
    send({ ok: true, from: msg.from, to: msg.to, res: out });
  })();
  return true;
});
