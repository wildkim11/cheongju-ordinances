# 조례·규칙과 상위법령(DB.OD)을 조례 저장소에서 다시 만드는 스크립트 (마스터 HTML → 새 마스터 HTML)
# 사용: ORD_REPO=<조례 저장소 clone 경로> python3 od_refresh.py <마스터.html> <새마스터.html>
#  - 저장소: GitHub wildkim11/cheongju-ordinances (indexes/ordinances.json, indexes/laws.json, 조례 본문 md). 얕게 clone하면 돼요.
#  - 조례마다 담당부서·전화번호·공포일·시행일·제개정 구분을 담고, 본문에서 「…」로 인용한 법령을 뽑아 상위법령으로 붙여요.
#  - 법령 목록(laws.json)에 있는 법령은 법제처 일련번호로 바로 연결하고, 목록에 없는 법령(장애인복지법 등)은 이름으로 찾는 주소를 써요.
#  - 「청주시 …」로 시작하는 인용은 다른 조례를 인용한 것으로 보고 조례끼리의 인용(O 행 10번째 값)으로 담아요.
#  - 소관위원회는 앱에서 부서 이름으로 맞춰요(부서·위원회 연혁 기준). 그래서 여기서는 위원회를 저장하지 않아요.
import json,re,os,sys,gzip,base64
LAWISH=re.compile(r'(법|법률|령|규칙|규정|특별법|기본법)$')
def norm(s):return re.sub(r'\s+','',str(s)).replace('ㆍ','·')
def build(R):
    O=json.load(open(os.path.join(R,'indexes/ordinances.json'),encoding='utf-8'))
    L=json.load(open(os.path.join(R,'indexes/laws.json'),encoding='utf-8'))
    C=[];cidx={}
    def addc(name,mst=0,kind='',min_='',eff='',ab=''):
        k=norm(name)
        if k in cidx:return cidx[k]
        cidx[k]=len(C);C.append([name,mst,kind,min_,eff,ab]);return cidx[k]
    key={}
    for x in L:
        i=addc(x['name'],x.get('mst') or 0,x.get('kind',''),x.get('ministry',''),x.get('effective',''),(x.get('info') or {}).get('법령명약칭','') or '')
        key[norm(x['name'])]=i
        ab=(x.get('info') or {}).get('법령명약칭')
        if ab:key[norm(ab)]=i
    onames={norm(x['name']):n for n,x in enumerate(O)}
    out=[]
    REV={'제정':0,'일부개정':1,'전부개정':2}
    for x in O:
        t=open(os.path.join(R,x['path']),encoding='utf-8').read()
        body=t.split('\n---\n',1)[-1] if t.startswith('---') else t
        cites=[];orefs=[]
        for c in re.findall(r'「([^」]{2,60})」',body):
            k=norm(c.strip())
            if k==norm(x['name']):continue
            if k in key:
                i=key[k]
                if i not in cites:cites.append(i)
            elif k in onames:
                n=onames[k]
                if n not in orefs:orefs.append(n)
            elif k.startswith('청주시'):continue
            elif LAWISH.search(k) and not re.search(r'[0-9]',k) and len(k)>=3:
                i=addc(c.strip())
                if i not in cites:cites.append(i)
        inf=x.get('info') or {}
        out.append([x['id'],x['name'],'조' if x['kind']=='조례' else '규',inf.get('담당부서명',''),inf.get('전화번호',''),x.get('mst') or 0,x.get('promulgated',''),x.get('effective',''),REV.get(x.get('revision') or inf.get('제개정정보'),1),sorted(cites),sorted(orefs)])
    asof=max([x.get('checked','')[:10] for x in O+L] or [''])
    return {'O':out,'C':C,'asof':asof}
def main():
    if len(sys.argv)<3:sys.exit(__doc__)
    MASTER,OUT=os.path.abspath(sys.argv[1]),os.path.abspath(sys.argv[2])
    R=os.environ.get('ORD_REPO','')
    if not R or not os.path.isdir(R):sys.exit('ORD_REPO 에 조례 저장소 clone 경로를 지정하세요.')
    OD=build(R)
    html=open(MASTER,encoding='utf-8').read()
    mm=re.search(r'<script id="data"[^>]*data-enc="gz64"[^>]*>(.*?)</script>',html,re.S)
    D=json.loads(gzip.decompress(base64.b64decode(mm.group(1))).decode('utf-8'))
    old=D.get('OD') or {}
    D['OD']=OD
    new=base64.b64encode(gzip.compress(json.dumps(D,ensure_ascii=False,separators=(',',':')).encode('utf-8'),9)).decode()
    open(OUT,'w',encoding='utf-8').write(html[:mm.start(1)]+new+html[mm.end(1):])
    print('== 이번에 바뀐 것: 조례·규칙',len(old.get('O',[])),'→',len(OD['O']),'건 · 인용 법령',len(old.get('C',[])),'→',len(OD['C']),'개 · 기준일',old.get('asof','-'),'→',OD['asof'])
    print('OD ->',OUT)
if __name__=='__main__':main()
