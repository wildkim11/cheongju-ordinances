#!/usr/bin/env python3
"""조직 연혁 자동화 시험: 법제처 API가 연혁 판 목록과 별표 파일(hwpx·xlsb)을 내려주는지만 확인함.
LAW_OC=<인증키> python3 scripts/probe_og.py   (저장소를 바꾸지 않고 probe_og/ 폴더에만 씀)"""
import os, re, sys, json, time, urllib.request, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sync

OC = os.environ.get('LAW_OC', '').strip()
if not OC:
    sys.exit('LAW_OC(법제처 인증키)가 없어요.')
OUT = 'probe_og2'
os.makedirs(OUT + '/files', exist_ok=True)
NAMES = ['청주시 행정기구 및 정원 조례 시행규칙', '청주시 행정기구 및 정원 조례', '청주시의회 교섭단체 및 위원회 구성과 운영에 관한 조례']
NWS = {'1': 'nw1', '2': 'nw2', '3': 'nw3'}  # 앞선 시험: nw2가 과거 판 전체를 돌려줌
rep = {'versions': {}, 'downloads': []}


def norm(s):
    return re.sub(r'\s+', '', s or '')


def versions(name, nw):
    rows = []
    for page in range(1, 6):
        d = sync.fetch('lawSearch.do', {'target': 'ordin', 'type': 'XML', 'query': name, 'search': '1', 'display': '100', 'page': str(page), 'nw': nw}, OC, tries=2, timeout=30)
        total, rs = sync.parse_list(d)
        rows += rs
        if not rs or len(rows) >= total:
            break
    return [r for r in rows if norm(r['자치법규명']) == norm(name) and r['지자체기관명'].startswith('충청북도 청주시')]


def links(xml):
    t = xml if isinstance(xml, str) else xml.decode('utf-8', 'ignore')
    return sorted(set(re.findall(r'https?://[^\s<>"\']*flDownload\.do[^\s<>"\']*', t.replace('&amp;', '&'))))


def magic(b):
    if b[:4] == b'PK\x03\x04':
        return 'zip(hwpx·xlsx·xlsb 계열)'
    if b[:8] == bytes.fromhex('D0CF11E0A1B11AE1'):
        return 'OLE(hwp·xls)'
    if b[:4] == b'%PDF':
        return 'pdf'
    return b[:12].hex()


for name in NAMES:
    for nw, lab in NWS.items():
        try:
            rows = versions(name, nw)
        except Exception as e:
            rep['versions'][name + '|' + lab] = 'ERR ' + str(e)[:200]
            print('[목록]', name, lab, '오류', str(e)[:200], flush=True)
            continue
        rep['versions'][name + '|' + lab] = [[r['자치법규일련번호'], r['공포일자'], r['시행일자'], r['제개정구분명']] for r in rows]
        print('[목록] %s · %s: %d판' % (name, lab, len(rows)), flush=True)
        for r in rows[:30]:
            print('    일련번호 %s 공포 %s 시행 %s %s' % (r['자치법규일련번호'], r['공포일자'], r['시행일자'], r['제개정구분명']), flush=True)

# 시행규칙의 모든 판(세 목록의 합집합) 중 2022년 이후 시행분을 최신순 25개까지: 별표 링크 수와 첫 파일(별표 1~14) 내려받기 확인
nm = NAMES[0]
pick = {}
for lab in NWS.values():
    v = rep['versions'].get(nm + '|' + lab)
    for x in (v if isinstance(v, list) else []):
        pick[x[0]] = x
pick = sorted([x for x in pick.values() if x[2] >= '20220101'], key=lambda x: x[2], reverse=True)[:25]
print('\n[판 목록] 시행규칙 2022년 이후 %d판: %s' % (len(pick), ', '.join(x[2] for x in pick)), flush=True)
for v in pick:
    try:
        d = sync.fetch('lawService.do', {'target': 'ordin', 'type': 'XML', 'MST': v[0]}, OC, tries=2, timeout=40)
    except Exception as e:
        print('[본문] %s(시행 %s) 오류 %s' % (v[0], v[2], str(e)[:150]), flush=True)
        continue
    txt = sync.scrub(d, OC)
    open('%s/files/%s.xml' % (OUT, v[0]), 'w', encoding='utf-8').write(txt)
    ls = links(txt)
    info = {'mst': v[0], 'sihaeng': v[2], 'links': len(ls)}
    if ls:
        try:
            req = urllib.request.Request(ls[0], headers={'User-Agent': sync.UA})
            with urllib.request.urlopen(req, timeout=40) as r:
                bb = r.read()
                info.update(status=r.status, size=len(bb), magic=magic(bb), file=urllib.parse.unquote(r.headers.get('Content-Disposition', ''))[:90])
            open('%s/files/%s_1.bin' % (OUT, v[0]), 'wb').write(bb)
        except Exception as e:
            info['error'] = str(e)[:150]
    rep['downloads'].append(info)
    print('[판] 시행 %s 일련번호 %s: 본문 %d자 · 별표 링크 %d개 · 첫 파일 %s' % (v[2], v[0], len(txt), len(ls), {k: info[k] for k in info if k in ('status', 'size', 'magic', 'file', 'error')}), flush=True)
    time.sleep(0.4)

json.dump(rep, open(OUT + '/report.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
ok = sum(1 for d in rep['downloads'] if d.get('status') == 200 and d.get('size', 0) > 1000)
print('\n요약: 판 %d개 확인 · 첫 별표 파일 정상 %d개' % (len(rep['downloads']), ok))
