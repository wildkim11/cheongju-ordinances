const fs=require('fs'),path=require('path');const P=require('./otparse.js');
const R=process.env.ORD_REPO;const out=process.argv[2]||'ot.json';
const L=JSON.parse(fs.readFileSync(path.join(R,'indexes/laws.json'),'utf8'));
const O=JSON.parse(fs.readFileSync(path.join(R,'indexes/ordinances.json'),'utf8'));
const C=L.map(x=>[x.name,0,'','','',(x.info||{})['법령명약칭']||'']);
const idx=P.otIdx(C);const onm=new Map(O.map(x=>[P.otN(x.name),x.name]));
// 옛 이름·약칭·표기가 다른 이름 → 현행(또는 저장된) 이름
const al={},rn={};
for(const x of L){for(const a of [...(x.aliases||[]),...(x.replaces?[x.replaces]:[])]){const k=P.otN(a);if(!k||idx.has(k))continue;idx.set(k,x.name);al[k]=x.name}
  if(x.historic&&x.renamed_to)rn[x.name]=x.renamed_to}
// 이름이 바뀐 조례: indexes/ordin_alias.json 에서 확실한 것만 (사람이 확인할 것은 HOLD)
const HOLD=new Set(['청주시 학교급식 지원에 관한 조례','청주시 외국인주민 및 다문화가족 지원 조례','청주시 정신건강복지센터 및 중독관리통합지원센터 설치ㆍ운영에 관한 조례','청주시 도시림 및 가로수 조성ㆍ관리 조례']);
const FORCE={'청주시 빈집 정비 조례':'청주시 빈집 및 소규모주택 정비에 관한 조례'};
const dice=(a,b)=>{const g=s=>{const m=new Map();for(let i=0;i<s.length-1;i++){const k=s.slice(i,i+2);m.set(k,(m.get(k)||0)+1)}return m};const A=g(a),B=g(b);let n=0;for(const[k,v]of A)n+=Math.min(v,B.get(k)||0);return 2*n/Math.max(1,a.length+b.length-2)};
const oa={},oe={};const oaLog=[];
const ap=path.join(R,'indexes/ordin_alias.json');
if(fs.existsSync(ap)){const AL=JSON.parse(fs.readFileSync(ap,'utf8'));
  for(const[old,v]of Object.entries(AL)){const k=P.otN(old);if(onm.has(k))continue;const hs=(v.hits||[]);if(!hs.length)continue;
    const isR=/규칙$/.test(P.otN(old));const same=hs.filter(h=>isR?/규칙/.test(h.kind):h.kind==='조례');
    const ex=hs.find(h=>P.otN(h.name)===k);let pick=null;
    let est=HOLD.has(old);if(FORCE[old]){pick={name:FORCE[old]};est=true}else if(ex)pick=ex;else if(same.length===1)pick=same[0];
    else if(same.length>1){const sc=same.map(h=>[dice(k,P.otN(h.name)),h]).sort((a,b)=>b[0]-a[0]);if(sc[0][0]>=0.5&&sc[0][0]-sc[1][0]>=0.12){pick=sc[0][1];est=true}}
    if(pick&&onm.has(P.otN(pick.name))&&P.otN(pick.name)!==k){oa[k]=pick.name;if(est)oe[k]=1;onm.set(k,pick.name);oaLog.push(old+' → '+pick.name+(est?' (추정)':''))}}}
const lawFut={},lawEf={};const lawArts={};for(const x of L){const t=fs.readFileSync(path.join(R,x.path),'utf8');const b=t.startsWith('---')?t.split('\n---\n').slice(1).join('\n---\n'):t;const m=new Map();for(const a of P.otArts(b))if(!m.has(a.k))m.set(a.k,a.x);for(const a of P.otBpyo(b))if(!m.has(a.k))m.set(a.k,a.x);lawArts[x.name]=m;const fm=(t.match(/조문시행일자문자열:\s*"([^"]*)"/)||[])[1]||'';if(!x.historic){lawFut[x.name]=fm;lawEf[x.name]=(x.info||{})['시행일자']||''}}
const o={},l={};let nref=0,miss=0,missL=new Map();const bodies={};
for(const x of O){const t=fs.readFileSync(path.join(R,x.path),'utf8');let b=t.startsWith('---')?t.split('\n---\n').slice(1).join('\n---\n'):t;b=b.replace(/^\s*#\s.*\n/,'').trim();o[x.id]=b;bodies[x.id]=b}
const oart={};for(const x of O){const m=new Map();for(const a of P.otArts(bodies[x.id]))if(!m.has(a.k))m.set(a.k,a.x);oart[x.name]=m}
for(const x of O){const b=bodies[x.id];const A=P.otAlias(b,idx);for(const r of P.otRefs(b,A,idx,onm)){nref++;
  if(r.t==='l'){const m=lawArts[r.n];if(!m){missL.set(r.n,(missL.get(r.n)||0)+1);continue}const tx=m.get(r.jo);if(tx){(l[r.n]=l[r.n]||{})[r.jo]=tx}else miss++}
  else{const m=oart[r.n];if(!(m&&m.get(r.jo)))miss++}}}
const asofS=((JSON.parse(fs.readFileSync(path.join(R,'reports/latest-sync.json'),'utf8')).checkedAt||'').slice(0,10)).replace(/-/g,'');
const ttl=tx=>{const m=/^제\d+조(?:의\d+)?\(([^)\n]*)\)/.exec(String(tx).trim());return m?m[1]:''};
const cur={};for(const [on,nn] of Object.entries(rn)){if(!l[on]||!lawArts[nn])continue;const tm=new Map();for(const [jo,tx] of lawArts[nn]){const t=ttl(tx);if(!t||/^별표/.test(jo))continue;(tm.get(t)||tm.set(t,[]).get(t)).push(jo)}
  for(const [jo,tx] of Object.entries(l[on])){const t=ttl(tx);const c=t?tm.get(t):null;const e=(cur[on]=cur[on]||{});if(c&&c.length===1)e[jo]={n:nn,j:c[0],t:lawArts[nn].get(c[0])};else e[jo]=null}}
const fu={},lf={};for(const [n,arts] of Object.entries(l)){const fm=lawFut[n];if(lawEf[n]&&lawEf[n]>asofS)lf[n]=lawEf[n];if(!fm)continue;
  for(const ln of fm.split('\\n')){const i=ln.indexOf(':');if(i<0)continue;const d=ln.slice(0,i).trim();if(!(d>asofS))continue;const items=ln.slice(i+1).split(',').map(z=>z.trim());
    for(const jo of Object.keys(arts)){if(items.some(z=>z.startsWith(jo)&&!/^의\d/.test(z.slice(jo.length)))){(fu[n]=fu[n]||{})[jo]=d}}}}
console.log('cur',Object.entries(cur).map(([k,v])=>k+':'+Object.values(v).filter(Boolean).length+'/'+Object.keys(v).length).join(' | '));console.log('fu',JSON.stringify(fu),'lf',Object.keys(lf).length);
const up=[];const upIdx=new Map();
for(const x of L){if(x.historic)continue;const ef=(x.info||{})['시행일자']||'';const fm=lawFut[x.name]||'';const arts=[];
  for(const ln of fm.split('\\n')){const i=ln.indexOf(':');if(i<0)continue;const d=ln.slice(0,i).trim();if(!(d>asofS))continue;
    for(const z of ln.slice(i+1).split(',').map(z=>z.trim())){const mm=/^제\d+조(?:의\d+)?/.exec(z);if(!mm)continue;const tx=lawArts[x.name]&&lawArts[x.name].get(mm[0]);arts.push([mm[0],ttl(tx||''),d])}}
  {const sn=new Set();for(let i=arts.length-1;i>=0;i--){const k=arts[i][0]+arts[i][2];if(sn.has(k))arts.splice(i,1);else sn.add(k)}}
  const lfE=ef>asofS?ef:'';if(lfE||arts.length){upIdx.set(x.name,up.length);up.push([x.name,x.kind||'',lfE,arts,'repo',x.revision||''])}}
let upa='';try{const UP=JSON.parse(fs.readFileSync(path.join(R,'indexes/upcoming.json'),'utf8'));upa=UP.asof||'';
  for(const z of (UP.laws||[])){const k=upIdx.get(z.name);const ar=(z.arts||[]).map(a=>[a[0],a[1],a[2]||z.eff||'']);if(k!=null){up[k][4]='both';if(!up[k][2])up[k][2]=z.eff||'';if(z.rev)up[k][5]=z.rev;if(!up[k][3].length&&ar.length)up[k][3]=ar;if(z.prev)up[k][6]=z.prev}else{upIdx.set(z.name,up.length);up.push([z.name,z.kind||'',z.eff||'',ar,'api',z.rev||'',z.prev||''])}}}catch(e){console.log('upcoming.json 없음')}
console.log('up',up.length);
let dga='';
const dg={};try{const DG=JSON.parse(fs.readFileSync(path.join(R,'indexes/delegations.json'),'utf8'));dga=DG.asof||'';for(const [n,v] of Object.entries(DG.laws||{})){if(!(v.items||[]).length)continue;dg[n]=[v.kind,v.items.map(z=>[z.jo,z.title,(z.s[0]||'').slice(0,170)]),v.eff||'']}}catch(e){console.log('delegations.json 없음')}
console.log('dg laws',Object.keys(dg).length);
const ms={o:{},l:{},d:{}};for(const x of O)if(x.mst&&(x.status||'active')==='active')ms.o[x.id]=x.mst;const lmst=new Map(L.map(x=>[x.name,x.mst]));for(const n of Object.keys(l))if(lmst.get(n))ms.l[n]=lmst.get(n);
try{const DG2=JSON.parse(fs.readFileSync(path.join(R,'indexes/delegations.json'),'utf8'));for(const n of Object.keys(dg)){const v=(DG2.laws||{})[n];if(v&&v.mst)ms.d[n]=v.mst}}catch(e){}
ms.u={};try{const UP2=JSON.parse(fs.readFileSync(path.join(R,'indexes/upcoming.json'),'utf8'));const tmp={};for(const x of UP2.laws||[])(tmp[x.name]=tmp[x.name]||[]).push(String(x.mst));for(const n of Object.keys(tmp))ms.u[n]=tmp[n].sort().join(',')}catch(e){}
fs.writeFileSync(out,JSON.stringify({o,l,al,rn,oa,oe,cur,fu,lf,dg,dga,up,upa,ms,asof:(JSON.parse(fs.readFileSync(path.join(R,'reports/latest-sync.json'),'utf8')).checkedAt||'').slice(0,10)}));
const sz=fs.statSync(out).size;console.log('refs',nref,'miss(no article)',miss,'laws with text',Object.keys(l).length,'cited arts',Object.values(l).reduce((a,b)=>a+Object.keys(b).length,0),'bytes',sz);
console.log('al',Object.keys(al).length,'rn',Object.keys(rn).length,'oa',Object.keys(oa).length,'oe',Object.keys(oe).length);console.log(oaLog.join('\n'));
console.log('cited laws not in repo:',[...missL.entries()].sort((a,b)=>b[1]-a[1]).slice(0,8));
