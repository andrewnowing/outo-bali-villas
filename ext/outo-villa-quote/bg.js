// 背景程式：替 Outo 查詢頁向 Villa Finder 的報價 API 拿「指定日期、所有房數」的實際報價。
// 只做 GET，不登入、不送表單；一律以美元回傳（currency=usd）。
// 拿到的報價會再送到 Outo 的共享報價收集器（/api/quotes），讓沒裝擴充功能的同事也看得到。
//
// 1.2.0 起：報價請求不再由背景程式直接發出，而是在一個 villa-finder.com 的分頁裡執行。
// 原因：2026-10-21 後 Villa Finder 的 Cloudflare 只放行從自家「別墅頁面」發出的 API 請求
//（2026-11-03 實測：從別墅頁 fetch 回 200，從首頁或擴充功能背景 fetch 一律 403）。
// 做法是找一個已開在別墅頁的 villa-finder.com 分頁（沒有就開一個釘選、不切換過去的分頁），
// 用 chrome.scripting 把查價的函式注入該分頁的頁面環境執行，等於「從 VF 自己的頁面查」。
const VF_ORIGIN = 'https://www.villa-finder.com';
// 任何別墅頁都可以當宿主；用一間長期上架的別墅，VF 會自己把 /en/bali/<slug> 轉到正確的區域路徑
const HELPER_URL = VF_ORIGIN + '/en/bali/villa-ananda';
// 別墅頁網址長這樣：/en/<區域>/<slug>；首頁與區域列表頁（/en/bali）查價會被擋，不能借用
const VILLA_PAGE_RE = /^https:\/\/www\.villa-finder\.com\/en\/[^\/?#]+\/[^\/?#]+/;
const SHARE_URL = 'https://outo-bali-villas.vercel.app/api/quotes';
const CONC = 3, GAP = 120, BATCH = 60;

let helperTabId = null, helperPromise = null;

async function tabReady(tabId, timeoutMs) {
  const tab = await chrome.tabs.get(tabId).catch(() => null);
  if (!tab) throw new Error('helper-tab-gone');
  if (tab.status === 'complete') return;
  await new Promise((res, rej) => {
    const timer = setTimeout(() => { chrome.tabs.onUpdated.removeListener(fn); rej(new Error('helper-tab-timeout')); }, timeoutMs);
    function fn(id, info) { if (id === tabId && info.status === 'complete') { clearTimeout(timer); chrome.tabs.onUpdated.removeListener(fn); res(); } }
    chrome.tabs.onUpdated.addListener(fn);
  });
}

// 回傳可用的 villa-finder.com 分頁 id；優先用使用者已開的分頁，沒有才自己開一個釘選的背景分頁。
async function getHelperTab() {
  if (helperTabId != null) {
    const t = await chrome.tabs.get(helperTabId).catch(() => null);
    if (t && VILLA_PAGE_RE.test(t.url || '')) { await tabReady(helperTabId, 20e3); return helperTabId; }
    helperTabId = null;
  }
  if (helperPromise) return helperPromise;
  helperPromise = (async () => {
    const existing = (await chrome.tabs.query({ url: VF_ORIGIN + '/*' })).filter(t => VILLA_PAGE_RE.test(t.url || ''));
    let tab = existing.find(t => t.status === 'complete') || existing[0];
    if (!tab) tab = await chrome.tabs.create({ url: HELPER_URL, active: false, pinned: true });
    await tabReady(tab.id, 25e3);
    helperTabId = tab.id;
    return tab.id;
  })();
  try { return await helperPromise; } finally { helperPromise = null; }
}
chrome.tabs.onRemoved.addListener(id => { if (id === helperTabId) helperTabId = null; });

// 在 VF 分頁的頁面環境裡執行：同源 fetch 報價 API。這個函式會被序列化注入，不能引用外面的變數。
function fetchInPage(slugs, from, to, conc, gap) {
  const blocked = /been blocked|Attention Required/i.test(document.title + ' ' + (document.body && document.body.innerText.slice(0, 400)));
  if (blocked) { const out = {}; for (const s of slugs) out[s] = { err: 'cf-blocked' }; return Promise.resolve(out); }
  async function one(slug) {
    const u = `/en/api/offer/${encodeURIComponent(slug)}.json?from=${from}&to=${to}&currency=usd`;
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
  const out = {}; let i = 0;
  async function worker() {
    while (i < slugs.length) { const s = slugs[i++]; out[s] = await one(s); await new Promise(r => setTimeout(r, gap)); }
  }
  return Promise.all(Array.from({ length: conc }, worker)).then(() => out);
}

async function quoteAll(slugs, from, to) {
  const out = {};
  let tabId;
  try { tabId = await getHelperTab(); }
  catch (e) { for (const s of slugs) out[s] = { err: 'helper:' + (e && e.message || e) }; return out; }
  for (let i = 0; i < slugs.length; i += BATCH) {
    const part = slugs.slice(i, i + BATCH);
    try {
      const r = await chrome.scripting.executeScript({ target: { tabId }, world: 'MAIN', func: fetchInPage, args: [part, from, to, CONC, GAP] });
      let res = r && r[0] && r[0].result || {};
      // 借用的分頁若不在別墅頁（例如使用者剛跳到搜尋頁），會整批 403：改開自己的別墅頁分頁重試一次
      if (part.length && part.every(s => res[s] && res[s].err === 'http403')) {
        helperTabId = null;
        const own = await chrome.tabs.create({ url: HELPER_URL, active: false, pinned: true });
        await tabReady(own.id, 25e3); helperTabId = tabId = own.id;
        const r2 = await chrome.scripting.executeScript({ target: { tabId }, world: 'MAIN', func: fetchInPage, args: [part, from, to, CONC, GAP] });
        res = r2 && r2[0] && r2[0].result || res;
      }
      for (const s of part) out[s] = res[s] || { err: 'no-result' };
    } catch (e) {
      // 分頁可能被關掉或正在跳轉：重新取得分頁再試一次
      helperTabId = null;
      try {
        tabId = await getHelperTab();
        const r = await chrome.scripting.executeScript({ target: { tabId }, world: 'MAIN', func: fetchInPage, args: [part, from, to, CONC, GAP] });
        const res = r && r[0] && r[0].result || {};
        for (const s of part) out[s] = res[s] || { err: 'no-result' };
      } catch (e2) { for (const s of part) out[s] = { err: 'inject:' + (e2 && e2.message || e2) }; }
    }
  }
  return out;
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
    const jobs = (msg.slugs || []).slice(0, 200);
    const out = await quoteAll(jobs, msg.from, msg.to);
    const shared = await share(msg.from, msg.to, out);
    send({ ok: true, from: msg.from, to: msg.to, res: out, shared });
  })();
  return true;
});
