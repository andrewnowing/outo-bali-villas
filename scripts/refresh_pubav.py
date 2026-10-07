#!/usr/bin/env python3
"""Refresh pubav.js: booked date ranges for Villa Finder public-site villas.
Reads the villa list from pub.js, fetches each public page, extracts the
`:unavailabilities` attribute of #request-form, writes pubav.js.
Runs every 4 hours on GitHub Actions. 10 parallel workers with a short pause each; backs off on HTTP 429.
"""
import json, re, sys, time, datetime, html, os, urllib.request, urllib.error
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pubrates

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src = open(os.path.join(ROOT, 'pub.js'), encoding='utf-8').read()
villas = json.loads(re.search(r'const PUB_VILLAS=(\[.*?\]);\n', src, re.S).group(1))
static_by = {v['s']: v for v in villas}
# live prices (rates table / default price / promotion) parsed from the same pages -> pubrates.js
rates = {}; rate_stat = {'ok': 0, 'norates': 0, 'badrate': 0, 'diff': 0}
old_rates = {}
try:
    o = open(os.path.join(ROOT, 'pubrates.js'), encoding='utf-8').read()
    old_rates = json.loads(re.search(r'const PUBRATES=(\{.*\});', o, re.S).group(1)).get('by', {})
except Exception:
    pass
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
noattr = 0
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
    if not m:
        with lock:
            global noattr; noattr += 1
    if m:
        try: unav = json.loads(html.unescape(m.group(1)))
        except Exception: unav = []
    live, st = pubrates.parse(body)
    with lock:
        by[v['s']] = to_ranges(unav); ok += 1
        rate_stat[st] += 1
        if st == 'ok' or live['dp'] is not None:
            if st != 'ok': live['r'] = []; live['b'] = []
            rates[v['s']] = live
            if pubrates.differs(live, static_by.get(v['s'])): rate_stat['diff'] += 1
        elif v['s'] in old_rates:
            rates[v['s']] = old_rates[v['s']]
        if (ok + err) % 100 == 0: print(f'{ok+err}/{len(villas)} ok={ok} err={err} {int(time.time()-t0)}s', flush=True)
    time.sleep(0.1)
with ThreadPoolExecutor(max_workers=12) as ex:
    list(ex.map(work, villas))

if noattr > len(villas) * 0.3:
    # page layout changed (attribute renamed/moved): writing empty ranges would show every villa as free
    print(f'unavailabilities attribute missing on {noattr} pages; keeping previous pubav.js', file=sys.stderr)
    sys.exit(2)
if ok < len(villas) * 0.7:
    print(f'too many failures ({ok}/{len(villas)}), keeping previous pubav.js', file=sys.stderr)
    sys.exit(1)

now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime('%Y-%m-%dT%H:%M:%S+08:00')
changed = sum(1 for k, v in by.items() if old.get(k) != v)
hist = ([{'t': now, 'feeds': ok, 'errors': err, 'changed': changed, 'noattr': noattr, 'rates': rate_stat['ok'], 'norates': rate_stat['norates'], 'pricediff': rate_stat['diff']}] + hist)[:120]
out = {'updatedAt': now, 'by': by, 'ok': ok, 'err': err, 'history': hist}
open(os.path.join(ROOT, 'pubav.js'), 'w', encoding='utf-8').write('const PUBAV=' + json.dumps(out, separators=(',', ':')) + ';\n')
# prices: write pubrates.js (the workflow commits it only when it changed)
if rate_stat['norates'] + rate_stat['badrate'] > len(villas) * 0.5 and old_rates:
    print(f"rates table missing on {rate_stat['norates']} pages; keeping previous pubrates.js", file=sys.stderr)
else:
    # rolling 14-day range of the public "from" price (it moves with Villa Finder's dynamic pricing)
    old_h = {}
    try: old_h = json.loads(re.search(r'const PUBRATES=(\{.*\});', o, re.S).group(1)).get('dph', {})
    except Exception: pass
    cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=14)).strftime('%Y-%m-%d')
    dph = {}
    for s_, L in rates.items():
        if L.get('r') or L.get('dp') is None: continue
        h = old_h.get(s_)
        if not h or h[2] < cutoff: h = [L['dp'], L['dp'], now[:10]]
        dph[s_] = [min(h[0], L['dp']), max(h[1], L['dp']), h[2]]
    rout = {'updatedAt': now, 'by': rates, 'stats': rate_stat, 'dph': dph}
    open(os.path.join(ROOT, 'pubrates.js'), 'w', encoding='utf-8').write('const PUBRATES=' + json.dumps(rout, separators=(',', ':')) + ';\n')
print(f"done ok={ok} err={err} rates={rate_stat} in {int(time.time()-t0)}s")
