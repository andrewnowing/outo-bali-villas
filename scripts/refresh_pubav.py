#!/usr/bin/env python3
"""Refresh pubav.js: booked date ranges for Villa Finder public-site villas.
Reads the villa list from pub.js, fetches each public page, extracts the
`:unavailabilities` attribute of #request-form, writes pubav.js.
Runs every 4 hours on GitHub Actions. 4 parallel workers with a short pause each; backs off on HTTP 429.
"""
import json, re, sys, time, datetime, html, os, urllib.request, urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src = open(os.path.join(ROOT, 'pub.js'), encoding='utf-8').read()
villas = json.loads(re.search(r'const PUB_VILLAS=(\[.*?\]);\n', src, re.S).group(1))
old = {}; hist = []
try:
    o = open(os.path.join(ROOT, 'pubav.js'), encoding='utf-8').read()
    prev = json.loads(re.search(r'const PUBAV=(\{.*\});', o, re.S).group(1))
    old = prev.get('by', {}); hist = prev.get('history', [])
except Exception:
    pass

UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36 OutoAvailabilitySync/1.0'
ATTR = re.compile(r':unavailabilities="([^"]*)"')

def fetch(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept-Language': 'en'})
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.status, r.read().decode('utf-8', 'replace')
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(15 * (i + 1)); continue
            return e.code, ''
        except Exception:
            time.sleep(5)
    return 0, ''

def to_ranges(unav):
    out = []
    for r in unav:
        try:
            fr = datetime.date.fromisoformat(r['from']) - datetime.timedelta(days=1)
            to = datetime.date.fromisoformat(r['to']) + datetime.timedelta(days=1)
            out.append([fr.strftime('%y%m%d'), to.strftime('%y%m%d')])
        except Exception:
            pass
    return out

by = {}
ok = err = 0
t0 = time.time()
import threading
from concurrent.futures import ThreadPoolExecutor
lock = threading.Lock()
def work(v):
    global ok, err
    status, body = fetch(v['url'])
    if status != 200 or not body:
        with lock:
            err += 1
            if v['s'] in old: by[v['s']] = old[v['s']]  # keep last good data rather than dropping the villa
        return
    m = ATTR.search(body)
    unav = []
    if m:
        try: unav = json.loads(html.unescape(m.group(1)))
        except Exception: unav = []
    with lock:
        by[v['s']] = to_ranges(unav); ok += 1
        if (ok + err) % 100 == 0: print(f'{ok+err}/{len(villas)} ok={ok} err={err} {int(time.time()-t0)}s', flush=True)
    time.sleep(0.3)
with ThreadPoolExecutor(max_workers=4) as ex:
    list(ex.map(work, villas))

if ok < len(villas) * 0.7:
    print(f'too many failures ({ok}/{len(villas)}), keeping previous pubav.js', file=sys.stderr)
    sys.exit(1)

now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime('%Y-%m-%dT%H:%M:%S+08:00')
changed = sum(1 for k, v in by.items() if old.get(k) != v)
hist = ([{'t': now, 'feeds': ok, 'errors': err, 'changed': changed}] + hist)[:120]
out = {'updatedAt': now, 'by': by, 'ok': ok, 'err': err, 'history': hist}
open(os.path.join(ROOT, 'pubav.js'), 'w', encoding='utf-8').write('const PUBAV=' + json.dumps(out, separators=(',', ':')) + ';\n')
print(f'done ok={ok} err={err} in {int(time.time()-t0)}s')
