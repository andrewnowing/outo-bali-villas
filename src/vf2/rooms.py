# 從 gal/*.json 的各臥室床型，整理成每棟別墅的房型組成，輸出 src/rooms_bi.js
# 用法：python3 src/vf2/rooms.py（在倉庫根目錄執行）
# ROOMS[slug] = [雙人房, 雙床房, 雙床可併, 三人房, 四人房以上, 床型未註明, 單人房]
import json, glob, os, re, collections
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STRIP = re.compile(r'\b(bedrooms? ?\d+|shared bathroom with|shared bath(room)?|bathroom|bathub|bathtub|aircon|tv|wi-?fi|minibar|desk|safe|fan|terrace|balcony|dressing room|walk-in closet|shower|fridge|ensuite|shared|pool view|room with swimming pool|first floor|ground floor|upper floor|2nd floor|second floor|1st building|master bedroom|connecting bedroom|this has a)\b', re.I)

def classify(desc):
    d = (desc or '').lower()
    d = re.sub(r'\b(king|queen|double) extra bed', r'\1 bed, single extra bed', d)
    d = re.sub(r'\btwin room\b', '2 single beds', d)
    d = STRIP.sub(' ', d)
    d = re.sub(r'[ ,]+', ' ', d).strip()
    if not d:
        return 5
    if re.search(r'can be (joined|set|converted|split)|convertible', d):
        return 2
    big = 0
    for m in re.finditer(r'(?:(\d+) )?(?:king|queen|double) beds?', d):
        big += int(m.group(1) or 1)
    bunk = 0
    for m in re.finditer(r'(?:(\d+) )?bunk', d):
        bunk += int(m.group(1) or 1)
    singles = 0
    singles += 2 * len(re.findall(r'\b2 singles?\b', d))
    singles += len(re.findall(r'(?<!2 )(?<!king )single bed', d))
    singles += len(re.findall(r'king single', d))
    cap = big * 2 + bunk * 2 + singles
    if cap == 0:
        return 5
    if cap >= 4:
        return 4
    if cap == 3:
        return 3
    if cap == 1:
        return 6
    return 1 if singles == 2 else 0

# Villa Finder 書面確認過的床型（src/vf2/bed_confirmed.json）優先於 gal/*.json 的頁面抓取
CONF_PATH = os.path.join(ROOT, 'src', 'vf2', 'bed_confirmed.json')
CONF = json.load(open(CONF_PATH, encoding='utf-8')) if os.path.exists(CONF_PATH) else {}

out = {}
roomx = {}
tot = collections.Counter()
slugs = {os.path.basename(f)[:-5] for f in glob.glob(os.path.join(ROOT, 'gal', '*.json'))} | set(CONF)
for slug in sorted(slugs):
    conf = CONF.get(slug)
    if conf:
        descs = conf['beds']
    else:
        g = json.load(open(os.path.join(ROOT, 'gal', slug + '.json'), encoding='utf-8'))
        descs = [b[2] if len(b) > 2 else '' for b in (g.get('bed') or [])]
    if not descs:
        continue
    c = [0] * 7
    for d in descs:
        k = classify(d)
        c[k] += 1
        tot[k] += 1
    out[slug] = c
    if conf:
        roomx[slug] = {'xb': conf.get('extra', ''), 'n': conf.get('note', ''), 'src': conf.get('src', '')}
open(os.path.join(ROOT, 'src', 'rooms_bi.js'), 'w', encoding='utf-8').write('var ROOMS=' + json.dumps(out, ensure_ascii=False, separators=(',', ':')) + ';\nvar ROOMX=' + json.dumps(roomx, ensure_ascii=False, separators=(',', ':')) + ';\n')
print('confirmed by Villa Finder:', len(roomx))
print('villas', len(out), 'rooms by type', dict(sorted(tot.items())))
