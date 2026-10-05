window.__outoX = async function(slug, area){
  const url='/en/'+area+'/'+slug;
  const r=await fetch(url,{credentials:'omit'});
  if(r.status===429) return {slug,err:429};
  if(!r.ok) return {slug,err:r.status};
  const html=await r.text();
  const doc=new DOMParser().parseFromString(html,'text/html');
  const o={slug,area,url};
  // request-form attrs
  const rf=doc.getElementById('request-form');
  const ga=n=>{if(!rf)return null;const v=rf.getAttribute(':'+n)??rf.getAttribute(n);if(v==null)return null;try{return JSON.parse(v);}catch(e){return v;}};
  o.unav=ga('unavailabilities')||[]; o.dp=ga('default-price'); o.promo=rf?rf.getAttribute('promotion-name'):null; o.chg=ga('changeover-days')||[]; o.cap=ga('max-capacity-with-extra-guest');
  // appState villa
  const s=[...doc.scripts].find(s=>!s.src&&/appState\['villa'\]/.test(s.textContent));
  if(s){const m=s.textContent.match(/appState\['villa'\]\s*=\s*(\{.*?\});/s);if(m){try{o.v=JSON.parse(m[1]);}catch(e){}}}
  // rates table
  const t=[...doc.querySelectorAll('table')].find(t=>t.rows[0]&&/Period/.test(t.rows[0].textContent));
  if(t){const head=[...t.rows[0].children].map(c=>c.textContent.trim());o.rateHead=head;o.rates=[...t.rows].slice(1).map(tr=>[...tr.children].map(td=>td.textContent.trim().replace(/\s+/g,' ')));}
  // accordion sections
  const secs={};
  for(const h of doc.querySelectorAll('h2')){const box=h.closest('.property__accordion');if(!box)continue;const key=h.textContent.trim().replace(/\s+/g,' ');
    if(/Services/.test(key)){const groups=[];for(const ul of box.querySelectorAll('ul')){let p=ul.previousElementSibling;let cat=p?p.textContent.trim().replace(/\s+/g,' '):'';groups.push([cat,[...ul.querySelectorAll('li')].map(li=>li.textContent.trim().replace(/\s+/g,' '))]);}o.feat=groups;}
    else if(/policies/i.test(key)){o.pol=[...box.querySelectorAll('li')].map(li=>[li.className.replace('services__item','').trim(),li.textContent.trim().replace(/\s+/g,' ')]);}
    else if(/Frequently/.test(key)){o.faq=box.innerText?box.innerText.replace(/\s+/g,' ').slice(0,3000):box.textContent.replace(/\s+/g,' ').slice(0,3000);}
    else if(/Location/.test(key)){o.loc=box.textContent.replace(/\s+/g,' ').slice(0,1500);}
    else if(/Around/.test(key)){o.around=box.textContent.replace(/\s+/g,' ').slice(0,1500);}
    else if(/Bedrooms/.test(key)){o.beds=box.textContent.replace(/\s+/g,' ').slice(0,2500);}
    else if(/Complimentary|Concierge/.test(key)){o.conc=box.textContent.replace(/\s+/g,' ').slice(0,800);}
  }
  const md=doc.querySelector('meta[name="description"]');o.desc=md?md.content:'';
  const h1=doc.querySelector('h1');o.h1=h1?h1.textContent.trim().replace(/\s+/g,' '):'';
  const ph=new Set();for(const im of doc.querySelectorAll('img')){const src=im.getAttribute('src')||im.getAttribute('data-src')||'';if(/cf-img\.villa-finder\.com\/cf\/[^"']*\/villas\//.test(src))ph.add(src.split('?')[0]);if(ph.size>=16)break;}o.ph=[...ph];
  const ld=[...doc.querySelectorAll('script[type="application/ld+json"]')].map(s=>s.textContent).join('');
  const sz=ld.match(/"floorSize":\{[^}]*"value":"?([\d.]+)/);if(sz)o.size=+sz[1];
  const ar=ld.match(/"ratingValue":([\d.]+),"reviewCount":(\d+)/);if(ar)o.rating=[+ar[1],+ar[2]];
  const bf=html.match(/[^.]{0,80}[Bb]reakfast[^.]{0,120}\./g);o.bf=bf?[...new Set(bf.map(x=>x.trim()))].slice(0,4):[];
  o.len=html.length;
  return o;
};
