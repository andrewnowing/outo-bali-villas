#!/usr/bin/env python3
"""Refresh portalrates.js: seasonal rate tables and promotions for the Villa Finder
Distribution Portal villas (the 118 partner-portal villas in src/data_bi.js).

Logs in with VF_PORTAL_USER / VF_PORTAL_PASS (GitHub Secrets, never printed), reads the
portal list pages (50 villas each), parses every villa's "Rates" modal and promotion banners,
and writes portalrates.js in the same row format as data_bi.js:
  r: [[from yymmdd, to yymmdd, season L/M/H/P/Q, min nights, price per bedroom config...], ...]
  b: [bedroom configs]   p: 'promo ; promo'
Skips the run (exit 0) when portalrates.js is younger than MIN_AGE_MIN minutes, so the
5-minute availability chain only logs in to the portal about twice an hour.
"""
import json, re, sys, os, time, datetime, html, urllib.request, urllib.parse, http.cookiejar
from bs4 import BeautifulSoup

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = 'https://distribution.villa-finder.com'
MIN_AGE_MIN = int(os.environ.get('PORTAL_MIN_AGE_MIN', '25'))
USER = os.environ.get('VF_PORTAL_USER', ''); PASS = os.environ.get('VF_PORTAL_PASS', '')
SEA = {'low season': 'L', 'mid-high season': 'M', 'mid season': 'M', 'high season': 'H', 'peak season': 'P',
       'mid-peak season': 'Q', 'sub-peak season': 'Q', 'shoulder season': 'M', 'christmas season': 'P', 'new year season': 'P'}
UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36 OutoAvailabilitySync/1.0'

out_path = os.path.join(ROOT, 'portalrates.js')
prev = {}
try:
    o = open(out_path, encoding='utf-8').read()
    prev = json.loads(re.search(r'const PORTALRATES=(\{.*\});', o, re.S).group(1))
    age = (datetime.datetime.now(datetime.timezone.utc) - datetime.datetime.fromisoformat(prev['updatedAt'])).total_seconds() / 60
    if age < MIN_AGE_MIN:
        print(f'portalrates.js is {int(age)} min old; skip'); sys.exit(0)
except SystemExit:
    raise
except Exception:
    prev = {}

if not USER or not PASS:
    print('VF_PORTAL_USER / VF_PORTAL_PASS not set; skip', file=sys.stderr); sys.exit(0)

cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
opener.addheaders = [('User-Agent', UA), ('Accept-Language', 'en')]

def get(url):
    with opener.open(url, timeout=60) as r:
        return r.status, r.geturl(), r.read().decode('utf-8', 'replace')

def post(url, data):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode(), method='POST')
    with opener.open(req, timeout=60) as r:
        return r.status, r.geturl(), r.read().decode('utf-8', 'replace')

# ---- login ----
st, _, body = get(BASE + '/login')
m = re.search(r'name="_csrf_token"\s+value="([^"]+)"', body) or re.search(r'value="([^"]+)"\s+name="_csrf_token"', body)
if not m:
    print('login form not found (portal layout changed?)', file=sys.stderr); sys.exit(2)
st, url, body = post(BASE + '/login', {'_csrf_token': m.group(1), '_username': USER, '_password': PASS, '_remember_me': 'on'})
if '/login' in url or 'name="_password"' in body:
    print('portal login failed (check VF_PORTAL_USER / VF_PORTAL_PASS)', file=sys.stderr); sys.exit(3)

def ymd8(d, m_, y): return '%02d%02d%02d' % (int(y) % 100, int(m_), int(d))

def parse_page(body):
    soup = BeautifulSoup(body, 'html.parser')
    found = {}
    # promotions: list rows carry a Rates link -> #modal-rates-<slug> and banner-discount divs
    for a in soup.select('a[data-target^="#modal-rates-"], a[data-bs-target^="#modal-rates-"]'):
        slug = (a.get('data-target') or a.get('data-bs-target'))[len('#modal-rates-'):]
        tr = a.find_parent('tr')
        promos = []
        if tr:
            for b in tr.select('.banner-discount'):
                promos.append(re.sub(r'\s+', ' ', b.get_text(' ', strip=True)).strip())
        found.setdefault(slug, {})['p'] = ' ; '.join(promos)
    for modal in soup.select('.modal-rates'):
        slug = modal.get('id', '')[len('modal-rates-'):]
        t = modal.find('table')
        if not t or not slug: continue
        head = [th.get_text(' ', strip=True) for th in t.select('thead th')]
        cfg = [int(re.match(r'(\d+)', h).group(1)) for h in head if re.match(r'\d+ bedroom', h)]
        rows = []
        for tr in t.select('tbody tr'):
            cells = [re.sub(r'\s+', ' ', td.get_text(' ', strip=True)) for td in tr.find_all('td')]
            if len(cells) < 4: continue
            mm = re.search(r'(\d\d)/(\d\d)/(\d{4}).*?(\d\d)/(\d\d)/(\d{4})', cells[0])
            if not mm: continue
            a_ = ymd8(mm[1], mm[2], mm[3]); b_ = ymd8(mm[4], mm[5], mm[6])
            code = SEA.get(cells[1].strip().lower(), 'M')
            ms = re.search(r'(\d+)', cells[2]); ms = int(ms.group(1)) if ms else 1
            prices = []
            for c in cells[3:3 + len(cfg)]:
                pm = re.match(r'[A-Z]{3}\s*([\d,]+)', c)   # "USD 240 Before tax: USD 208" -> 240 (tax included)
                prices.append(int(pm.group(1).replace(',', '')) if pm else None)
            if not prices or any(p is None for p in prices): continue
            rows.append([a_, b_, code, ms] + prices)
        d = found.setdefault(slug, {})
        d['b'] = cfg; d['r'] = rows
    return found

by = {}
for page in range(1, 10):
    st, url, body = get(BASE + ('/?page=%d' % page))
    if 'name="_password"' in body:
        print('session lost while paging', file=sys.stderr); sys.exit(3)
    f = parse_page(body)
    if not f: break
    by.update(f)
    if ('page=%d' % (page + 1)) not in body: break
    time.sleep(1)

good = {s: v for s, v in by.items() if v.get('r')}
if len(good) < 60:
    print(f'only {len(good)} villas with rate tables parsed; keeping previous portalrates.js', file=sys.stderr); sys.exit(2)

# compare with data_bi.js (static)
diff = 0
try:
    s = open(os.path.join(ROOT, 'src', 'data_bi.js'), encoding='utf-8').read()
    static = {v['s']: v for v in json.loads(re.search(r'const VILLAS=(\[.*?\]);\n', s, re.S).group(1))}
    for slug, v in good.items():
        sv = static.get(slug)
        if not sv or v['r'] != sv.get('r') or (v.get('p') or '') != (sv.get('p') or ''): diff += 1
except Exception:
    static = {}

now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime('%Y-%m-%dT%H:%M:%S+08:00')
out = {'updatedAt': now, 'by': good, 'stats': {'villas': len(good), 'norates': len(by) - len(good), 'diff': diff}}
open(out_path, 'w', encoding='utf-8').write('const PORTALRATES=' + json.dumps(out, separators=(',', ':')) + ';\n')
print(f'portal rates: {len(good)} villas, {diff} differ from data_bi.js, {len(by)-len(good)} without table')
