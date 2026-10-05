/**
 * Outo 峇里島別墅查詢頁 — 監控與自動修復（Google Apps Script）
 *
 * 安裝（一次）：
 * 1. script.google.com → 新專案 → 貼上本檔 → 儲存。
 * 2. 專案設定 → 指令碼屬性，新增：
 *      GH_TOKEN   = GitHub fine-grained token（只給 outo-bali-villas 的 Actions: Read and write）
 *      ALERT_TO   = andrew@outo.co
 * 3. 執行一次 setup()（會要求授權：寄信、外部連線）。它會建立「每 15 分鐘」觸發器。
 * 4. 部署 → 新增部署 → 類型「網頁應用程式」→ 執行身分「我」、存取權「任何人」→ 複製網址，
 *    貼到網站 config.js 的 WATCH_URL（網頁會用它回報 Google Maps 金鑰／帳務錯誤）。
 *
 * 每 15 分鐘檢查：
 *   A. 官網房況（pubav.js）更新時間是否超過 20 分鐘 → 寄信 + 自動重新啟動 GitHub 接力鏈
 *   B. 最近一次抓取是否大量失敗（errors / noattr）→ 寄信
 *   C. GitHub 接力鏈是否還在跑（最近 15 分鐘有沒有 run）→ 沒有就自動重啟 + 寄信
 *   D. 網站 https://outo-bali-villas.vercel.app 是否打得開 → 寄信
 *   E. 同業價 118 間（Apps Script 房況）更新時間是否超過 3 小時 → 寄信（AVAIL_URL 填了才檢查）
 * 同一種警報 6 小時內只寄一次；恢復正常時寄一封「已恢復」。
 */
const REPO = 'andrewnowing/outo-bali-villas';
const RAW = 'https://raw.githubusercontent.com/' + REPO + '/main/pubav.js';
const SITE = 'https://outo-bali-villas.vercel.app/';
const AVAIL_URL = ''; // 118 間同業價房況的 Apps Script 網址（與 config.js 的 AVAIL_URL 相同）；留空則跳過檢查 E
const STALE_MIN = 20;         // 官網房況多久沒更新算異常
const AVAIL_STALE_MIN = 180;  // 118 間多久沒更新算異常
const MUTE_HOURS = 6;         // 同一警報重複寄信的間隔

function setup() {
  ScriptApp.getProjectTriggers().forEach(t => ScriptApp.deleteTrigger(t));
  ScriptApp.newTrigger('check').timeBased().everyMinutes(15).create();
  check();
}

function check() {
  const problems = [];
  const fixes = [];
  // A + B 官網房況
  let pubav = null;
  try {
    const txt = UrlFetchApp.fetch(RAW + '?t=' + Date.now(), { muteHttpExceptions: true }).getContentText();
    pubav = JSON.parse(txt.replace(/^const PUBAV=/, '').replace(/;\s*$/, ''));
  } catch (e) { problems.push(['pubav_unreadable', '讀不到 pubav.js：' + e]); }
  if (pubav) {
    const age = (Date.now() - new Date(pubav.updatedAt).getTime()) / 60000;
    if (age > STALE_MIN) problems.push(['pubav_stale', '官網房況已 ' + Math.round(age) + ' 分鐘沒更新（最後：' + pubav.updatedAt + '）']);
    const h = (pubav.history || [])[0] || {};
    if (h.errors > 300) problems.push(['pubav_errors', '最近一次抓取失敗 ' + h.errors + ' 間（可能被 Villa Finder 封鎖）']);
    if (h.noattr > 300) problems.push(['pubav_layout', 'Villa Finder 頁面格式改變：' + h.noattr + ' 頁找不到房況欄位，程式已停止寫入以免全部顯示有空房']);
  }
  // C GitHub 接力鏈
  const gh = ghRuns_();
  if (gh.error) problems.push(['gh_api', 'GitHub API 讀不到：' + gh.error]);
  else {
    const latest = gh.runs[0];
    const minsSince = latest ? (Date.now() - new Date(latest.created_at).getTime()) / 60000 : 999;
    const failing = gh.runs.slice(0, 3).filter(r => r.conclusion === 'failure').length;
    if (minsSince > 15) {
      problems.push(['gh_chain_dead', '更新接力鏈已停止（最近一次 run 在 ' + Math.round(minsSince) + ' 分鐘前）']);
      const ok = ghDispatch_();
      fixes.push(ok ? '已自動重新啟動接力鏈' : '自動重啟失敗（檢查 GH_TOKEN 權限）');
    } else if (failing >= 3) problems.push(['gh_failing', '最近 3 次更新都失敗，請到 GitHub Actions 看紀錄']);
  }
  // D 網站
  try {
    const r = UrlFetchApp.fetch(SITE + '?t=' + Date.now(), { muteHttpExceptions: true, followRedirects: true });
    if (r.getResponseCode() !== 200) problems.push(['site_down', '網站回應 HTTP ' + r.getResponseCode()]);
  } catch (e) { problems.push(['site_down', '網站打不開：' + e]); }
  // E 118 間
  if (AVAIL_URL) {
    try {
      const d = JSON.parse(UrlFetchApp.fetch(AVAIL_URL, { muteHttpExceptions: true }).getContentText());
      const ts = d.updatedAt || d.updated_at || d.ts;
      const age = ts ? (Date.now() - new Date(ts).getTime()) / 60000 : 999;
      if (age > AVAIL_STALE_MIN) problems.push(['avail_stale', '同業價 118 間房況已 ' + Math.round(age) + ' 分鐘沒更新']);
    } catch (e) { problems.push(['avail_unreadable', '118 間房況資料讀不到：' + e]); }
  }
  notify_(problems, fixes);
}

// 網頁回報（Google Maps 金鑰／帳務錯誤、瀏覽器端發現資料過舊）
function doPost(e) {
  let body = {};
  try { body = JSON.parse(e.postData.contents); } catch (_) {}
  const kind = String(body.kind || 'page').slice(0, 40);
  const msg = String(body.msg || '').slice(0, 500);
  const allowed = { gm_auth: 'Google 地圖金鑰或帳務錯誤（地圖無法顯示）', gm_load: 'Google 地圖程式載入失敗', stale_in_page: '網頁端讀到的房況資料過舊' };
  if (allowed[kind]) notify_([[kind, allowed[kind] + (msg ? '：' + msg : '')]], [], true);
  return ContentService.createTextOutput('ok');
}

function notify_(problems, fixes, fromPage) {
  const props = PropertiesService.getScriptProperties();
  const to = props.getProperty('ALERT_TO') || 'andrew@outo.co';
  const now = Date.now();
  const active = JSON.parse(props.getProperty('ACTIVE') || '{}'); // {key: lastMailTs}
  const fresh = [];
  problems.forEach(([key, text]) => {
    const last = active[key] || 0;
    if (now - last > MUTE_HOURS * 3600e3) { fresh.push(text); active[key] = now; }
  });
  if (!fromPage) {
    const nowKeys = new Set(problems.map(p => p[0]));
    const recovered = Object.keys(active).filter(k => !nowKeys.has(k) && !k.startsWith('gm_') && k !== 'stale_in_page');
    if (recovered.length) {
      MailApp.sendEmail(to, '[Outo 別墅查詢] 已恢復正常', '以下狀況已恢復：\n- ' + recovered.join('\n- ') + '\n\n' + Utilities.formatDate(new Date(), 'Asia/Taipei', 'yyyy-MM-dd HH:mm'));
      recovered.forEach(k => delete active[k]);
    }
  }
  if (fresh.length) {
    const body = '發現以下狀況：\n- ' + fresh.join('\n- ') + (fixes.length ? '\n\n自動處理：\n- ' + fixes.join('\n- ') : '') +
      '\n\n查看：' + SITE + '\nGitHub Actions：https://github.com/' + REPO + '/actions\n' + Utilities.formatDate(new Date(), 'Asia/Taipei', 'yyyy-MM-dd HH:mm');
    MailApp.sendEmail(to, '[Outo 別墅查詢] 異常：' + fresh[0].slice(0, 40), body);
  }
  props.setProperty('ACTIVE', JSON.stringify(active));
}

function ghRuns_() {
  const tok = PropertiesService.getScriptProperties().getProperty('GH_TOKEN');
  try {
    const r = UrlFetchApp.fetch('https://api.github.com/repos/' + REPO + '/actions/workflows/refresh-pubav.yml/runs?per_page=5',
      { headers: tok ? { Authorization: 'Bearer ' + tok, Accept: 'application/vnd.github+json' } : { Accept: 'application/vnd.github+json' }, muteHttpExceptions: true });
    if (r.getResponseCode() !== 200) return { error: 'HTTP ' + r.getResponseCode() };
    return { runs: JSON.parse(r.getContentText()).workflow_runs || [] };
  } catch (e) { return { error: String(e) }; }
}

function ghDispatch_() {
  const tok = PropertiesService.getScriptProperties().getProperty('GH_TOKEN');
  if (!tok) return false;
  const r = UrlFetchApp.fetch('https://api.github.com/repos/' + REPO + '/actions/workflows/refresh-pubav.yml/dispatches', {
    method: 'post', contentType: 'application/json', muteHttpExceptions: true,
    headers: { Authorization: 'Bearer ' + tok, Accept: 'application/vnd.github+json' },
    payload: JSON.stringify({ ref: 'main', inputs: { chain: 'true' } }) });
  return r.getResponseCode() === 204;
}
