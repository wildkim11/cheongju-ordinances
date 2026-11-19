// 인용한 조문의 내용이 조례 최종 개정(공포) 이후에 바뀌었는지 + 바뀌기 전 용어가 조례에 그대로 남았는지 점검
// 입력: indexes/laws.json·ordinances.json, history/{l,o}/<id>.json(이전·이후 조문 전문), 출력: audit3.json
const fs=require('fs'),path=require('path');const P=require('./otparse.js');
const R=process.env.ORD_REPO||'.';const ASOF=(process.env.ASOF||new Date().toISOString().slice(0,10));
const L=JSON.parse(fs.readFileSync(R+'/indexes/laws.json','utf8')),O=JSON.parse(fs.readFileSync(R+'/indexes/ordinances.json','utf8'));
const C=L.map(x=>[x.name,0,'','','',(x.info||{})['법령명약칭']||'']);const idx=P.otIdx(C);const onm=new Map(O.map(x=>[P.otN(x.name),x.name]));
const lid=new Map(L.map(x=>[x.name,x.id])),oid=new Map(O.map(x=>[x.name,x.id]));
const rd=p=>{const t=fs.readFileSync(path.join(R,p),'utf8');return t.startsWith('---')?t.split('\n---\n').slice(1).join('\n---\n'):t};
const hcache={};function hist(t,id){const k=t+id;if(k in hcache)return hcache[k];let v=null;try{v=JSON.parse(fs.readFileSync(path.join(R,'history',t,id+'.json'),'utf8')).ev||[]}catch(e){}return hcache[k]=v}
const CI='①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳㉑㉒㉓㉔㉕㉖㉗㉘㉙㉚';
const norm=s=>String(s||'').replace(/<[^>\n]*\d{4}\.\s?\d+\.\s?\d+\.?[^>\n]*>/g,'').replace(/\[[^\]\n]*\d{4}\.\s?\d+\.\s?\d+[^\]\n]*\]/g,'').replace(/\s+/g,' ').trim();
function para(txt,n){const t=String(txt||'');const ch=CI[n-1];if(!ch)return null;const i=t.indexOf(ch);if(i<0)return null;let j=t.length;for(let k=i+1;k<t.length;k++){if(CI.indexOf(t[k])===n){j=k;break}}return t.slice(i,j)}
function diffSnip(a,b){a=norm(a);b=norm(b);let i=0;while(i<a.length&&i<b.length&&a[i]===b[i])i++;let j=0;while(j<a.length-i&&j<b.length-i&&a[a.length-1-j]===b[b.length-1-j])j++;
  const cut=(s,x,y)=>{const m=s.slice(x,s.length-y);return m.length>70?m.slice(0,70)+'…':m};const pre=a.slice(Math.max(0,i-12),i);return {o:pre+cut(a,i,j),n:pre+cut(b,i,j)}}
const josa=/(?:으로서|으로써|에서는|에게는|이라|으로|에서|에게|까지|부터|에는|에도|이며|이고|이나|과의|와의|하여|하고|한다|에|의|을|를|은|는|이|가|과|와|도|로|만)$/;
const tok=s=>{const m=new Set();for(const w of String(s||'').replace(/[「」()\[\]<>“”"'.,;:·ㆍ]/g,' ').split(/\s+/)){let x=w.replace(josa,'');if(x.length>=2&&/[가-힣]/.test(x)&&!/^\d/.test(x)&&!/^제?\d/.test(x))m.add(x)}return m};
function core(a,b){a=norm(a);b=norm(b);let i=0;while(i<a.length&&i<b.length&&a[i]===b[i])i++;let j=0;while(j<a.length-i&&j<b.length-i&&a[a.length-1-j]===b[b.length-1-j])j++;
  while(i>0&&a[i-1]!==' ')i--;let ea=a.length-j,eb=b.length-j;while(ea<a.length&&a[ea]!==' ')ea++;while(eb<b.length&&b[eb]!==' ')eb++;return [a.slice(i,ea),b.slice(i,eb)]}
const STOP=new Set(['그리고','그러나','이하','다음','각호','대통령령','조례','규칙','같다','따라','경우','있는','없는','필요한','필요','관한','하는','위한','대한','또는','및','따른','해당하','정하','하여야','있','없']);
function loc(b,pos){const pre=b.slice(0,pos);const bi=pre.lastIndexOf('## 부칙');const H=/^제(\d+)조(?:의(\d+))?(?:\(([^)\n]*)\))?/gm;let m,last=null;while((m=H.exec(pre)))last=m;
  let a=last?(bi>=0&&last.index>bi?'부칙 ':'')+'제'+last[1]+'조'+(last[2]?'의'+last[2]:'')+(last[3]?'('+last[3]+')':''):'(조문 앞부분)';if(bi>=0&&!last)a='부칙';
  const seg=last?pre.slice(last.index):pre;let hang='';for(let i=seg.length-1;i>=0;i--){const k=CI.indexOf(seg[i]);if(k>=0){hang=' 제'+(k+1)+'항';break}}
  let ho='';const lines=seg.split('\n');for(let i=lines.length-1;i>=0;i--){const mm=/^\s*(\d+)(?:의(\d+))?\.\s/.exec(lines[i]);if(mm){ho=' 제'+mm[1]+(mm[2]?'의'+mm[2]:'')+'호';break}if(/[①-㉚]/.test(lines[i].slice(0,3)))break}
  const ls=pre.lastIndexOf('\n')+1,le=b.indexOf('\n',pos);const line=b.slice(ls,le<0?b.length:le).replace(/\s+/g,' ').trim();
  return {where:a+hang+ho,sec:last?last.index:0,line:line.length>260?line.slice(Math.max(0,pos-ls-110),pos-ls+120):line}}
const out=[];const seen=new Set();let nref=0;
for(const x of O){if((x.status||'active')!=='active')continue;const b=rd(x.path).replace(/^\s*#\s.*\n/,'').trim();const A=P.otAlias(b,idx);const op=String(x.promulgated||'');const opd=op.slice(0,4)+'-'+op.slice(4,6)+'-'+op.slice(6,8);
  for(const r of P.otRefs(b,A,idx,onm)){if(/^별표/.test(r.jo))continue;const id=(r.t==='l'?lid:oid).get(r.n);if(!id)continue;if(r.t==='o'&&r.n===x.name)continue;
    const ev=hist(r.t==='l'?'l':'o',id);if(!ev)continue;nref++;
    const L0=loc(b,r.s);const mh=/^\s?제(\d+)항/.exec(b.slice(r.e));const hn=mh?+mh[1]:0;
    const hits=[];for(const e of ev){if(!(e.pd>opd)||e.ed>ASOF)continue;const u=(e.u||[]).find(z=>z[0]===r.jo&&z[1]==='c');if(u)hits.push({e,o:u[2],n:u[3]})}
    if(!hits.length)continue;hits.sort((p,q)=>p.e.pd<q.e.pd?-1:p.e.pd>q.e.pd?1:0);
    let oldT=hits[0].o,newT=hits[hits.length-1].n;if(hn){const po=para(oldT,hn),pn=para(newT,hn);if(po!=null&&pn!=null){oldT=po;newT=pn}}
    if(norm(oldT)===norm(newT))continue;if(/^(?:제\d+조(?:의\d+)?(?:\([^)]*\))?\s*)?(?:[①-㉚]\s*)?삭제\s*$/.test(norm(newT)))continue;
    const key=x.name+'|'+L0.where+'|'+r.n+'|'+r.jo+'|'+hn;if(seen.has(key))continue;seen.add(key);
    const last=hits[hits.length-1].e;const ds=diffSnip(oldT,newT);
    // 옛 용어: 이전 조문에만 있던 낱말이 조례의 해당 조(인용 문장 포함)에 그대로 있는지
    const [co,cn]=core(oldT,newT);const small=co.length<=40&&cn.length<=80;const to=small?tok(co):new Set(),tn=tok(cn);const secEnd=(()=>{const m=/\n제\d+조/.exec(b.slice(L0.sec+1));return m?L0.sec+1+m.index:b.length})();const body=b.slice(L0.sec,secEnd);
    const gone=[...to].filter(w=>!tn.has(w)&&!STOP.has(w)&&body.includes(w));
    out.push({ord:x.name,kind:x.kind,dept:x.dept||'',where:L0.where,line:L0.line,t:r.t,n:r.n,jo:r.jo,hang:hn,ed:last.ed,pd:last.pd,rv:last.rv,m:last.m,o:ds.o,nw:ds.n,terms:gone.slice(0,5),opd})}}
fs.writeFileSync('audit3.json',JSON.stringify(out));const tc=out.filter(r=>r.terms.length).length;
console.log('refs w/history',nref,'changed',out.length,'with 옛 용어',tc);
const cnt={};out.forEach(r=>cnt[r.n]=(cnt[r.n]||0)+1);console.log(Object.entries(cnt).sort((a,b)=>b[1]-a[1]).slice(0,10));
