"""Parse nightly rates / default price / promotion from a Villa Finder public villa page.
Used by refresh_pubav.py on every 5-minute run so the site's prices follow the public site.
Output per villa: {'b':[bedroom configs], 'r':[[from,to,season,minStay,price per config...]], 'dp':default price or None, 'p':promotion text}
Same conventions as src/vf2/convert.py (dates yymmdd, season codes L/M/H/P/Q).
"""
import re, json, html
from html.parser import HTMLParser

SEA = {'low season': 'L', 'mid-high season': 'M', 'mid season': 'M', 'high season': 'H', 'peak season': 'P',
       'mid-peak season': 'Q', 'sub-peak season': 'Q', 'shoulder season': 'M', 'christmas season': 'P', 'new year season': 'P'}

class _Tables(HTMLParser):
    def __init__(self):
        super().__init__(); self.tables = []; self._t = None; self._row = None; self._cell = None
    def handle_starttag(self, tag, attrs):
        if tag == 'table': self._t = []
        elif tag == 'tr' and self._t is not None: self._row = []
        elif tag in ('td', 'th') and self._row is not None: self._cell = []
    def handle_endtag(self, tag):
        if tag in ('td', 'th') and self._cell is not None and self._row is not None:
            self._row.append(re.sub(r'\s+', ' ', ''.join(self._cell)).strip()); self._cell = None
        elif tag == 'tr' and self._row is not None and self._t is not None:
            self._t.append(self._row); self._row = None
        elif tag == 'table' and self._t is not None:
            self.tables.append(self._t); self._t = None
    def handle_data(self, data):
        if self._cell is not None: self._cell.append(data)

def _ymd8(d, m, y): return '%02d%02d%02d' % (int(y) % 100, int(m), int(d))

def parse(body):
    """Return (rates dict or None, status) where status in ok | norates | badrate."""
    out = {'b': [], 'r': [], 'dp': None, 'p': ''}
    m = re.search(r'promotion-name="([^"]*)"', body)
    if m: out['p'] = html.unescape(m.group(1)).strip()
    m = re.search(r':default-price="([^"]*)"', body)
    if m:
        try:
            dp = json.loads(html.unescape(m.group(1)))
            if isinstance(dp, dict):
                v = dp.get('originalPrice')
                out['dp'] = v if isinstance(v, (int, float)) and v <= 20000 else None
                v = dp.get('discountedPrice')
                if isinstance(v, (int, float)) and v <= 20000: out['dpd'] = v
        except Exception: pass
    p = _Tables()
    try: p.feed(body)
    except Exception: pass
    table = next((t for t in p.tables if t and t[0] and re.search(r'Period', ' '.join(t[0]))), None)
    if not table:
        return out, 'norates'
    head = table[0]
    cfg = [int(re.match(r'(\d+)', h).group(1)) for h in head[3:] if re.match(r'\d+ bedroom', h)]
    rows = []
    for r in table[1:]:
        if len(r) < 4: continue
        mm = re.match(r'(\d\d)/(\d\d)/(\d{4})\s+(\d\d)/(\d\d)/(\d{4})', r[0])
        if not mm: continue
        a = _ymd8(mm[1], mm[2], mm[3]); b = _ymd8(mm[4], mm[5], mm[6])
        code = SEA.get(r[1].strip().lower(), 'M')
        ms = re.search(r'(\d+)', r[2]); ms = int(ms.group(1)) if ms else 1
        prices = []
        for x in r[3:3 + len(cfg)]:
            n = re.sub(r'[^\d]', '', x)
            prices.append(int(n) if n else None)
        if not prices or any(x is None for x in prices): continue
        rows.append([a, b, code, ms] + prices)
    if any(x > 20000 for r_ in rows for x in r_[4:]):
        return out, 'badrate'
    out['b'] = cfg; out['r'] = rows
    return out, ('ok' if rows else 'norates')

def differs(live, static):
    """True when the live page's prices differ from what pub.js carries for this villa."""
    if not static: return True
    if live['r']:
        return live['r'] != (static.get('r') or []) or (live['b'] and live['b'] != static.get('b')) or (live['p'] or '') != (static.get('p') or '')
    return live['dp'] != static.get('dp') or (live['p'] or '') != (static.get('p') or '')
