# 從 gal/*.json 的各臥室床型，整理成每棟別墅的房型組成，輸出 src/rooms_bi.js
# 用法：python3 src/vf2/rooms.py（在倉庫根目錄執行）
# ROOMS[slug] = [雙人房, 雙床房, 雙床可併, 三人房, 四人房以上, 床型未註明, 單人房]
import json, glob, os, re, collections
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STRIP = re.compile(r'\b(bathroom|bathub|bathtub|aircon|tv|wi-?fi|minibar|desk|safe|fan|terrace|balcony|dressing room|walk-in closet|shower|fridge|ensuite|shared|pool view|room with swimming pool|first floor|ground floor|upper floor|2nd floor|second floor|1st building|master bedroom|connecting bedroom|this has a)\b', re.I)

def classify(desc):
    d = STRIP.sub(' ', (desc or '').lower())
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

out = {}
tot = collections.Counter()
for f in glob.glob(os.path.join(ROOT, 'gal', '*.json')):
    slug = os.path.basename(f)[:-5]
    g = json.load(open(f, encoding='utf-8'))
    beds = g.get('bed') or []
    if not beds:
        continue
    c = [0] * 7
    for b in beds:
        k = classify(b[2] if len(b) > 2 else '')
        c[k] += 1
        tot[k] += 1
    out[slug] = c
open(os.path.join(ROOT, 'src', 'rooms_bi.js'), 'w', encoding='utf-8').write('var ROOMS=' + json.dumps(out, ensure_ascii=False, separators=(',', ':')) + ';\n')
print('villas', len(out), 'rooms by type', dict(sorted(tot.items())))
