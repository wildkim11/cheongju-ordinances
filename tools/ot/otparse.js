const otN=s=>String(s||'').replace(/\s+/g,'').replace(/ㆍ/g,'·');
const otJo=(n,m)=>'제'+n+'조'+(m?'의'+m:'');
function otArts(body){const out=[];let cur=null;const H=/^제(\d+)조(?:의(\d+))?(?:\(([^)\n]*)\))?/;
  for(const ln of String(body||'').split('\n')){if(/^##\s*부칙/.test(ln))break;if(/^#{1,6}\s/.test(ln)){cur=null;continue}
    const m=H.exec(ln);if(m){cur={k:otJo(m[1],m[2]),t:m[3]||'',x:ln};out.push(cur);continue}
    if(cur&&ln.trim())cur.x+='\n'+ln}
  return out}
function otBpyo(body){const out=[];const t=String(body||'');const i=t.indexOf('## 별표·서식');if(i<0)return out;const s=t.slice(i);
  const hs=[...s.matchAll(/^■ .*\[별표\s?(\d+)(?:의(\d+))?\](.*)$/gm)];
  for(let j=0;j<hs.length;j++){const h=hs[j];if(/삭제/.test(h[3]))continue;let seg=s.slice(h.index+h[0].length,j+1<hs.length?hs[j+1].index:s.length);
    const mm=/\n\d{4}\n\d{2}\n(?:별표|서식)\n/.exec(seg);if(mm)seg=seg.slice(0,mm.index);
    seg=seg.replace(/[ \t]+$/gm,'').replace(/\n{2,}/g,'\n').trim();if(!seg)continue;
    out.push({k:'별표 '+h[1]+(h[2]?'의'+h[2]:''),x:seg})}
  return out}
function otIdx(C){const m=new Map();for(const c of C){if(!c||!c[0])continue;m.set(otN(c[0]),c[0]);if(c[5])m.set(otN(c[5]),c[0])}return m}
const otBase=n=>String(n).replace(/\s?시행(?:령|규칙)$/,'');
function otAlias(body,idx){const A={};const txt=String(body||'');
  const re=/「([^」\n]{2,80})」\s*\(이하\s*[“"'‘]([^”"'’\n]{1,20})[”"'’]\s*(?:이?라)\s*한다\)/g;let m;
  while((m=re.exec(txt))){const nm=idx.get(otN(m[1]));A[otN(m[2])]=nm||''}
  if(A['법']===undefined){const re2=/「([^」\n]{2,80})」/g;let k;while((k=re2.exec(txt))){const raw=k[1];if(/(시행령|시행규칙|규칙|령)$/.test(otN(raw))||!/법(?:률)?$/.test(otN(raw)))continue;const nm=idx.get(otN(raw));if(nm)A['법']=nm;break}}
  if(A['법']){const b=A['법'];const y=idx.get(otN(b+' 시행령')),r=idx.get(otN(b+' 시행규칙'));if(y&&A['영']===undefined)A['영']=y;if(y&&A['시행령']===undefined)A['시행령']=y;if(r&&A['시행규칙']===undefined)A['시행규칙']=r;if(r&&A['규칙']===undefined)A['규칙']=r}
  return A}
function otRefs(text,A,idx,onm){const out=[];const R=/(「([^」\n]{2,80})」|같은\s?법(?:\s?시행령|\s?시행규칙)?|같은\s?영|같은\s?규칙|(?<![가-힣])(시행령|시행규칙|법|영|규칙)(?![가-힣]))\s?(?:\([^)\n]{0,30}\)\s?)?(?:제(\d+)조(?:의(\d+))?|\[?별표\s?(\d+)(?:의(\d+))?\]?)/g;
  const CH=/^(?:\s?제\d+항)*(?:\s?제\d+호(?:의\d+)?)*\s?(?:,|·|ㆍ|및|또는)\s?제(\d+)조(?:의(\d+))?/;
  let last=null,m;
  while((m=R.exec(text))){let t=null,n=null;const w=m[1];
    if(m[2]!=null){const k=otN(m[2]);if(idx.has(k)){t='l';n=idx.get(k)}else if(onm&&onm.has(k)){t='o';n=onm.get(k)}}
    else if(/^같은/.test(w)){if(last&&last.t==='l'&&m.index-last.e<260){const b=otBase(last.n);const f=otN(w);let nm=null;if(/시행령$/.test(f))nm=b+' 시행령';else if(/시행규칙$/.test(f))nm=b+' 시행규칙';else if(/^같은영$/.test(f))nm=/시행령$/.test(last.n)?last.n:b+' 시행령';else if(/^같은규칙$/.test(f))nm=/시행규칙$/.test(last.n)?last.n:b+' 시행규칙';else nm=b;const c=idx.get(otN(nm));if(c){t='l';n=c}}}
    else{const a=A[m[3]];if(a){t='l';n=a}}
    const bp=m[6]!=null;if(bp&&t==='o')t=null;const jo=bp?'별표 '+m[6]+(m[7]?'의'+m[7]:''):otJo(m[4],m[5]);let e=m.index+m[0].length;const lit=bp?m[0].slice(m[0].search(/\[?별표/)):jo;
    if(t){out.push({s:e-lit.length,e,t,n,jo,q:m[2]||''});last={t,n,e}}else last=null
    let rest=bp?'':text.slice(e),c;
    while((c=CH.exec(rest))){const j2=otJo(c[1],c[2]);const e2=e+c[0].length;if(t)out.push({s:e2-j2.length,e:e2,t,n,jo:j2,q:m[2]||''});e=e2;rest=text.slice(e)}
    R.lastIndex=e}
  return out}
if(typeof module!=='undefined')module.exports={otBpyo,otN,otJo,otArts,otIdx,otAlias,otRefs,otBase};
