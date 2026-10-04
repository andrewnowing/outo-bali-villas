#!/usr/bin/env python3
"""Build gal/<slug>.json (photo tiles grouped by Bedrooms / Outdoor / Indoor / More)
from Villa Finder public villa pages. Runs in GitHub Actions (workflow_dispatch or weekly).
Reads villa list from pub.js + the 118 portal villas listed in gal_slugs.txt (slug<TAB>area).
"""
import json, re, os, sys, time, html, urllib.request, urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'gal'); os.makedirs(OUT, exist_ok=True)
src = open(os.path.join(ROOT, 'pub.js'), encoding='utf-8').read()
villas = [(v['s'], v['url']) for v in json.loads(re.search(r'const PUB_VILLAS=(\[.*?\]);\n', src, re.S).group(1))]
extra = os.path.join(ROOT, 'scripts', 'gal_slugs.txt')
if os.path.exists(extra):
    for line in open(extra, encoding='utf-8'):
        p = line.strip().split('\t')
        if len(p) == 2: villas.append((p[0], 'https://www.villa-finder.com/en/%s/%s' % (p[1], p[0])))
only_missing = '--missing' in sys.argv
UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36 OutoGallerySync/1.0'
SEC = {'Bedrooms': 'bed', 'Outdoor areas': 'out', 'Indoor areas': 'in', 'More pictures': 'more'}
TAG = re.compile(r'<[^>]+>')
CF = 'https://cf-img.villa-finder.com/cf/m/'

def fetch(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept-Language': 'en'})
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.status, r.read().decode('utf-8', 'replace')
        except urllib.error.HTTPError as e:
            if e.code == 429: time.sleep(15 * (i + 1)); continue
            return e.code, ''
        except Exception:
            time.sleep(5)
    return 0, ''

def parse(page, name):
    out = {}
    # split into h2 sections
    parts = re.split(r'(<h2[^>]*>.*?</h2>)', page, flags=re.S)
    for i in range(1, len(parts) - 1, 2):
        title = html.unescape(TAG.sub('', parts[i])).strip()
        title = re.sub(r'\s+', ' ', title)
        key = SEC.get(title)
        if not key: continue
        body = parts[i + 1]
        tiles = re.findall(r'<a[^>]*class="[^"]*tile--gallery[^"]*"[^>]*>(.*?)</a>', body, flags=re.S)
        items = []
        for t in tiles:
            imgs = re.findall(r'data-src="([^"]+)"', t)
            imgs = [u.replace(CF, '') for u in imgs if u.startswith(CF) and re.search(r'\.(jpe?g|webp|png)$', u, re.I)][:6]
            imgs = [re.sub(r'^villas/', '', u) for u in imgs]
            if not imgs: continue
            alt = re.search(r'alt="([^"]*)"', t)
            tt = html.unescape(alt.group(1)) if alt else ''
            if name and tt.startswith(name): tt = tt[len(name):].strip()
            text = re.sub(r'\s+', ' ', html.unescape(TAG.sub(' ', t))).strip()
            desc = text
            if tt and desc.lower().startswith(tt.lower()): desc = desc[len(tt):]
            desc = re.sub(r'^\s*\d+ pictures?\s*', '', desc).strip(' ,')
            items.append([tt or text[:30], imgs, desc[:120]])
        if items: out[key] = items
    return out

ok = err = 0; t0 = time.time()
for i, (slug, url) in enumerate(villas):
    path = os.path.join(OUT, slug + '.json')
    if only_missing and os.path.exists(path): continue
    status, page = fetch(url)
    if status != 200 or not page:
        err += 1; continue
    h1 = re.search(r'<h1[^>]*>(.*?)</h1>', page, flags=re.S)
    name = re.sub(r'\s+', ' ', html.unescape(TAG.sub('', h1.group(1)))).strip() if h1 else ''
    g = parse(page, name)
    if g:
        json.dump(g, open(path, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
        ok += 1
    if i % 100 == 0: print(f'{i}/{len(villas)} ok={ok} err={err} {int(time.time()-t0)}s', flush=True)
    time.sleep(0.5)
print(f'done ok={ok} err={err} in {int(time.time()-t0)}s')
