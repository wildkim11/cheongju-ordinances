const fs=require('fs'),path=require('path');const P=require('./otparse.js');
const R=process.env.ORD_REPO||'.';
const L=JSON.parse(fs.readFileSync(R+'/indexes/laws.json','utf8')),O=JSON.parse(fs.readFileSync(R+'/indexes/ordinances.json','utf8'));
const C=L.map(x=>[x.name,0,'','','',(x.info||{})['법령명약칭']||'']);const idx=P.otIdx(C);const onm=new Map(O.map(x=>[P.otN(x.name),x.name]));
const rd=p=>{const t=fs.readFileSync(path.join(R,p),'utf8');return t.startsWith('---')?t.split('\n---\n').slice(1).join('\n---\n'):t};
const lawArts={};for(const x of L){const m=new Map();for(const a of P.otArts(rd(x.path)))if(!m.has(a.k))m.set(a.k,a);for(const a of P.otBpyo(rd(x.path)))if(!m.has(a.k))m.set(a.k,{k:a.k,x:a.x});lawArts[x.name]=m}
const bodies={};for(const x of O)bodies[x.id]=rd(x.path).replace(/^\s*#\s.*\n/,'').trim();
const oart={};for(const x of O){const m=new Map();for(const a of P.otArts(bodies[x.id]))if(!m.has(a.k))m.set(a.k,a);oart[x.name]=m}
function loc(b,pos){const pre=b.slice(0,pos);let bu=false;const bi=pre.lastIndexOf('## 부칙');
  const H=/^제(\d+)조(?:의(\d+))?(?:\(([^)\n]*)\))?/gm;let m,last=null;while((m=H.exec(pre)))last=m;
  let a=last?(bu||bi>=0&&last.index>bi?'부칙 ':'')+'제'+last[1]+'조'+(last[2]?'의'+last[2]:'')+(last[3]?'('+last[3]+')':''):'(조문 앞부분)';
  if(bi>=0&&!last)a='부칙';
  const seg=last?pre.slice(last.index):pre;const C='①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳㉑㉒㉓㉔㉕㉖㉗㉘㉙㉚';let hang='';for(let i=seg.length-1;i>=0;i--){const k=C.indexOf(seg[i]);if(k>=0){hang=' 제'+(k+1)+'항';break}}
  let ho='';const lines=seg.split('\n');for(let i=lines.length-1;i>=0;i--){const mm=/^\s*(\d+)(?:의(\d+))?\.\s/.exec(lines[i]);if(mm){ho=' 제'+mm[1]+(mm[2]?'의'+mm[2]:'')+'호';break}if(/[①-㉚]/.test(lines[i].slice(0,3)))break}
  const ls=pre.lastIndexOf('\n')+1,le=b.indexOf('\n',pos);const line=b.slice(ls,le<0?b.length:le).replace(/\s+/g,' ').trim();
  return {where:a+hang+ho,line:line.length>260?line.slice(Math.max(0,pos-ls-110),pos-ls+120):line}}const num=k=>{const m=/제(\d+)조(?:의(\d+))?/.exec(k);return [+m[1],+(m[2]||0)]};

const T=JSON.parse(fs.readFileSync('ot.json','utf8'));
for(const k in (T.al||{}))if(!idx.has(k))idx.set(k,T.al[k]);for(const k in (T.oa||{}))if(!onm.has(k))onm.set(k,T.oa[k]);
const abbr=new Map();for(const x of L){const a=(x.info||{})['법령명약칭'];if(a)abbr.set(P.otN(a),x.name)}
const rnN=new Set(Object.keys(T.rn||{}).map(P.otN));const oeN=new Set(Object.keys(T.oe||{}));
const rows=[];const seen=new Set();
for(const x of O){const b=bodies[x.id];const A=P.otAlias(b,idx);
  const defd=new Set();{const re=/\(이하\s*[“"'‘]([^”"'’\n]{1,30})[”"'’]/g;let m;while((m=re.exec(b)))defd.add(P.otN(m[1]))}
  for(const r of P.otRefs(b,A,idx,onm)){if(!r.q)continue;const qn=P.otN(r.q),nn=P.otN(r.n);if(qn===nn&&!(r.t==='l'&&rnN.has(qn)))continue;
    const L0=loc(b,r.s);const key=x.name+'|'+L0.where+'|'+qn;if(seen.has(key))continue;seen.add(key);
    let ty,dg;
    if(r.t==='o'){ty='옛 이름';dg=oeN.has(qn)?'현행 조례 이름으로 이어 줌(추정) → 인용 표기를 현행 이름으로 정비 검토':'현행 조례 이름으로 이어 줌 → 인용 표기를 현행 이름으로 정비 검토'}
    else if(abbr.has(qn)){if(defd.has(qn)){continue}ty='약칭 미정의';dg='법령 약칭을 쓰면서 조례 안에서 약칭을 정하지 않음 → 「이하 “…”라 한다」 추가 또는 정식 명칭 사용 검토'}
    else if(rnN.has(qn)){ty='옛 이름';const nw=Object.entries(T.rn||{}).find(([k])=>P.otN(k)===qn);dg='법령 이름이 「'+(nw?nw[1]:'')+'」(으)로 바뀜 → 현행 명칭으로 정비 검토'}
    else {ty='표기 차이';dg='정식 명칭과 글자·띄어쓰기가 다름 → 정식 명칭으로 정비 검토'}
    rows.push({ord:x.name,where:L0.where,line:L0.line,q:r.q,n:r.n,ty,dg,t:r.t})}}
fs.writeFileSync('audit6.json',JSON.stringify(rows));const c={};rows.forEach(r=>c[r.ty]=(c[r.ty]||0)+1);console.log(rows.length,c);
