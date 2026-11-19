// 「검토」 후보: 글자로 뽑을 수 있는 세 가지(판정이 아니라 사람이 확인할 후보)
//  v1 상위법 용어 변경: 인용한 상위법에서 조례 최종 공포 이후 사라진 용어가 조례 본문에 남아 있음
//  v2 약칭 미사용: (이하 "…"라 한다)로 정의했는데 본문에서 쓰이지 않음
//  v3 조문 참조 확인: 조례(시행규칙은 모 조례)가 가리킨 조문이 없거나 삭제됨
const fs=require('fs'),path=require('path');const P=require('./otparse.js');
const R=process.env.ORD_REPO||'.';const ASOF=(process.env.ASOF||new Date().toISOString().slice(0,10));
const L=JSON.parse(fs.readFileSync(R+'/indexes/laws.json','utf8')),O=JSON.parse(fs.readFileSync(R+'/indexes/ordinances.json','utf8'));
const idx=P.otIdx(L.map(x=>[x.name,0,'','','',(x.info||{})['법령명약칭']||'']));const onm=new Map(O.map(x=>[P.otN(x.name),x.name]));
const rd=p=>{const t=fs.readFileSync(path.join(R,p),'utf8');return t.startsWith('---')?t.split('\n---\n').slice(1).join('\n---\n'):t};
const CI='①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳㉑㉒㉓㉔㉕㉖㉗㉘㉙㉚';
const norm=s=>String(s||'').replace(/<[^>\n]*\d{4}\.\s?\d+\.\s?\d+\.?[^>\n]*>/g,'').replace(/\s+/g,' ').trim();
const josa=/(?:으로서|으로써|에서는|에게는|이라|으로|에서|에게|까지|부터|에는|에도|이며|이고|이나|과의|와의|하여|하고|한다|에|의|을|를|은|는|이|가|과|와|도|로|만)$/;
const VERB=/(?:하여야|하여|하게|하기|하는|하도록|하지|하며|한다|된|될|한|할|하다|있는|없는|따른|대한|관한|위한)$/;
const tok=s=>{const m=new Set();for(const w of String(s).replace(/[「」()\[\]<>“”"'.,;:·ㆍ]/g,' ').split(/\s+/)){const x=w.replace(josa,'');if(x.length>=4&&/[가-힣]/.test(x)&&!/\d/.test(x)&&!VERB.test(x))m.add(x)}return m};
function core(a,b){a=norm(a);b=norm(b);let i=0;while(i<a.length&&i<b.length&&a[i]===b[i])i++;let j=0;while(j<a.length-i&&j<b.length-i&&a[a.length-1-j]===b[b.length-1-j])j++;while(i>0&&a[i-1]!==' ')i--;let ea=a.length-j,eb=b.length-j;while(ea<a.length&&a[ea]!==' ')ea++;while(eb<b.length&&b[eb]!==' ')eb++;return [a.slice(i,ea),b.slice(i,eb)]}
function loc(b,pos){const pre=b.slice(0,pos);const bi=pre.lastIndexOf('## 부칙');const H=/^제(\d+)조(?:의(\d+))?(?:\(([^)\n]*)\))?/gm;let m,last=null;while((m=H.exec(pre)))last=m;
  let a=last?(bi>=0&&last.index>bi?'부칙 ':'')+'제'+last[1]+'조'+(last[2]?'의'+last[2]:'')+(last[3]?'('+last[3]+')':''):'(조문 앞부분)';if(bi>=0&&!last)a='부칙';
  const seg=last?pre.slice(last.index):pre;let hang='';for(let i=seg.length-1;i>=0;i--){const k=CI.indexOf(seg[i]);if(k>=0){hang=' 제'+(k+1)+'항';break}}
  const ls=pre.lastIndexOf('\n')+1,le=b.indexOf('\n',pos);const line=b.slice(ls,le<0?b.length:le).replace(/\s+/g,' ').trim();
  return {where:a+hang,line:line.length>200?line.slice(Math.max(0,pos-ls-80),pos-ls+100):line}}
// 상위법별 사라진 용어(본칙 기준)
const pairs={};
for(const x of L){let ev;try{ev=JSON.parse(fs.readFileSync(R+'/history/l/'+x.id+'.json','utf8')).ev}catch(e){continue}
  const rt=rd(x.path);const bi=rt.indexOf('## 부칙');const cur=norm(bi>=0?rt.slice(0,bi):rt);const m=new Map();
  for(const e of ev){if(e.ed>ASOF)continue;for(const u of (e.u||[])){if(u[1]!=='c'||u[2]==null||u[3]==null)continue;const [co,cn]=core(u[2],u[3]);if(!co||co.length>60||cn.length>80)continue;const to=tok(co),tn=tok(cn);
    for(const w of to){if(tn.has(w)||cur.includes(w))continue;const z=m.get(w)||{d:'',to:new Set()};if(e.ed>z.d)z.d=e.ed;for(const y of tn)z.to.add(y);m.set(w,z)}}}
  if(m.size)pairs[x.name]=m}
const oByName=new Map(O.map(x=>[P.otN(x.name),x]));const out=[];
const flat=s=>String(s).replace(/[\sㆍ·]/g,'');
for(const o of O){if((o.status||'active')!=='active')continue;const b=rd(o.path).replace(/^\s*#\s.*\n/,'').trim();const bi=b.indexOf('## 부칙');const body=bi>=0?b.slice(0,bi):b;
  const A=P.otAlias(b,idx);const refs=P.otRefs(body,A,idx,onm);const opd=String(o.promulgated||'');const od=opd.slice(0,4)+'-'+opd.slice(4,6)+'-'+opd.slice(6,8);
  // v1
  const seen1=new Set();const cited=new Set(refs.filter(r=>r.t==='l').map(r=>r.n));
  for(const ln of cited){const m=pairs[ln];if(!m)continue;for(const [w,e] of m){if(e.d<=od)continue;const p=body.indexOf(w);if(p<0)continue;const dk='1'+o.name+w;if(seen1.has(dk))continue;seen1.add(dk);const L0=loc(b,p);out.push({k:1,ord:o.name,kind:o.kind,where:L0.where,line:L0.line,law:ln,w,to:[...e.to].slice(0,3),d:e.d})}}
  // v2
  {const re=/\(이하\s*[“"'‘]([^”"'’\n]{1,20})[”"'’]\s*(?:이?라)\s*한다\)/g;let m;const fb=flat(b);while((m=re.exec(b))){const w=m[1];if(/^이 (?:항|조|호)/.test(w))continue;if(fb.split(flat(w)).length-1<=1){const L0=loc(b,m.index);out.push({k:2,ord:o.name,kind:o.kind,where:L0.where,line:L0.line,w})}}}
  // v3
  const art=P.otArts(b),have=new Set(art.map(a=>a.k)),mx=Math.max(0,...art.map(a=>{const q=/제(\d+)조/.exec(a.k);return q?+q[1]:0}));
  const isDel=(arts,k)=>{const a=arts.find(z=>z.k===k);return !!a&&/^제\d+조(?:의\d+)?\s*(?:\([^)]*\)\s*)?삭제/.test(a.x.split('\n')[0].trim())};
  const par=/ 시행규칙$/.test(o.name)?oByName.get(P.otN(o.name.replace(/ 시행규칙$/,''))):null;let partArts=null,pmx=0,pHave=null;if(par){const pb=rd(par.path);partArts=P.otArts(pb);pHave=new Set(partArts.map(a=>a.k));pmx=Math.max(0,...partArts.map(a=>{const q=/제(\d+)조/.exec(a.k);return q?+q[1]:0}))}
  const skip=refs.map(r=>[r.s,r.e]);const CH=/^(?:\s?제\d+항)*(?:\s?제\d+호(?:의\d+)?)*\s?(?:,|·|ㆍ|및|또는)\s?제(\d+)조(?:의(\d+))?/;
  const aliasK=Object.keys(A||{}).filter(k=>k.length>=2&&!/^(?:시행령|시행규칙|규칙)$/.test(k));
  const seen=new Set();
  // 조례가 정한 약칭(「이하 "공유재산법"」 등)이 붙은 인용은 어디서 쓰였든 상위법 인용으로 보고 건너뜀(및·쉼표로 이어진 조문 포함)
  aliasK.forEach(k=>{const ra=new RegExp(k.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+'\\s?(?:\\([^)\\n]{0,30}\\)\\s?)?제(\\d+)조(?:의(\\d+))?','g');let q;while((q=ra.exec(body))){let e=q.index+q[0].length,rest=body.slice(e),c;while((c=CH.exec(rest))){e+=c[0].length;rest=body.slice(e)}skip.push([q.index,e])}});
  if(par){const rp=/(?<![가-힣」])조례\s?제(\d+)조(?:의(\d+))?/g;let m;while((m=rp.exec(body))){let e=m.index+m[0].length;const ks=['제'+m[1]+'조'+(m[2]?'의'+m[2]:'')];let rest=body.slice(e),c;while((c=CH.exec(rest))){ks.push('제'+c[1]+'조'+(c[2]?'의'+c[2]:''));e+=c[0].length;rest=body.slice(e)}skip.push([m.index,e]);
    for(const k of ks){if(seen.has('p'+k))continue;seen.add('p'+k);const n=+/제(\d+)/.exec(k)[1];if(!pHave.has(k)){const L0=loc(b,m.index);out.push({k:3,ord:o.name,kind:o.kind,where:L0.where,line:L0.line,jo:k,tgt:par.name,why:n>pmx?'조문 없음(모 조례 최종 제'+pmx+'조)':'번호 공백'})}else if(isDel(partArts,k)){const L0=loc(b,m.index);out.push({k:3,ord:o.name,kind:o.kind,where:L0.where,line:L0.line,jo:k,tgt:par.name,why:'삭제된 조문'})}}}}
  const rulNoPar=/ 시행규칙$/.test(o.name)&&!par;const re=/제(\d+)조(?:의(\d+))?/g;let m;
  while((m=re.exec(body))){const s=m.index,e=s+m[0].length;if(skip.some(p=>s<p[1]&&e>p[0]))continue;if(rulNoPar&&/조례\s?$/.test(body.slice(Math.max(0,s-4),s)))continue;
    const around=body.slice(Math.max(0,s-60),e+40);if(/개정규정|이동\s?<|<[^>]*\d{4}\./.test(around)||/부터\s?$/.test(body.slice(Math.max(0,s-3),s))||/^\s?(?:부터|까지)/.test(body.slice(e,e+4))||/(?:규칙|[·ㆍ])\s?$/.test(body.slice(Math.max(0,s-3),s)))continue;
    if(/부터[^.]{0,30}까지/.test(body.slice(Math.max(0,s-40),s))||/까지\s?,\s?$/.test(body.slice(Math.max(0,s-4),s)))continue;
    const ls=Math.max(body.lastIndexOf('\n',s),body.lastIndexOf('다. ',s));const sent=body.slice(ls<0?0:ls,s);
    if(/「[^」]*」/.test(sent)||/(?:^|[^가-힣])(?:법|영|령|규칙|시행령|시행규칙|같은 법|이 법)\s/.test(sent.slice(-30))||/(?:법|영|령|규칙)\s?$/.test(sent))continue;
    if(/^\s*$/.test(body.slice(body.lastIndexOf('\n',s)+1,s)))continue;
    const k='제'+m[1]+'조'+(m[2]?'의'+m[2]:'');if(seen.has(k))continue;seen.add(k);
    if(par&&pHave&&pHave.has(k)&&!have.has(k))continue;const why=!have.has(k)?(+m[1]>mx?'조문 없음(최종 제'+mx+'조)':'번호 공백'):(isDel(art,k)?'삭제된 조문':'');if(!why)continue;
    const L0=loc(b,s);out.push({k:3,ord:o.name,kind:o.kind,where:L0.where,line:L0.line,jo:k,tgt:o.name,why})}
}
fs.writeFileSync('audit4.json',JSON.stringify(out));const c={};out.forEach(r=>c['v'+r.k]=(c['v'+r.k]||0)+1);console.log('검토 후보',out.length,c);
