# 從 src/ 組出倉庫根目錄的 index.html 與 guest.html
# 用法：python3 src/build_deploy.py（在倉庫根目錄執行）
import os, shutil
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'src')
rd = lambda f: open(os.path.join(SRC, f), encoding='utf-8').read()
t = rd('template_bi.html')
h = t.replace('/*DATA*/', rd('data_bi.js')).replace('/*PHOTOS*/', rd('photos.js')).replace('/*EXTRA*/', rd('extra_bi.js')).replace('/*ROOMS*/', rd('rooms_bi.js') if os.path.exists(os.path.join(SRC,'rooms_bi.js')) else '')
old = "const HOSTED=false, MAPS_KEY='', AVAIL_URL='';/*HOSTCFG*/"
new = "const HOSTED=true, MAPS_KEY=(window.OUTO_CFG&&window.OUTO_CFG.MAPS_KEY)||'', AVAIL_URL='https://script.google.com/macros/s/AKfycbzvqcI0xCpSHgDeUvMmwzP0DNryB8XdpdxAd1QmvB2arWUp_QeEdwPnP-2D-W2TIUGd0w/exec';"
assert h.count(old) == 1
head = '<!doctype html><html lang="zh-Hant-TW"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="robots" content="noindex,nofollow"><script src="config.js"></script><script src="pub.js?v=2"></script><script src="pub_extra.js?v=2"></script><script src="pubav.js?v=2"></script></head><body>'
out = head + h.replace(old, new) + '</body></html>'
for f in ('index.html', 'guest.html'):
    open(os.path.join(ROOT, f), 'w', encoding='utf-8').write(out)
print('built', len(out))
