const inp = document.getElementById('token'), msg = document.getElementById('msg');
chrome.storage.sync.get('token', s => { if (s && s.token) { inp.value = s.token; msg.textContent = '已設定（已儲存的金鑰不會顯示在查詢頁）'; } });
document.getElementById('save').addEventListener('click', () => {
  const token = inp.value.trim();
  chrome.storage.sync.set({ token }, () => { msg.textContent = token ? '已儲存，重新整理查詢頁後生效' : '已清除，之後不會分享報價'; });
});
