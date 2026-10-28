import json,collections,re
import os
R=os.environ.get('ORD_REPO','.').rstrip('/')+'/'
ASOF=os.environ.get('ASOF','')
d=json.load(open('audit.json'))
OO={x['name']:x for x in json.load(open(R+'indexes/ordinances.json'))}
LL=json.load(open(R+'indexes/laws.json'));nl=len(LL)
dept=lambda n:OO[n]['info'].get('담당부서명','') if n in OO else ''
kind=lambda n:OO[n]['kind'] if n in OO else ''
isL=lambda n:any(x['name']==n for x in LL)
rows1=[]
for r in d['del']:
    tgt='상위법령' if isL(r['law']) else '청주시 조례·규칙'
    rows1.append([tgt,'삭제된 조문 인용',r['ord'],kind(r['ord']),dept(r['ord']),r['where'],r['line'],r['law'],r['jo'],r['delx'],'삭제된 조문을 근거로 쓰고 있음 → 현행 조문으로 정비 검토'])
for r in d['miss']:
    tgt='상위법령' if r['t']=='l' else '청주시 조례·규칙'
    cl=r['cls']
    st={'별표 없음(이미지·한글 파일만 있거나 삭제)':'앱 저장소에 별표 본문 없음(그림·한글 파일이거나 삭제) → 원문 확인','가지번호없음(본조는 있음)':'인용한 가지 조문(제N조의M)이 현행 법령에 없음(본조는 있음) → 삭제·이동 여부 확인','조문수 초과(최종 제21조)':'인용한 조문 번호가 현재 조례에 없음(현재 21조까지)'}.get(cl,cl)
    rows1.append([tgt,'조문 없음',r['ord'],kind(r['ord']),dept(r['ord']),r['where'],r['line'],r['law'],r['jo'],st,'조문 번호 변경·삭제 여부 확인 후 정비 검토'])
rows1.sort(key=lambda x:(x[1],x[2],x[5]))
loc=collections.defaultdict(list)
for r in d['ext']:
    if r['law'].startswith('청주시'):loc[r['law']].append(r)
O=list(OO)
n=lambda s:re.sub(r'[\s·ㆍ]','',s)
rows2=[]
for k,v in loc.items():
    cand=[o for o in O if n(k)[3:9] in n(o)][:2]
    for r in v:
        bu=r['where'].startswith('부칙')
        rows2.append([r['ord'],kind(r['ord']),dept(r['ord']),r['where'],r['line'],k,', '.join(cand) if cand else '(비슷한 이름 없음)','부칙(경과조치·개칭 규정)이라 정상일 가능성 큼' if bu else '현행 목록에 같은 이름 없음 → 개칭·폐지 여부 확인 후 정비 검토'])
rows2.sort(key=lambda x:(x[7].startswith('부칙'),x[0],x[3]))
c=collections.defaultdict(lambda:[0,set()])
for r in d['ext']:
    if not r['law'].startswith('청주시'):c[r['law']][0]+=1;c[r['law']][1].add(r['ord'])
bu1=[r for r in rows1 if str(r[5]).startswith('부칙')];rows1=[r for r in rows1 if not str(r[5]).startswith('부칙')]
bu2=[r for r in rows2 if str(r[3]).startswith('부칙')];rows2=[r for r in rows2 if not str(r[3]).startswith('부칙')]
rep=json.load(open(R+'reports/latest-sync.json'))
try:cache=json.load(open(R+'indexes/laws_missing.json'))
except Exception:cache={}
nrm=lambda x:re.sub(r'[\s·ㆍ‧]','',x)
miss_set={nrm(x) for x in list(rep.get('laws_missing',[]))+list(cache)}
loc3=collections.defaultdict(list)
for r in d['ext']:
    if not r['law'].startswith('청주시') and nrm(r['law']) in miss_set:loc3[r['law']].append(r)
rows3=sorted(([k,v[0],len(v[1]),', '.join(sorted(v[1])[:3]),'법제처에서 같은 이름의 현행 법령을 못 찾음' if nrm(k) in miss_set else '아직 수집 전'] for k,v in c.items()),key=lambda x:(x[4]!='법제처에서 같은 이름의 현행 법령을 못 찾음',-x[1]))
rows3b=[[r['ord'],kind(r['ord']),dept(r['ord']),r['where'],r['line'],k,'법제처에서 같은 이름의 현행 법령을 못 찾음 → 법령명 개정·약칭 사용·오기 확인 후 정비 검토'] for k,v in sorted(loc3.items(),key=lambda x:-len(x[1])) for r in v if not r['where'].startswith('부칙')]
bu3=[[r['ord'],kind(r['ord']),dept(r['ord']),r['where'],r['line'],k,'(부칙)'] for k,v in loc3.items() for r in v if r['where'].startswith('부칙')]

a6=json.load(open('audit6.json'))
rows6=[[r['ord'],kind(r['ord']),dept(r['ord']),r['where'],r['line'],r['q'],r['n'],r['ty'],r['dg']] for r in a6]
rows6.sort(key=lambda x:(['약칭 미정의','표기 차이','옛 이름'].index(x[7]),x[0],x[3]))
nb=len(bu1)+len(bu2)+len(bu3)
S=[
 ['1 인용 오류',len(rows1),'어느 조례의 어느 조·항·호에서 무엇을 잘못 인용했는지 (삭제된 조문 인용 %d · 조문 없음 %d). 대상이 상위법령인지 청주시 조례인지 첫 열에 표시'%(len(d['del']),len(d['miss']))],
 ['2 청주시 조례 이름 불일치',len(rows2),'본칙에서 인용한 청주시 조례·규칙 이름이 현행 목록에 없음(개칭·폐지 의심)'],
 ['4 부칙 인용',nb,'부칙(경과조치·개칭 규정)에서 옛 이름·옛 조문을 인용한 곳. 대개 정상이라 오류 목록과 분리 — 이미 효력이 끝난 규정인지만 확인'],
 ['3 법령 이름 불일치',len(rows3b),'조례가 인용한 법령 이름으로 법제처에서 현행 법령을 못 찾음(개명·약칭·오기 의심) → 본칙만. 부칙은 시트 4'],
 ['5 저장소 밖 법령',len(rows3),'저장소에 없는 법령 전체(인용 횟수순)'],
 ['6 약칭·표기 불일치',len(rows6),'인용 표기가 정식 명칭과 다른 곳(약칭 미정의 · 옛 이름 · 표기 차이). 앱은 이어서 보여주지만 조례 본문 정비 대상일 수 있음']]
sh=[
 ['1 인용 오류',['대상 구분','문제 유형','인용한 조례','종류','소관','위치(조·항·호)','인용 문구(원문)','인용한 대상','인용 조문','대상의 현재 상태','조치 제안'],rows1,[12,17.9,47.6,6,16,30,70,28,12,34,34]],
 ['2 청주시 조례 이름 불일치',['인용한 조례','종류','소관','위치(조·항·호)','인용 문구(원문)','인용된 이름','현행 후보','진단'],rows2,[36,6,16,30,70,36,36,38]],
 ['3 법령 이름 불일치',['인용한 조례','종류','소관','위치(조·항·호)','인용 문구(원문)','인용된 법령 이름','진단'],rows3b,[36,6,16,30,70,40,40]],
 ['5 저장소 밖 법령',['법령(조례 표기)','인용 횟수','인용 조례 수','조례 예시(3개)','상태'],rows3,[48,10,12,70,36]],
 ['4 부칙 인용',['구분','인용한 조례','종류','소관','위치(조·항·호)','인용 문구(원문)','인용된 이름·조문','현행 후보 / 상태'],
  [['법령 조문 인용']+[r[2],r[3],r[4],r[5],r[6],r[7]+' '+r[8],r[9]] for r in bu1]+[['청주시 조례 이름 불일치']+[r[0],r[1],r[2],r[3],r[4],r[5],r[6]] for r in bu2]+[['법령 이름 불일치']+r for r in bu3],[22,36,6,16,34,70,36,36]],
 ['6 약칭·표기 불일치',['인용한 조례','종류','소관','위치(조·항·호)','인용 문구(원문)','인용된 표기','정식 명칭','유형','진단'],rows6,[36,6,16,30,70,40,40,14,50]]]
au={'d':ASOF,'t':'조례 인용 점검표 (일회성)','b':'기준: 청주시 조례·규칙 %d건 / 저장소 법령 %d개 / %s'%(len(OO),nl,ASOF),'S':S,'sh':sh,
 'rd':'위치 = 인용한 조례의 조·항·호, 인용 문구 = 그 줄의 원문, 인용 대상/조문 = 인용된 곳, 현재 상태 = 대상에서 실제로 확인된 내용',
 'nt':'앞서 “조문을 못 찾은 143건”은 줄임말(법·영) 연결 오류였고 고쳤어요'}
json.dump(au,open('au.json','w'),ensure_ascii=False,separators=(',',':'))
print([ (x[0],len(x[2])) for x in sh], len(open('au.json',encoding='utf8').read()))
