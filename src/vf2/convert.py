import json,re,sys,datetime
BASE='/tmp/claude-0/-home-claude/7d65f0f0-0338-50a5-a298-bf5a05a2899b/scratchpad/'
raw=json.load(open(BASE+'vf2/outo_pub.json'))          # {slug: extract record}
lst=json.load(open(BASE+'vf2/outo_list.json'))         # search list
_cs=open(BASE+'vf2/com_src.txt').read().split('\n')
_c20=set(_cs[0].split(':',1)[1].split()); _cu=set(_cs[1].split(':',1)[1].split())
def com_of(slug): return None if slug in _cu else (20 if slug in _c20 else 10)
featmap=json.load(open(BASE+'vf2/featmap.json'))
s=open(BASE+'vf/data_bi.js').read()
V118=json.loads(re.search(r'const VILLAS=(\[.*?\]);\n',s,re.S).group(1))
have=set(v['s'] for v in V118)
SEA={'low season':'L','mid-high season':'M','mid season':'M','high season':'H','peak season':'P','mid-peak season':'Q','sub-peak season':'Q','shoulder season':'M','christmas season':'P','new year season':'P'}
def ymd8(d,m,y): return '%02d%02d%02d'%(int(y)%100,int(m),int(d))
def rates(rec):
    rows=rec.get('rates') or []; head=rec.get('rateHead') or []
    cfg=[int(re.match(r'(\d+)',h).group(1)) for h in head[3:] if re.match(r'\d+ bedroom',h)]
    out=[];unknown=set()
    for r in rows:
        if len(r)<4: continue
        m=re.match(r'(\d\d)/(\d\d)/(\d{4})\s+(\d\d)/(\d\d)/(\d{4})',r[0])
        if not m: continue
        a=ymd8(m[1],m[2],m[3]); b=ymd8(m[4],m[5],m[6])
        code=SEA.get(r[1].strip().lower())
        if not code: unknown.add(r[1]); code='M'
        ms=re.search(r'(\d+)',r[2]); ms=int(ms.group(1)) if ms else 1
        prices=[]
        for p in r[3:3+len(cfg)]:
            n=re.sub(r'[^\d]','',p)
            prices.append(int(n) if n else None)
        if not prices or any(p is None for p in prices): continue
        out.append([a,b,code,ms]+prices)
    return cfg,out,unknown
def bf_code(rec):
    items=[i for g in (rec.get('feat') or []) for i in g[1]]
    txt=' '.join(items)
    m=[i for i in items if 'reakfast' in i]
    if not m: return None
    m.sort(key=lambda i:('loating' in i, 'included' not in i.lower()))
    t=m[0]
    if re.search(r'first day',t,re.I): return ['first',t]
    if re.search(r'included',t,re.I): return ['inc',t]
    if re.search(r'request|extra|charge|not included|available',t,re.I): return ['req',t]
    return ['req',t]
def t24(x):
    if not x: return x
    m=re.match(r'(\d{1,2})[:.](\d{2})\s*(am|pm)',x,re.I)
    if not m: return x
    h=int(m.group(1))%12+(12 if m.group(3).lower()=='pm' else 0)
    return '%02d:%s'%(h,m.group(2))
def times(rec):
    ci=co=None
    for cls,t in (rec.get('pol') or []):
        m=re.match(r'Check-in:\s*(?:after|from)?\s*(.+)',t,re.I)
        if m: ci=m[1].strip()
        m=re.match(r'Check-out:\s*(?:until|before)?\s*(.+)',t,re.I)
        if m: co=m[1].strip()
    return t24(ci),t24(co)
def feats(rec):
    f={};fe={};info={}
    for cat,items in (rec.get('feat') or []):
        if cat.startswith('More information'):
            for i in items:
                m=re.match(r'Villa size:\s*([\d,.]+)',i)
                if m: info['sz']=m.group(1).replace(',','')+' m²'
                m=re.match(r'Garden:\s*([\d,.]+)',i)
                if m: info['gd']=m.group(1).replace(',','')+' m²'
                m=re.search(r'NIB:\s*([0-9]+)',i)
                if m: info['nib']=m.group(1)
            continue
        zc=featmap.get('__cat__',{}).get(cat,cat)
        fe[cat]=items; f[zc]=[featmap.get(i,i) for i in items]
    return f,fe,info
def classify_pol(pol):
    out={'rules':[],'pay':[],'cancel':[],'incl':[],'fees':[]}
    for cls,t in pol:
        if re.match(r'Check-(in|out)',t,re.I): continue
        if 'policy-pay' in cls or re.search(r'deposit|payment|payable|balance|credit card|bank transfer',t,re.I): out['pay'].append([t,t])
        elif re.search(r'cancel|refund|non-refundable',t,re.I): out['cancel'].append([t,t])
        elif re.search(r'included|complimentary|free of charge',t,re.I): out['incl'].append([t,t])
        elif re.search(r'charge|fee|extra|surcharge|\$|USD',t,re.I): out['fees'].append([t,t])
        else: out['rules'].append([t,t])
    return out
byslug={x['s']:x for x in lst}
pub=[];meta={};av={};ppol={};pbf={};unk=set();stats={'norates':0,'nounav':0,'async':0}
for slug,rec in raw.items():
    if slug in have: continue
    L=byslug.get(slug,{})
    cfg,rows,u=rates(rec); unk|=u
    # Villa Finder data errors: IDR amounts labelled USD (e.g. 'USD 2,800,000'/night). Drop them instead of guessing.
    if any(x>20000 for r_ in rows for x in r_[4:]): rows=[]; stats['badrate']=stats.get('badrate',0)+1
    if not rows: stats['norates']+=1;
    vv=rec.get('v') or {}
    pt=vv.get('point') or L.get('g')
    g=None
    if vv.get('point'): g='%s,%s'%(vv['point'][1],vv['point'][0])
    elif L.get('g'): g='%s,%s'%(L['g'][0],L['g'][1])
    f,fe,info=feats(rec)
    x={'g':L.get('cap2') or L.get('cap') or rec.get('cap'),'st':L.get('st') or vv.get('staffNumber')}
    if rec.get('size'): x['sz']=str(rec['size'])+' m²'
    x.update(info)
    v={'n':L.get('n') or vv.get('name') or rec.get('h1'),'s':slug,'a':L.get('a') or (vv.get('location') or {}).get('name') or rec.get('area'),
       'src':'pub','b':cfg or L.get('b') or [],'r':rows,'p':rec.get('promo') or '','x':x,'g':g,'f':f,'fe':fe,
       'url':'https://www.villa-finder.com'+rec['url'],'ba':L.get('ba'),'vr':[L.get('ra'),L.get('rn')] if L.get('ra') else None,
       'com':com_of(slug),'asy':bool(L.get('async')),'api':L.get('api')}
    if not rows:
        v['dyn']=True; v['dp']=(rec.get('dp') or {}).get('originalPrice'); v['dpd']=(rec.get('dp') or {}).get('discountedPrice')
        if v['dp'] and v['dp']>20000: v['dp']=None; v['dpd']=None; stats['baddp']=stats.get('baddp',0)+1
        if not v['b']: v['b']=[L.get('br') or (rec.get('v') or {}).get('bedroomNumber') or 1]
    if L.get('async'): stats['async']+=1
    ci,co=times(rec)
    meta[slug]={'ph':rec.get('ph') or [],'desc':rec.get('desc') or ''}
    pc=classify_pol(rec.get('pol') or []); pc['ci']=ci; pc['co']=co; ppol[slug]=pc
    b=bf_code(rec)
    if b: pbf[slug]=b
    rng=[]
    for r_ in rec.get('unav') or []:
        try:
            fr=datetime.date.fromisoformat(r_['from'])-datetime.timedelta(days=1)
            to=datetime.date.fromisoformat(r_['to'])+datetime.timedelta(days=1)
            rng.append([fr.strftime('%y%m%d'),to.strftime('%y%m%d')])
        except Exception: pass
    if not rec.get('unav'): stats['nounav']+=1
    av[slug]=rng
    pub.append(v)
print('pub villas',len(pub),'stats',stats,'unknown seasons',unk)
print('commission known',sum(1 for v in pub if v['com']),'dist',{k:sum(1 for v in pub if v['com']==k) for k in set(v['com'] for v in pub)})
open(BASE+'vf/pub.js','w').write('const PUB_VILLAS='+json.dumps(pub,ensure_ascii=False,separators=(',',':'))+';\nconst PUB_META='+json.dumps(meta,ensure_ascii=False,separators=(',',':'))+';\nconst PUB_POL='+json.dumps(ppol,ensure_ascii=False,separators=(',',':'))+';\nconst PUB_BF='+json.dumps(pbf,ensure_ascii=False,separators=(',',':'))+';\n')
now=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime('%Y-%m-%dT%H:%M:%S+08:00')
open(BASE+'vf/pubav.js','w').write('const PUBAV='+json.dumps({'updatedAt':now,'by':av},separators=(',',':'))+';\n')
import os
print('pub.js',os.path.getsize(BASE+'vf/pub.js'),'pubav.js',os.path.getsize(BASE+'vf/pubav.js'))
