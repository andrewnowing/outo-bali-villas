// 內容腳本：在 Outo 查詢頁上標記「擴充功能已安裝」，並轉送頁面的報價請求給背景程式。
document.documentElement.dataset.outoQuote = chrome.runtime.getManifest().version;
window.addEventListener('message', (e) => {
  if (e.source !== window || !e.data || e.data.type !== 'OUTO_QUOTE_REQ') return;
  const { id, slugs, from, to } = e.data;
  chrome.runtime.sendMessage({ type: 'OUTO_QUOTE', slugs, from, to }, (resp) => {
    window.postMessage({ type: 'OUTO_QUOTE_RES', id, from, to, res: (resp && resp.res) || {}, err: chrome.runtime.lastError ? String(chrome.runtime.lastError.message) : null }, '*');
  });
});
