"""Breakfast status from a Villa Finder public villa page.
The "Services & features" list has <li class="services__item"> rows; a row whose icon carries the
`extra-cost` class is a paid item. Breakfast rows look like:
  "Breakfast included" / "Breakfast included on the first day only" / "Floating breakfast included"
  "Breakfast (150,000 IDR/person)" / "Breakfast (menu system)" / "Breakfast (contact us)"   (all extra-cost)
Output per villa: [code, breakfast text or None, floating-breakfast text or None]
  codes: inc (daily), first (first day only), floatinc (floating breakfast included), paid (price known),
         req (on request / menu / contact us), none (no breakfast item on the page)
Same shape as BF in src/extra_bi.js so the page can use one lookup.
"""
import re
from html.parser import HTMLParser

class _Items(HTMLParser):
    def __init__(self):
        super().__init__(); self.items = []; self._depth = 0; self._cur = None
    def handle_starttag(self, tag, attrs):
        a = dict(attrs); cls = a.get('class', '') or ''
        if tag == 'li' and 'services__item' in cls:
            self._cur = {'text': [], 'extra': False}; self._depth = 1; return
        if self._cur is not None:
            if tag in ('img', 'br', 'input', 'hr', 'meta', 'link', 'source', 'path', 'use'): return
            self._depth += 1
            if 'extra-cost' in cls.split(): self._cur['extra'] = True
    def handle_endtag(self, tag):
        if self._cur is not None:
            if tag in ('img', 'br', 'input', 'hr', 'meta', 'link', 'source', 'path', 'use'): return
            self._depth -= 1
            if self._depth <= 0:
                t = re.sub(r'\s+', ' ', ''.join(self._cur['text'])).strip()
                self.items.append((t, self._cur['extra'])); self._cur = None
    def handle_data(self, data):
        if self._cur is not None: self._cur['text'].append(data)

def _zh_price(t):
    m = re.search(r'\(([^)]*)\)', t)
    if not m: return None
    p = m.group(1).strip()
    m2 = re.match(r'([\d.,]+)\s*(IDR|USD)\s*/\s*(person|pax|pers)', p, re.I)
    if m2: return f'早餐（每人 {m2.group(2).upper()} {m2.group(1)}）'
    if re.search(r'contact us', p, re.I): return '早餐（價格另詢）'
    if re.search(r'menu', p, re.I): return '早餐（依菜單計價）'
    return f'早餐（{p}）'

def parse(body):
    p = _Items()
    try: p.feed(body)
    except Exception: pass
    bf = [(t, x) for t, x in p.items if re.match(r'^(floating )?breakfast\b', t, re.I)]
    if not bf: return ['none', None, None]
    code, txt, flt = 'none', None, None
    for t, extra in bf:
        low = t.lower()
        if low.startswith('floating'):
            if not extra and 'included' in low: flt = '含漂浮早餐'; code = code if code != 'none' else 'floatinc'
            else:
                m = re.search(r'\(([^)]*)\)', t); flt = '漂浮早餐（' + (m.group(1) if m else '價格另詢') + '）'
            continue
        if not extra:
            if 'first day' in low: code = 'first'
            elif 'included' in low: code = 'inc'
            else: code = 'inc' if code == 'none' else code
        else:
            z = _zh_price(t)
            if z and re.search(r'\d', z): code, txt = 'paid', z
            elif code not in ('inc', 'first'): code, txt = 'req', z
    return [code, txt, flt]
