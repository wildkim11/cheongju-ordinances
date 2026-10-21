#!/usr/bin/env python3
"""청주시 자치법규(조례·규칙) 수집기 — 법제처 국가법령정보 공동활용 Open API 사용.

사용:
  LAW_OC=<인증키> python3 scripts/sync.py --mode incremental   # 새로 생기거나 개정된 것만
  LAW_OC=<인증키> python3 scripts/sync.py --mode full          # 전부 다시 받기
  LAW_OC=<인증키> python3 scripts/sync.py --mode probe         # 응답 모양만 확인(probe/ 폴더에 원본 저장)
표준 라이브러리만 씁니다. 목록이 비었거나 크게 줄면 아무것도 바꾸지 않고 실패합니다.
"""
import argparse, datetime, hashlib, json, os, re, sys, time
import urllib.parse, urllib.request, urllib.error
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = os.environ.get('LAW_API_BASE', 'https://www.law.go.kr/DRF/').rstrip('/') + '/'
UA = 'cheongju-ordinances/1.0'
ORG_PREFIX = os.environ.get('ORG_PREFIX', '충청북도 청주시')
QUERIES = [q.strip() for q in os.environ.get('QUERIES', '청주').split(',') if q.strip()]
# 법제처 지자체 기관코드를 알면 ORG(시·도), SBORG(시·군·구)로 기관 자체를 걸러 검색할 수 있어요(비워 두면 이름 검색 + 기관명 확인).
ORG = os.environ.get('ORG', '').strip()
SBORG = os.environ.get('SBORG', '').strip()
KINDS = ('조례', '규칙')
PAUSE = float(os.environ.get('PAUSE', '0.3'))
FIELDS = ('자치법규일련번호', '자치법규ID', '자치법규명', '공포일자', '공포번호', '제개정구분명',
          '지자체기관명', '자치법규종류', '시행일자', '자치법규상세링크')


class ApiError(Exception):
    pass


def now():
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat(timespec='seconds')


def fetch(path, params, oc):
    q = dict(params)
    q['OC'] = oc
    url = API + path + '?' + urllib.parse.urlencode(q)
    last = None
    for i in range(4):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
            head = data[:600].decode('utf-8', 'ignore')
            if '사용자 정보 검증에 실패' in head or '사용자정보 검증' in head:
                raise ApiError('법제처가 인증키(OC) 또는 접속 주소를 확인하지 못했어요. 인증키가 맞는지, '
                               '신청한 서버 주소(IP·도메인) 조건이 있는지 확인하세요: ' + re.sub(r'<[^>]+>', ' ', head)[:200])
            time.sleep(PAUSE)
            return data
        except ApiError:
            raise
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last = e
            time.sleep(2 * (i + 1))
    raise ApiError('요청 실패: %s (%s)' % (path, last))


def parse_list(data):
    root = ET.fromstring(data)
    total = int((root.findtext('totalCnt') or '0').strip() or 0)
    rows = []
    for e in root.iter('law'):
        rows.append({k: (e.findtext(k) or '').strip() for k in FIELDS})
    return total, rows


def collect(oc, limit=None):
    seen = {}
    orgs = {}
    for qn in QUERIES:
        page, got = 1, 0
        while True:
            prm = {'target': 'ordin', 'type': 'XML', 'query': qn, 'search': '1',
                   'display': '100', 'page': str(page), 'nw': '3'}
            if ORG:
                prm['org'] = ORG
            if SBORG:
                prm['sborg'] = SBORG
            data = fetch('lawSearch.do', prm, oc)
            total, rows = parse_list(data)
            if not rows:
                break
            got += len(rows)
            for r in rows:
                orgs[r['지자체기관명']] = orgs.get(r['지자체기관명'], 0) + 1
                if not r['지자체기관명'].startswith(ORG_PREFIX) or r['자치법규종류'] not in KINDS:
                    continue
                if r['자치법규ID'] and r['자치법규일련번호']:
                    seen[r['자치법규ID']] = r
            if got >= total or (limit and len(seen) >= limit):
                break
            page += 1
    return list(seen.values()), orgs


# ───────────── 본문 → 마크다운 ─────────────
def clean(s):
    s = (s or '').replace('\r', '')
    return '\n'.join(l.rstrip() for l in s.split('\n')).strip()


def first_text(e, *tags):
    for t in tags:
        v = e.findtext(t)
        if v and v.strip():
            return clean(v)
    return ''


def all_text(e):
    return '\n'.join(clean(t) for t in e.itertext() if t and t.strip())


PAD = {'항': '', '호': '　', '목': '　　', '세목': '　　　'}


def units(e, out):
    for ch in e:
        if ch.tag in PAD:
            t = first_text(ch, ch.tag + '내용', '내용')
            if t:
                out.append(PAD[ch.tag] + t.replace('\n', '\n' + PAD[ch.tag]))
            units(ch, out)


def render_articles(jos):
    out = []
    for jo in jos:
        head = first_text(jo, '조문내용', '조내용')
        if re.match(r'^제\s*\d+\s*[편장절관]', head):
            out += ['', '## ' + head.replace('\n', ' '), '']
            continue
        if head:
            out.append(head)
        units(jo, out)
        out.append('')
    return out


def to_markdown(data, meta):
    root = ET.fromstring(data)
    base = root.find('자치법규기본정보')
    if base is None:
        raise ApiError('본문 응답에 자치법규기본정보가 없어요: ' + meta.get('자치법규명', ''))
    g = lambda k: (base.findtext(k) or meta.get(k, '') or '').strip()
    name = g('자치법규명') or meta['자치법규명']
    body = []
    art = root.find('조문')
    if art is not None:
        jos = list(art.iter('조'))
        body += render_articles(jos) if jos else [all_text(art)]
    bu = root.find('부칙')
    if bu is not None and all_text(bu):
        body += ['', '## 부칙', '', all_text(bu)]
    bp = root.find('별표')
    if bp is not None and all_text(bp):
        body += ['', '## 별표·서식', '', all_text(bp)]
    text = '\n'.join(body).strip()
    if len(re.sub(r'\s', '', text)) < 30:
        raise ApiError('본문이 비어 있거나 형식이 달라요: ' + name)
    fm = [('id', meta['자치법규ID']), ('name', name), ('kind', meta['자치법규종류']), ('org', meta['지자체기관명']),
          ('mst', meta['자치법규일련번호']), ('promulgated', g('공포일자') or meta['공포일자']),
          ('effective', g('시행일자') or meta['시행일자']), ('revision', meta['제개정구분명']),
          ('source', source_url(meta)), ('fetched', now())]
    head = '---\n' + '\n'.join('%s: %s' % (k, json.dumps(v, ensure_ascii=False)) for k, v in fm) + '\n---\n'
    return name, head + '\n# ' + name + '\n\n' + text + '\n'


def source_url(meta):
    l = meta.get('자치법규상세링크', '')
    if l.startswith('/'):
        return 'https://www.law.go.kr' + l
    return l or 'https://www.law.go.kr/ordinInfoP.do?ordinSeq=' + meta['자치법규일련번호']


def safe(name):
    return re.sub(r'[\\/:*?"<>|\s]+', '_', name).strip('_')[:80]


def rel_path(meta):
    return 'ordinances/%s/%s_%s.md' % (meta['자치법규종류'], meta['자치법규ID'], safe(meta['자치법규명']))


# ───────────── 저장 ─────────────
def jload(path, default):
    p = os.path.join(ROOT, path)
    return json.load(open(p, encoding='utf-8')) if os.path.exists(p) else default


def jsave(path, obj):
    p = os.path.join(ROOT, path)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
        f.write('\n')


def sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def probe(oc):
    os.makedirs(os.path.join(ROOT, 'probe'), exist_ok=True)
    data = fetch('lawSearch.do', {'target': 'ordin', 'type': 'XML', 'query': QUERIES[0], 'search': '1',
                                   'display': '20', 'page': '1', 'nw': '3'}, oc)
    open(os.path.join(ROOT, 'probe', 'list.xml'), 'wb').write(data)
    total, rows = parse_list(data)
    print('전체 건수(검색어 %s): %s, 이번 페이지 %d건' % (QUERIES[0], total, len(rows)))
    for r in rows[:5]:
        print(' ', r['자치법규종류'], r['지자체기관명'], r['자치법규명'], r['시행일자'], r['자치법규일련번호'])
    pick = next((r for r in rows if r['지자체기관명'].startswith(ORG_PREFIX) and r['자치법규종류'] in KINDS), None)
    if not pick:
        print('청주시 조례·규칙을 목록에서 못 찾았어요. 기관명 예:', sorted({r['지자체기관명'] for r in rows})[:5])
        return 1
    body = fetch('lawService.do', {'target': 'ordin', 'type': 'XML', 'MST': pick['자치법규일련번호']}, oc)
    open(os.path.join(ROOT, 'probe', 'body.xml'), 'wb').write(body)
    name, md = to_markdown(body, pick)
    print('본문 변환 성공:', name, '(%d자)' % len(md))
    print(md[:600])
    return 0


def run(mode, limit=None):
    oc = os.environ.get('LAW_OC', '').strip()
    if not oc:
        print('LAW_OC(법제처 인증키)가 없어요. 저장소 Settings → Secrets에 LAW_OC를 넣으세요.')
        return 2
    if mode == 'probe':
        return probe(oc)
    idx = {r['id']: r for r in jload('indexes/ordinances.json', [])}
    active_before = [r for r in idx.values() if r.get('status') == 'active']
    items, orgs = collect(oc, limit)
    print('검색어 %s · 기관명 분포(상위): %s' % (QUERIES, sorted(orgs.items(), key=lambda x: -x[1])[:6]))
    print('목록에서 청주시 자치법규 %d건 (조례 %d · 규칙 %d)' % (
        len(items), sum(1 for i in items if i['자치법규종류'] == '조례'), sum(1 for i in items if i['자치법규종류'] == '규칙')))
    if not items:
        print('목록이 비었어요. 기관명 분포:', orgs)
        return 1
    if not limit and active_before and len(items) < 0.7 * len(active_before):
        print('목록이 이전(%d건)보다 크게 줄었어요(%d건). 안전을 위해 중단합니다.' % (len(active_before), len(items)))
        return 1
    new, changed, errors = [], [], []
    for it in sorted(items, key=lambda r: r['자치법규ID']):
        i = it['자치법규ID']
        old = idx.get(i)
        path = rel_path(it)
        need = (mode == 'full' or old is None or old.get('mst') != it['자치법규일련번호']
                or old.get('status') != 'active' or not os.path.exists(os.path.join(ROOT, old['path'])))
        if need:
            try:
                data = fetch('lawService.do', {'target': 'ordin', 'type': 'XML', 'MST': it['자치법규일련번호']}, oc)
                name, md = to_markdown(data, it)
            except (ApiError, ET.ParseError) as e:
                errors.append('%s %s: %s' % (i, it['자치법규명'], e))
                print('오류', errors[-1])
                continue
            if old and old['path'] != path and os.path.exists(os.path.join(ROOT, old['path'])):
                os.remove(os.path.join(ROOT, old['path']))
            p = os.path.join(ROOT, path)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, 'w', encoding='utf-8').write(md)
            (changed if old else new).append(i)
            digest = sha(md)
        else:
            digest = old['sha256']
        idx[i] = {'id': i, 'name': it['자치법규명'], 'kind': it['자치법규종류'], 'org': it['지자체기관명'],
                  'mst': it['자치법규일련번호'], 'promulgated': it['공포일자'], 'effective': it['시행일자'],
                  'revision': it['제개정구분명'], 'path': path, 'sha256': digest, 'status': 'active',
                  'source': source_url(it), 'checked': now()}
    seen = {it['자치법규ID'] for it in items}
    gone = []
    for i, r in idx.items():
        if i not in seen and r.get('status') == 'active':
            r['status'] = 'absent'
            r['absent_since'] = now()
            gone.append(i)
    jsave('indexes/ordinances.json', sorted(idx.values(), key=lambda r: r['id']))
    act = [r for r in idx.values() if r['status'] == 'active']
    jsave('manifest.json', {'checkedAt': now(), 'mode': mode, 'ordinances': sum(1 for r in act if r['kind'] == '조례'),
                            'rules': sum(1 for r in act if r['kind'] == '규칙'), 'absent': sum(1 for r in idx.values() if r['status'] != 'active'),
                            'org': ORG_PREFIX})
    jsave('reports/latest-sync.json', {'checkedAt': now(), 'mode': mode, 'listed': len(items), 'new': new,
                                       'changed': changed, 'absent': gone, 'errors': errors})
    print('새로 %d · 개정 %d · 목록에서 사라짐 %d · 오류 %d' % (len(new), len(changed), len(gone), len(errors)))
    return 1 if errors else 0


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--mode', choices=['auto', 'incremental', 'full', 'probe'], default='incremental')
    ap.add_argument('--limit', type=int, default=None, help='시험용: 이 건수까지만')
    a = ap.parse_args()
    try:
        sys.exit(run('incremental' if a.mode == 'auto' else a.mode, a.limit))
    except ApiError as e:
        print('오류:', e)
        sys.exit(1)
