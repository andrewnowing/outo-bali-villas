import json,re,os,shutil
BASE='/tmp/claude-0/-home-claude/7d65f0f0-0338-50a5-a298-bf5a05a2899b/scratchpad/'
G=json.load(open(BASE+'vf2/outo_gal.json'))
out=BASE+'deploy/gal/'
os.makedirs(out,exist_ok=True)
n=0;empty=0;beds=0
for slug,g in G.items():
    if not isinstance(g,dict) or g.get('err'): empty+=1; continue
    o={}
    for k in ('bed','out','in','more'):
        arr=g.get(k) or []
        clean=[]
        for item in arr:
            title,imgs,desc=(item+['',[],''])[:3]
            title=re.sub(r'\s+',' ',title).strip()
            desc=re.sub(r'\s+',' ',desc or '').strip()
            if desc.lower().startswith(title.lower()): desc=desc[len(title):].strip(' ,')
            desc=re.sub(r'^\d+ pictures?\s*','',desc).strip(' ,')
            imgs=[i for i in imgs if i and not i.startswith('http')]
            if not imgs: continue
            clean.append([title,imgs[:6],desc[:120]])
        if clean: o[k]=clean
    if not o: empty+=1; continue
    if o.get('bed'): beds+=1
    json.dump(o,open(out+slug+'.json','w'),ensure_ascii=False,separators=(',',':'))
    n+=1
print('written',n,'empty',empty,'with bedrooms',beds)
