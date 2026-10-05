import json,re,os
BASE='/tmp/claude-0/-home-claude/7d65f0f0-0338-50a5-a298-bf5a05a2899b/scratchpad/'
def load(n):
    p=BASE+'vf2/'+n
    return json.load(open(p)) if os.path.exists(p) else {}
beds=load('outo_beds.json'); places=load('outo_places.json'); routes=load('outo_routes.json'); ph2=load('outo_ph2.json')
anch=json.load(open(BASE+'vf2/anchors.json'))
s=open(BASE+'vf/pub.js').read()
PV=json.loads(re.search(r'const PUB_VILLAS=(\[.*?\]);\n',s,re.S).group(1))
PM=json.loads(re.search(r'const PUB_META=(\{.*?\});\n',s,re.S).group(1))
d=open(BASE+'vf/data_bi.js').read(); V118=json.loads(re.search(r'const VILLAS=(\[.*?\]);\n',d,re.S).group(1)); have=set(v['s'] for v in V118)
byslug={v['s']:v for v in PV}

# ---- beds ----
def parse_beds(txt):
    if not txt: return None
    i=txt.find('Bedroom 1')
    if i<0: i=txt.find('Bedroom ')
    if i<0: return None
    seg=txt[i:]
    # cut at the end of the bedroom list: before descriptive prose (first sentence-ish long text)
    parts=re.split(r'(?=Bedroom \d+\b)',seg)
    rooms=[]
    for p in parts:
        m=re.match(r'Bedroom (\d+)\s*(.*)',p,re.S)
        if not m: continue
        body=m.group(2)
        body=re.sub(r'^\d+ pictures?\s*','',body)
        # stop at first long prose (>= 60 chars without comma-separated short tokens)
        cut=re.split(r'(?<=[a-z])\s(?=[A-Z][a-z]+ [a-z]+ [a-z]+ [a-z]+ )',body,1)[0]
        cut=cut[:160]
        rooms.append((int(m.group(1)),cut.strip(' ,')))
    if not rooms: return None
    rooms.sort()
    return rooms
def flags(rooms):
    tw=db=qd=bk=0; desc=[]
    for n,b in rooms:
        bl=b.lower()
        isT=bool(re.search(r'\b(2|two) single beds?|twin',bl))
        isB=bool(re.search(r'bunk',bl))
        isQ=bool(re.search(r'\b(2|two) (double|queen|king) beds|\bfamily\b|\b4 single|\bfour single',bl))
        isD=bool(re.search(r'king|queen|double bed|super king',bl))
        if isT: tw=1
        if isB: bk=1
        if isQ: qd=1
        if isD: db=1
        bed=[]
        if re.search(r'super king',bl): bed.append('Super King')
        elif re.search(r'king',bl): bed.append('King')
        if re.search(r'queen',bl): bed.append('Queen')
        if re.search(r'double bed',bl): bed.append('Double')
        if isT: bed.append('2 Singles')
        elif re.search(r'\b(1|one)? ?single bed\b',bl): bed.append('Single')
        if isB: bed.append('Bunk')
        if re.search(r'sofa bed|day ?bed',bl): bed.append('Sofa bed')
        desc.append((n,bed))
    return tw,db,qd,bk,desc
PUB_BEDS={};PUB_TWIN={};PUB_TWIN_EN={}
for slug,rec in beds.items():
    if slug in have or slug not in byslug: continue
    rooms=parse_beds(rec.get('beds') or '')
    if not rooms:
        PUB_BEDS[slug]=[-1,-1,-1,-1]; PUB_TWIN[slug]=['unk','Villa Finder 公開頁面沒有列出各房床型',0,'']; PUB_TWIN_EN[slug]=['unk','Bed types per room not listed on the Villa Finder public page',0,'']; continue
    tw,db,qd,bk,desc=flags(rooms)
    known=any(b for _,b in desc)
    if not known:
        PUB_BEDS[slug]=[-1,-1,-1,-1]; PUB_TWIN[slug]=['unk','公開頁面有列臥室但沒寫床型',0,'']; PUB_TWIN_EN[slug]=['unk','Rooms listed but bed types not specified',0,'']; continue
    PUB_BEDS[slug]=[tw,db,qd,bk]
    zh='；'.join(f'臥室 {n}：{"、".join(b) if b else "未註明"}' for n,b in desc)
    en='; '.join(f'Bedroom {n}: {", ".join(b) if b else "not specified"}' for n,b in desc)
    st='yes' if tw else ('no' if db else 'unk')
    PUB_TWIN[slug]=[st,zh,bk,'']; PUB_TWIN_EN[slug]=[st,en,bk,'']

# ---- places ----
PUB_GMAP={};PUB_ADDR={};PUB_RATE={}
def norm(x): return re.sub(r'[^a-z0-9]','',(x or '').lower())
for slug,ps in places.items():
    if slug in have or slug not in byslug or not isinstance(ps,list) or not ps: continue
    v=byslug[slug]; nm=norm(v['n'])
    best=None
    for p in ps:
        if p.get('d',9e9)>700: continue
        pn=norm(p.get('n'))
        simi=(nm[:6] in pn) or (pn[:6] in nm) if nm and pn else False
        lodging='lodging' in (p.get('t') or []) or re.search(r'villa|resort|hotel',pn or '')
        score=(2 if simi else 0)+(1 if lodging else 0)-p['d']/1000
        if best is None or score>best[0]: best=(score,p)
    if not best: continue
    p=best[1]
    if best[0]<1: continue   # neither name match nor lodging type -> skip
    PUB_GMAP[slug]=[p['id'],p.get('n') or v['n']]
    if p.get('a'): PUB_ADDR[slug]=re.sub(r',\s*Indonesia$','',p['a'])
    if p.get('r') is not None: PUB_RATE[slug]=[p['r'],p.get('c') or 0]

# ---- routes ----
ROUTE=None
if routes:
    ROUTE={k:v for k,v in routes.items()}
# anchors i18n additions
out={'BEDS':PUB_BEDS,'TWIN':PUB_TWIN,'TWIN_EN':PUB_TWIN_EN,'GMAP':PUB_GMAP,'ADDR':PUB_ADDR,'RATE':PUB_RATE,'ROUTE':ROUTE,'AREA_ZH':anch['area_zh'],'ANCHOR_ZH':anch['anchor_zh'],'ANCHOR_EN':anch['anchor_en']}
# photos top-up
if ph2:
    for k,urls in ph2.items():
        if k in PM and not PM[k]['ph'] and isinstance(urls,list) and urls: PM[k]['ph']=urls[:10]
    js='const PUB_META='+json.dumps(PM,ensure_ascii=False,separators=(',',':'))+';\n'
    s=re.sub(r'const PUB_META=(\{.*?\});\n',lambda m: js,s,count=1,flags=re.S)
    open(BASE+'vf/pub.js','w').write(s)
open(BASE+'vf/pub_extra.js','w').write('const PUB_X='+json.dumps(out,ensure_ascii=False,separators=(',',':'))+';\n')
print('beds',len(PUB_BEDS),'twin yes',sum(1 for t in PUB_TWIN.values() if t[0]=='yes'),'unk',sum(1 for t in PUB_TWIN.values() if t[0]=='unk'))
print('gmap',len(PUB_GMAP),'addr',len(PUB_ADDR),'rate',len(PUB_RATE),'routes',len(ROUTE or {}),'ph2',len(ph2))
print('no photos now',sum(1 for m in PM.values() if not m['ph']))
