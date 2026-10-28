const fs=require('fs'),path=require('path');const P=require('./otparse.js');
const R=process.env.ORD_REPO||'.';
const L=JSON.parse(fs.readFileSync(R+'/indexes/laws.json','utf8')),O=JSON.parse(fs.readFileSync(R+'/indexes/ordinances.json','utf8'));
const C=L.map(x=>[x.name,0,'','','',(x.info||{})['법령명약칭']||'']);const idx=P.otIdx(C);const onm=new Map(O.map(x=>[P.otN(x.name),x.name]));
const rd=p=>{const t=fs.readFileSync(path.join(R,p),'utf8');return t.startsWith('---')?t.split('\n---\n').slice(1).join('\n---\n'):t};
const lawArts={};for(const x of L){const m=new Map();for(const a of P.otArts(rd(x.path)))if(!m.has(a.k))m.set(a.k,a);for(const a of P.otBpyo(rd(x.path)))if(!m.has(a.k))m.set(a.k,{k:a.k,x:a.x});lawArts[x.name]=m}
const bodies={};for(const x of O)bodies[x.id]=rd(x.path).replace(/^\s*#\s.*\n/,'').trim();
const oart={};for(const x of O){const m=new Map();for(const a of P.otArts(bodies[x.id]))if(!m.has(a.k))m.set(a.k,a);oart[x.name]=m}
const miss=[],ext=[],del=[];
function loc(b,pos){const pre=b.slice(0,pos);let bu=false;const bi=pre.lastIndexOf('## 부칙');
  const H=/^제(\d+)조(?:의(\d+))?(?:\(([^)\n]*)\))?/gm;let m,last=null;while((m=H.exec(pre)))last=m;
  let a=last?(bu||bi>=0&&last.index>bi?'부칙 ':'')+'제'+last[1]+'조'+(last[2]?'의'+last[2]:'')+(last[3]?'('+last[3]+')':''):'(조문 앞부분)';
  if(bi>=0&&!last)a='부칙';
  const seg=last?pre.slice(last.index):pre;const C='①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳㉑㉒㉓㉔㉕㉖㉗㉘㉙㉚';let hang='';for(let i=seg.length-1;i>=0;i--){const k=C.indexOf(seg[i]);if(k>=0){hang=' 제'+(k+1)+'항';break}}
  let ho='';const lines=seg.split('\n');for(let i=lines.length-1;i>=0;i--){const mm=/^\s*(\d+)(?:의(\d+))?\.\s/.exec(lines[i]);if(mm){ho=' 제'+mm[1]+(mm[2]?'의'+mm[2]:'')+'호';break}if(/[①-㉚]/.test(lines[i].slice(0,3)))break}
  const ls=pre.lastIndexOf('\n')+1,le=b.indexOf('\n',pos);const line=b.slice(ls,le<0?b.length:le).replace(/\s+/g,' ').trim();
  return {where:a+hang+ho,line:line.length>260?line.slice(Math.max(0,pos-ls-110),pos-ls+120):line}}const num=k=>{const m=/제(\d+)조(?:의(\d+))?/.exec(k);return [+m[1],+(m[2]||0)]};
for(const x of O){const b=bodies[x.id];const A=P.otAlias(b,idx);
  for(const r of P.otRefs(b,A,idx,onm)){const src=r.t==='l'?lawArts[r.n]:oart[r.n];if(src&&src.get(r.jo)){const a=src.get(r.jo);if(/^제\d+조(?:의\d+)?\s*(?:\([^)]*\)\s*)?삭제/.test(a.x.split('\n')[0].trim()))del.push({where:loc(b,r.s).where,line:loc(b,r.s).line,delx:a.x.split('\n')[0].trim(),ord:x.name,law:r.n,jo:r.jo,ctx:b.slice(Math.max(0,r.s-40),r.e+20).replace(/\n/g,' ')});continue}
    const L0=loc(b,r.s);const ctx=b.slice(Math.max(0,r.s-40),r.e+20).replace(/\n/g,' ');const pre=b.slice(Math.max(0,r.s-90),r.s);const expl=/」\s?(?:\([^)\n]{0,30}\)\s?)?$/.test(pre)||/」[^「\n]{0,40}$/.test(pre)&&!/(?:^|[^가-힣])(?:법|영|규칙|시행령|시행규칙)\s?$/.test(pre);
    let cls='',note='';
    if(!src){cls='대상없음';}
    else if(/^별표/.test(r.jo))cls='별표 없음(이미지·한글 파일만 있거나 삭제)';else{const [n,s]=num(r.jo);const keys=[...src.keys()];const mx=Math.max(...keys.filter(k=>/^제/.test(k)).map(k=>num(k)[0]));
      if(s&&src.get('제'+n+'조'))cls='가지번호없음(본조는 있음)';
      else if(n>mx)cls='조문수 초과(최종 제'+mx+'조)';
      else{ // within range but absent
        cls='번호 공백(삭제·이동 추정)';}}
    miss.push({where:L0.where,line:L0.line,expl,ord:x.name,kind:x.kind,dept:x.dept,law:r.n,jo:r.jo,t:r.t,cls,ctx})}
  // external refs not in repo
  const re=/「([^」\n]{2,80})」\s?(?:\([^)\n]{0,30}\)\s?)?제(\d+)조(?:의(\d+))?/g;let m;while((m=re.exec(b))){const k=P.otN(m[1]);if(!idx.has(k)&&!onm.has(k))ext.push({where:loc(b,m.index).where,line:loc(b,m.index).line,ord:x.name,law:m[1],jo:P.otJo(m[2],m[3])})}}
fs.writeFileSync('audit.json',JSON.stringify({miss,ext,del}));
const cnt={};miss.forEach(r=>cnt[r.cls]=(cnt[r.cls]||0)+1);console.log(miss.length,cnt);
const e={};ext.forEach(r=>e[r.law]=(e[r.law]||0)+1);console.log(ext.length,Object.keys(e).length,Object.entries(e).sort((a,b)=>b[1]-a[1]).slice(0,15))
