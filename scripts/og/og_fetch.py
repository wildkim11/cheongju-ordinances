#!/usr/bin/env python3
"""법제처 API에서 조직 연혁의 재료를 내려받아 캐시 폴더에 둠.
  hw/<시행일>.txt   청주시 행정기구 및 정원 조례 판별 본문
  gs/<시행일>.txt   청주시의회 교섭단체 및 위원회 구성과 운영에 관한 조례 판별 본문
  rule/<시행일>.json 시행규칙 판별 별표 1~14(분장사무)
사용: LAW_OC=<인증키> python3 og_fetch.py <캐시폴더> [--since 20220101]"""
import os, re, sys, io, json, time, zipfile, datetime, argparse, urllib.request, urllib.parse
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
for p in (os.path.join(HERE, '..'), HERE):          # scripts/sync.py 를 찾음(scripts/og/ 에서 한 단계 위)
    if os.path.exists(os.path.join(p, 'sync.py')): sys.path.insert(0, p)
import sync
import og_xls

N_JW = '청주시 행정기구 및 정원 조례'
N_RULE = '청주시 행정기구 및 정원 조례 시행규칙'
N_GS = '청주시의회 교섭단체 및 위원회 구성과 운영에 관한 조례'

def norm(s): return re.sub(r'\s+', '', s or '')

def versions(name, oc):
    """nw=1·2·3 목록의 합집합(nw=2가 연혁 전체를 줌) → {시행일: 행}"""
    got = {}
    for nw in ('2', '1', '3'):
        for page in range(1, 6):
            try:
                d = sync.fetch('lawSearch.do', {'target': 'ordin', 'type': 'XML', 'query': name, 'search': '1', 'display': '100', 'page': str(page), 'nw': nw}, oc, tries=3, timeout=25)
            except Exception as e:
                print('  목록 오류', name, nw, str(e)[:120], flush=True); break
            total, rows = sync.parse_list(d)
            for r in rows:
                if norm(r['자치법규명']) == norm(name) and r['지자체기관명'].startswith('충청북도 청주시') and re.match(r'^\d{8}$', r['시행일자']):
                    old = got.get(r['시행일자'])
                    if not old or r['공포일자'] > old['공포일자'] or (r['공포일자'] == old['공포일자'] and int(r['자치법규일련번호']) > int(old['자치법규일련번호'])):
                        got[r['시행일자']] = r
            if not rows or len(rows) >= total: break
    return got

def body_text(row, oc):
    d = sync.fetch('lawService.do', {'target': 'ordin', 'type': 'XML', 'MST': row['자치법규일련번호']}, oc, tries=3, timeout=40)
    xml = sync.scrub(d, oc)
    _, md = sync.to_markdown(xml.encode('utf-8'), row)
    return xml, md.split('\n---\n', 1)[-1] if md.startswith('---') else md

def links(xml):
    t = xml.replace('&amp;', '&')
    return list(dict.fromkeys(re.findall(r'https?://[^\s<>"\']*flDownload\.do[^\s<>"\']*', t)))

def kind_of(b, fname=''):
    ext = os.path.splitext(fname)[1].lower()
    if ext in ('.xlsb', '.xls', '.xlsx'): return ext
    if b[:8] == bytes.fromhex('D0CF11E0A1B11AE1'): return '.xls'
    if b[:4] == b'PK\x03\x04':
        try:
            n = zipfile.ZipFile(io.BytesIO(b)).namelist()
            if 'xl/workbook.bin' in n: return '.xlsb'
            if 'xl/workbook.xml' in n: return '.xlsx'
        except Exception: pass
    return ''

def download(url):
    req = urllib.request.Request(url, headers={'User-Agent': sync.UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        b = r.read(); cd = urllib.parse.unquote(r.headers.get('Content-Disposition', ''))
    m = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)', cd)
    return b, (m.group(1) if m else '')

def duty_file(xml):
    """별표 파일 링크 중 '분장사무' 파일(별표 1~14)을 찾아 (바이트, 확장자) 반환"""
    ls = links(xml)
    # 별표 단위 본문에서 분장사무가 들어 있는 구간의 링크를 먼저 시도
    pref = []
    for blk in re.split(r'<별표단위', xml):
        if '분장사무' in blk:
            pref += links(blk)
    for u in list(dict.fromkeys(pref + ls)):
        try:
            b, fn = download(u)
        except Exception as e:
            print('   다운로드 실패', u[-40:], str(e)[:80], flush=True); continue
        if ('분장사무' in fn or u in pref) and kind_of(b, fn) in ('.xlsb', '.xls', '.xlsx'):
            return b, kind_of(b, fn)
        time.sleep(0.2)
    return None, ''

def run(cache, since='20220101', today=None):
    oc = os.environ.get('LAW_OC', '').strip()
    if not oc: sys.exit('LAW_OC(법제처 인증키)가 없어요.')
    today = today or (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)).strftime('%Y%m%d')
    for sub in ('hw', 'gs', 'rule'): os.makedirs(os.path.join(cache, sub), exist_ok=True)
    meta = {'future': [], 'missing': []}
    for name, sub in ((N_JW, 'hw'), (N_GS, 'gs'), (N_RULE, 'rule')):
        vs = versions(name, oc)
        if not vs:      # 접속 실패·응답 이상: 빈 결과로 연혁을 덮어쓰지 않도록 바로 멈춤
            sys.exit('법제처에서 「%s」 판 목록을 받지 못했어요(접속 지연 가능). 잠시 뒤 다시 실행하세요.' % name)
        print('[%s] 판 %d개: %s' % (name, len(vs), ', '.join(sorted(vs))), flush=True)
        for d in sorted(vs):
            if d > today: meta['future'].append([name, d]); continue
            if d < since and not (sub != 'rule' and d == max(k for k in vs if k < since)): continue   # 조례는 기준일 직전 판도 필요
            try:
                if sub == 'rule':
                    xml = sync.scrub(sync.fetch('lawService.do', {'target': 'ordin', 'type': 'XML', 'MST': vs[d]['자치법규일련번호']}, oc, tries=3, timeout=40), oc)
                    b, ext = duty_file(xml)
                    if not b: meta['missing'].append([name, d, '분장사무 별표 파일을 찾지 못함']); print('  ! 시행규칙 %s 별표 파일 없음' % d, flush=True); continue
                    tmp = os.path.join(cache, 'rule', d + ext); open(tmp, 'wb').write(b)
                    json.dump(og_xls.parse(tmp), open(os.path.join(cache, 'rule', d + '.json'), 'w', encoding='utf-8'), ensure_ascii=False)
                    os.remove(tmp)
                else:
                    xml, txt = body_text(vs[d], oc)
                    open(os.path.join(cache, sub, d + '.txt'), 'w', encoding='utf-8').write(txt)
                print('  %s %s 완료' % (sub, d), flush=True)
            except Exception as e:
                meta['missing'].append([name, d, str(e)[:150]]); print('  ! %s %s 실패: %s' % (sub, d, str(e)[:150]), flush=True)
            time.sleep(0.2)
    json.dump(meta, open(os.path.join(cache, 'fetch_meta.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    return meta

if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('cache'); ap.add_argument('--since', default='20220101')
    a = ap.parse_args(); m = run(a.cache, a.since)
    if m['missing']: print('\n받지 못한 항목 %d개' % len(m['missing']))
