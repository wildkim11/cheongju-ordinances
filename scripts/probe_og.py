#!/usr/bin/env python3
"""조직 연혁 자동화 시험: 법제처 API가 연혁 판 목록과 별표 파일(hwpx·xlsb)을 내려주는지만 확인함.
LAW_OC=<인증키> python3 scripts/probe_og.py   (저장소를 바꾸지 않고 probe_og/ 폴더에만 씀)"""
import os, re, sys, json, time, urllib.request, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sync

OC = os.environ.get('LAW_OC', '').strip()
if not OC:
    sys.exit('LAW_OC(법제처 인증키)가 없어요.')
OUT = 'probe_og'
os.makedirs(OUT + '/files', exist_ok=True)
NAMES = ['청주시 행정기구 및 정원 조례 시행규칙', '청주시 행정기구 및 정원 조례', '청주시의회 교섭단체 및 위원회 구성과 운영에 관한 조례']
NWS = {'1': '연혁', '2': '시행예정', '3': '현행'}
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

# 시행규칙의 연혁 판을 최신 5개까지 받아 별표 링크와 파일을 확인
nm = NAMES[0]
allv = rep['versions'].get(nm + '|연혁') or []
cur = rep['versions'].get(nm + '|현행') or []
pick = []
for v in (cur if isinstance(cur, list) else []) + (allv if isinstance(allv, list) else []):
    if v[0] not in [p[0] for p in pick]:
        pick.append(v)
pick = sorted(pick, key=lambda v: v[2], reverse=True)[:5]
for v in pick:
    try:
        d = sync.fetch('lawService.do', {'target': 'ordin', 'type': 'XML', 'MST': v[0]}, OC, tries=2, timeout=40)
    except Exception as e:
        print('[본문] %s 오류 %s' % (v[0], str(e)[:150]), flush=True)
        continue
    txt = sync.scrub(d, OC)
    open('%s/files/%s.xml' % (OUT, v[0]), 'w', encoding='utf-8').write(txt)
    ls = links(txt)
    print('[본문] 일련번호 %s(시행 %s): 본문 %d자, 별표 링크 %d개' % (v[0], v[2], len(txt), len(ls)), flush=True)
    for i, u in enumerate(ls[:8]):
        info = {'mst': v[0], 'url': re.sub(r'(?i)OC=[^&]*', 'OC=***', u)}
        try:
            req = urllib.request.Request(u, headers={'User-Agent': sync.UA})
            with urllib.request.urlopen(req, timeout=40) as r:
                b = r.read()
                info.update(status=r.status, type=r.headers.get('Content-Type', ''), disp=r.headers.get('Content-Disposition', '')[:120], size=len(b), magic=magic(b))
            fn = '%s/files/%s_%d.bin' % (OUT, v[0], i)
            open(fn, 'wb').write(b)
        except Exception as e:
            info['error'] = str(e)[:150]
        rep['downloads'].append(info)
        print('    파일 %d: %s' % (i + 1, {k: info[k] for k in info if k != 'url'}), flush=True)
        time.sleep(0.5)

json.dump(rep, open(OUT + '/report.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
ok = sum(1 for d in rep['downloads'] if d.get('status') == 200 and d.get('size', 0) > 1000)
print('\n요약: 연혁 판 %s개 · 별표 파일 시도 %d · 정상 %d' % (len(allv) if isinstance(allv, list) else allv, len(rep['downloads']), ok))
