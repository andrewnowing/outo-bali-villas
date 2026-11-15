// 背景程式：替 Outo 查詢頁向 Villa Finder 的報價 API 拿「指定日期、所有房數」的實際報價。
// 只做 GET，不登入、不送表單；一律以美元回傳（currency=usd）。
// 拿到的報價會再送到 Outo 的共享報價收集器（/api/quotes），讓沒裝擴充功能的同事也看得到。
//
// 1.2.2：第一次查價時自己開的 VF 分頁還沒載完就逾時（25 秒等 status complete），回「找不到可用的 Villa Finder 分頁」。
// 改成輪詢分頁、只要停在別墅頁且文件可用就開查，等最久 45 秒、失敗自動換備用別墅網址重試。
//
// 1.2.0 起：報價請求不再由背景程式直接發出，而是在一個 villa-finder.com 的分頁裡執行。
// 原因：2026-10-21 後 Villa Finder 的 Cloudflare 只放行從自家「別墅頁面」發出的 API 請求
//（2026-11-03 實測：從別墅頁 fetch 回 200，從首頁或擴充功能背景 fetch 一律 403）。
// 做法是找一個已開在別墅頁的 villa-finder.com 分頁（沒有就開一個釘選、不切換過去的分頁），
// 用 chrome.scripting 把查價的函式注入該分頁的頁面環境執行，等於「從 VF 自己的頁面查」。
const VF_ORIGIN = 'https://www.villa-finder.com';
// 任何別墅頁都可以當宿主。1.2.2 起直接用「最終網址」（/en/bali/<slug> 會被 VF 連轉兩次才到 /en/<區域>/<slug>），
// 並準備備用別墅：第一間載不出來（逾時、下架、卡在 Cloudflare 檢查頁）就換下一間。
const HELPER_URLS = [
  VF_ORIGIN + '/en/kerobokan/villa-ananda',
  VF_ORIGIN + '/en/seminyak/alice-estate',
  VF_ORIGIN + '/en/ubud/katak-villa',
];
const HELPER_URL = HELPER_URLS[0];
// 等分頁準備好的時間：第一次最長 45 秒，換備用別墅各 25 秒（總共約 95 秒，仍在查詢頁 4 分鐘逾時內）
const HELPER_WAIT = [45e3, 25e3, 25e3];
const VILLA_PAGE_RE = /^https:\/\/www\.villa-finder\.com\/en\/[^\/?#]+\/[^\/?#]+/;
const SHARE_URL = 'https://outo-bali-villas.vercel.app/api/quotes';
// 1.2.1 起：Villa Finder 也加了頻率限制。2026-11-03 實測：每 5 秒一筆，第 13 筆回 429、Retry-After 3600 秒，
// 跟速度快慢無關，大約是「每小時 12 筆」。所以一次只查一筆、每筆間隔 GAP 毫秒、每個請求最多 MAX_PER_REQ 間，
// 每小時最多 HOURLY_BUDGET 筆（滾動一小時，留 2 筆餘裕）；收到 429 就記下 Retry-After，封鎖期間不再打 VF。
const CONC = 1, GAP = 5000, BATCH = 10, MAX_PER_REQ = 10, HOURLY_BUDGET = 10;

// 429 封鎖與每小時用量都存在 storage.local，service worker 睡著再醒也不會忘
async function getRate() {
  try { const s = await chrome.storage.local.get(['vfCoolUntil', 'vfHits']); return { until: +s.vfCoolUntil || 0, hits: Array.isArray(s.vfHits) ? s.vfHits : [] }; }
  catch { return { until: 0, hits: [] }; }
}
async function setRate(r) { try { await chrome.storage.local.set({ vfCoolUntil: r.until, vfHits: r.hits }); } catch {} }

let helperTabId = null, helperPromise = null;
const sleep = ms => new Promise(r => setTimeout(r, ms));
const errMsg = e => String(e && e.message || e);

// 自己開的釘選分頁 id 記在 storage.session：service worker 睡著再醒也找得回來，不會一直開新分頁
async function getOwnId() { try { const s = await chrome.storage.session.get('ownTab'); return s && s.ownTab != null ? s.ownTab : null; } catch { return null; } }
async function setOwnId(id) { try { await chrome.storage.session.set({ ownTab: id }); } catch {} }

// 等 ms 毫秒，或該分頁有任何更新就提早醒來（輪詢為主、onUpdated 只是加速，不會漏掉早就 complete 的分頁）
function waitTabEvent(tabId, ms) {
  return new Promise(res => {
    const done = () => { clearTimeout(timer); chrome.tabs.onUpdated.removeListener(fn); res(); };
    const fn = (id) => { if (id === tabId) done(); };
    const timer = setTimeout(done, ms);
    chrome.tabs.onUpdated.addListener(fn);
  });
}

// 看分頁裡現在是什麼：注入一個小函式讀 readyState / 標題 / 網址。注入失敗（還在跳轉、錯誤頁）回 null
async function probeTab(tabId) {
  try {
    const r = await Promise.race([
      chrome.scripting.executeScript({ target: { tabId }, world: 'ISOLATED', injectImmediately: true, func: () => {
        const title = document.title || '';
        const txt = (document.body && document.body.innerText || '').slice(0, 400);
        return {
          rs: document.readyState, url: location.href, title,
          // Cloudflare「Just a moment…」檢查頁：會自己跳回別墅頁，要繼續等
          challenge: /just a moment|checking your browser|請稍候|verify you are human/i.test(title) || !!document.querySelector('#challenge-form,#challenge-running,#cf-challenge-running,.cf-browser-verification'),
          notFound: /\b404\b|not found|page introuvable/i.test(title),
        };
      } }),
      sleep(5000).then(() => null),
    ]);
    return r && r[0] && r[0].result || null;
  } catch { return null; }
}

// 等到分頁「真的」停在別墅頁上：網址符合 VILLA_PAGE_RE、文件至少 interactive、不是 Cloudflare 檢查頁。
// 不等 status==='complete'：VF 別墅頁有上百張圖和一堆追蹤碼，背景分頁要 load 完常常超過 25 秒，但查價只需要同源的頁面環境。
async function waitVillaTab(tabId, timeoutMs) {
  const end = Date.now() + timeoutMs; let last = 'helper-tab-timeout', reloaded = false;
  while (Date.now() < end) {
    const t = await chrome.tabs.get(tabId).catch(() => null);
    if (!t) throw new Error('helper-tab-gone');
    if (t.discarded && !reloaded) { reloaded = true; await chrome.tabs.reload(tabId).catch(() => {}); }
    else if (VILLA_PAGE_RE.test(t.url || '')) {
      const p = await probeTab(tabId);
      if (p && VILLA_PAGE_RE.test(p.url || '')) {
        if (p.notFound && t.status === 'complete') throw new Error('helper-not-villa');
        if (p.challenge) last = 'helper-cf-challenge';
        else if (p.rs !== 'loading') return;
        else last = 'helper-tab-loading';
      }
    } else if (t.status === 'complete' && t.url && !t.pendingUrl) {
      // 已經載完卻不在別墅頁（例如別墅下架被轉到列表頁）：這個網址不能用
      if (/^(https?|chrome-error):/.test(t.url)) throw new Error('helper-not-villa');
    }
    await waitTabEvent(tabId, 700);
  }
  throw new Error(last);
}

// 自己的釘選背景分頁：沿用之前開的；載不出來就依序換備用別墅網址（等於自動重試）
async function ownHelperTab(forceReload) {
  let id = await getOwnId();
  let tab = id != null ? await chrome.tabs.get(id).catch(() => null) : null;
  let lastErr = new Error('helper-tab-timeout');
  for (let i = 0; i < HELPER_URLS.length; i++) {
    try {
      if (!tab) tab = await chrome.tabs.create({ url: HELPER_URLS[i], active: false, pinned: true });
      else if (i > 0 || !VILLA_PAGE_RE.test(tab.url || tab.pendingUrl || '')) await chrome.tabs.update(tab.id, { url: HELPER_URLS[i] });
      else if (forceReload) { forceReload = false; await chrome.tabs.reload(tab.id); }
      await setOwnId(tab.id);
      await waitVillaTab(tab.id, HELPER_WAIT[i] || 25e3);
      return tab.id;
    } catch (e) {
      lastErr = e;
      if (errMsg(e) === 'helper-tab-gone' || /No tab with id/i.test(errMsg(e))) tab = null;
    }
  }
  throw lastErr;
}

// 回傳可用的 villa-finder.com 分頁 id；優先用使用者已開、而且已就緒的別墅頁分頁，沒有才用自己的釘選背景分頁。
async function getHelperTab() {
  if (helperPromise) return helperPromise;
  helperPromise = (async () => {
    if (helperTabId != null) {
      try { await waitVillaTab(helperTabId, 8e3); return helperTabId; } catch { helperTabId = null; }
    }
    const own = await getOwnId();
    const existing = (await chrome.tabs.query({ url: VF_ORIGIN + '/*' }))
      .filter(t => t.id !== own && !t.discarded && VILLA_PAGE_RE.test(t.url || ''))
      .sort((a, b) => (b.status === 'complete') - (a.status === 'complete'));
    for (const t of existing.slice(0, 3)) {
      try { await waitVillaTab(t.id, 8e3); helperTabId = t.id; return t.id; } catch {}
    }
    helperTabId = await ownHelperTab(false);
    return helperTabId;
  })();
  try { return await helperPromise; } finally { helperPromise = null; }
}
chrome.tabs.onRemoved.addListener(id => { if (id === helperTabId) helperTabId = null; });

// 在 VF 分頁的頁面環境裡執行：同源 fetch 報價 API。這個函式會被序列化注入，不能引用外面的變數。
function fetchInPage(slugs, from, to, conc, gap) {
  const blocked = /been blocked|Attention Required/i.test(document.title + ' ' + (document.body && document.body.innerText.slice(0, 400)));
  if (blocked) { const out = {}; for (const s of slugs) out[s] = { err: 'cf-blocked' }; return Promise.resolve({ res: out, ra: null }); }
  let ra = null; // 收到 429 時的 Retry-After（秒）
  async function one(slug) {
    const u = `/en/api/offer/${encodeURIComponent(slug)}.json?from=${from}&to=${to}&currency=usd`;
    try {
      const r = await fetch(u, { credentials: 'include', headers: { 'Accept': 'application/json' } });
      if (r.status === 429) { ra = +(r.headers.get('retry-after') || 3600) || 3600; return { err: 'http429' }; }
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
    while (i < slugs.length) {
      const s = slugs[i++];
      if (ra != null) { out[s] = { err: 'http429' }; continue; } // 已被限流：剩下的不要再打
      out[s] = await one(s);
      if (ra == null && i < slugs.length) await new Promise(r => setTimeout(r, gap));
    }
  }
  return Promise.all(Array.from({ length: conc }, worker)).then(() => ({ res: out, ra }));
}

async function quoteAll(slugs, from, to) {
  const out = {};
  const rate = await getRate(); const now = Date.now();
  rate.hits = rate.hits.filter(t => now - t < 3600e3);
  if (rate.until > now) { for (const s of slugs) out[s] = { err: 'http429' }; return { res: out, cool: rate.until }; }
  const room = Math.max(0, HOURLY_BUDGET - rate.hits.length);
  const todo = slugs.slice(0, Math.min(MAX_PER_REQ, room));
  for (const s of slugs.slice(todo.length)) out[s] = { err: 'budget' };
  if (!todo.length) return { res: out, cool: 0, budget: true };
  let tabId;
  try { tabId = await getHelperTab(); }
  catch (e) { for (const s of todo) out[s] = { err: 'helper:' + errMsg(e) }; await setRate(rate); return { res: out, cool: 0 }; }
  let cool = 0;
  async function run(part) {
    const r = await chrome.scripting.executeScript({ target: { tabId }, world: 'MAIN', injectImmediately: true, func: fetchInPage, args: [part, from, to, CONC, GAP] });
    const v = r && r[0] && r[0].result || { res: {}, ra: null };
    return v;
  }
  // 失敗的查價（注入失敗、403、找不到分頁）都不算進每小時額度：只有真的拿到報價（out[s].o）才記一筆
  function take(part, v) {
    for (const s of part) { out[s] = v.res[s] || { err: 'no-result' }; if (out[s].o) rate.hits.push(Date.now()); }
    if (v.ra != null) { cool = Date.now() + v.ra * 1000; }
  }
  for (let i = 0; i < todo.length && !cool; i += BATCH) {
    const part = todo.slice(i, i + BATCH);
    try {
      let v = await run(part);
      // 借用的分頁若不在別墅頁（例如使用者剛跳到搜尋頁）或停在 Cloudflare 檢查頁，會整批 403：
      // 改用自己的釘選別墅頁分頁（已經是自己的就重新載入）再試一次
      if (part.length && part.every(s => v.res[s] && v.res[s].err === 'http403')) {
        const own = await getOwnId();
        helperTabId = tabId = await ownHelperTab(tabId === own);
        v = await run(part);
      }
      take(part, v);
    } catch (e) {
      // 分頁可能被關掉或正在跳轉：改用自己的釘選分頁（等它就緒）再試一次
      helperTabId = null;
      try {
        helperTabId = tabId = await ownHelperTab(false);
        take(part, await run(part));
      } catch (e2) {
        const m = errMsg(e2);
        for (const s of part) out[s] = { err: (/^helper-/.test(m) ? 'helper:' : 'inject:') + m };
      }
    }
  }
  if (cool) { rate.until = cool; for (const s of todo) if (!out[s]) out[s] = { err: 'http429' }; }
  await setRate(rate);
  return { res: out, cool };
}

async function getToken() {
  try { const s = await chrome.storage.sync.get('token'); return (s && s.token || '').trim(); } catch { return ''; }
}
// 把這批報價送到共享收集器。回傳 'ok' / 'notoken' / 'httpNNN'（例如 http401 金鑰不對、http502 收集器寫不進 GitHub、http503 伺服器沒設定）/ 'err'（連不上）
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
    const q = await quoteAll(jobs, msg.from, msg.to);
    const shared = await share(msg.from, msg.to, q.res);
    send({ ok: true, from: msg.from, to: msg.to, res: q.res, shared, cool: q.cool || 0, budget: !!q.budget });
  })();
  return true;
});
