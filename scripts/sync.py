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
ORG_PREFIX = os.environ.get('ORG_PREFIX') or '충청북도 청주시'
QUERIES = [q.strip() for q in (os.environ.get('QUERIES') or '청주').split(',') if q.strip()] or ['청주']
# 법제처 지자체 기관코드를 알면 ORG(시·도), SBORG(시·군·구)로 기관 자체를 걸러 검색할 수 있어요(비워 두면 이름 검색 + 기관명 확인).
ORG = os.environ.get('ORG', '').strip()
SBORG = os.environ.get('SBORG', '').strip()
KINDS = ('조례', '규칙')
PAUSE = float(os.environ.get('PAUSE') or '0.3')
BUDGET_MIN = float(os.environ.get('BUDGET_MIN') or '45')   # 이 시간(분)이 지나면 지금까지 받은 것을 저장하고 멈춰요(다음 실행이 이어받아요)
T0 = time.time()
FIELDS = ('자치법규일련번호', '자치법규ID', '자치법규명', '공포일자', '공포번호', '제개정구분명',
          '지자체기관명', '자치법규종류', '시행일자', '자치법규상세링크')


class ApiError(Exception):
    pass


class EmptyBody(ApiError):
    pass


def now():
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat(timespec='seconds')


def fetch(path, params, oc, tries=4, timeout=30):
    q = dict(params)
    q['OC'] = oc
    url = API + path + '?' + urllib.parse.urlencode(q)
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
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
            print('목록 %s p%d: %d/%s건 (%.0f초)' % (qn, page, got, total, time.time() - T0), flush=True)
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


def base_info(data):
    # 자치법규기본정보 안의 짧은 항목(담당부서명·전화번호·분야 등)을 이름 그대로 전부 담아요.
    root = ET.fromstring(data)
    base = root.find('자치법규기본정보')
    out = {}
    if base is not None:
        for ch in base:
            v = (ch.text or '').strip()
            if v and len(v) <= 200 and len(ch) == 0:
                out[ch.tag] = v
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
        raise EmptyBody('본문이 비어 있거나 형식이 달라요: %s [최상위 태그 %s, 조문 %s자, 부칙 %s자, 별표 %s자]' % (
            name, [c.tag for c in root], len(all_text(art)) if art is not None else 0,
            len(all_text(bu)) if bu is not None else 0, len(all_text(bp)) if bp is not None else 0))
    fm = [('id', meta['자치법규ID']), ('name', name), ('kind', meta['자치법규종류']), ('org', meta['지자체기관명']),
          ('mst', meta['자치법규일련번호']), ('promulgated', g('공포일자') or meta['공포일자']),
          ('effective', g('시행일자') or meta['시행일자']), ('revision', meta['제개정구분명']),
          ('source', source_url(meta)), ('fetched', now())]
    used = {'자치법규ID', '자치법규명', '자치법규종류', '지자체기관명', '자치법규일련번호', '공포일자', '시행일자', '제개정구분명'}
    extra = [(k, v) for k, v in base_info(data).items() if k not in used]
    fm += extra
    head = '---\n' + '\n'.join('%s: %s' % (k, json.dumps(v, ensure_ascii=False)) for k, v in fm) + '\n---\n'
    return name, head + '\n# ' + name + '\n\n' + text + '\n'


def stub_markdown(meta, info, reason):
    # 법제처가 본문을 내려주지 않는 자치법규는 목록 정보만 남기고 원문 링크를 안내해요.
    fm = [('id', meta['자치법규ID']), ('name', meta['자치법규명']), ('kind', meta['자치법규종류']), ('org', meta['지자체기관명']),
          ('mst', meta['자치법규일련번호']), ('promulgated', meta['공포일자']), ('effective', meta['시행일자']),
          ('revision', meta['제개정구분명']), ('source', source_url(meta)), ('fetched', now()), ('body_unavailable', True)]
    fm += [(k, v) for k, v in info.items() if k not in {'자치법규ID', '자치법규명', '자치법규종류', '지자체기관명', '자치법규일련번호', '공포일자', '시행일자', '제개정구분명'}]
    head = '---\n' + '\n'.join('%s: %s' % (k, json.dumps(v, ensure_ascii=False)) for k, v in fm) + '\n---\n'
    return head + '\n# ' + meta['자치법규명'] + '\n\n본문을 법제처 API가 제공하지 않아서 목록 정보만 보관해요. 원문은 위 `source` 주소에서 확인하세요.\n\n(' + reason + ')\n'


def source_url(meta):
    # API 링크에는 인증키(OC)가 들어 있어서 쓰지 않고, 누구나 열 수 있는 공개 화면 주소를 만들어요.
    return 'https://www.law.go.kr/ordinInfoP.do?ordinSeq=' + meta['자치법규일련번호']


def scrub(data, oc):
    # 저장하는 모든 원본·본문에서 인증키를 지워요.
    if isinstance(data, bytes):
        data = data.decode('utf-8', 'ignore')
    data = re.sub(r'(?i)([?&;]|&amp;)OC=[^&<"\s]*', r'\1OC=***', data)
    if oc:
        data = data.replace(oc, '***')
    return data


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
    open(os.path.join(ROOT, 'probe', 'list.xml'), 'w', encoding='utf-8').write(scrub(data, oc))
    total, rows = parse_list(data)
    print('전체 건수(검색어 %s): %s, 이번 페이지 %d건' % (QUERIES[0], total, len(rows)))
    for r in rows[:5]:
        print(' ', r['자치법규종류'], r['지자체기관명'], r['자치법규명'], r['시행일자'], r['자치법규일련번호'])
    pick = next((r for r in rows if r['지자체기관명'].startswith(ORG_PREFIX) and r['자치법규종류'] in KINDS), None)
    if not pick:
        print('청주시 조례·규칙을 목록에서 못 찾았어요. 기관명 예:', sorted({r['지자체기관명'] for r in rows})[:5])
        return 1
    body = fetch('lawService.do', {'target': 'ordin', 'type': 'XML', 'MST': pick['자치법규일련번호']}, oc)
    open(os.path.join(ROOT, 'probe', 'body.xml'), 'w', encoding='utf-8').write(scrub(body, oc))
    name, md = to_markdown(body, pick)
    print('본문 변환 성공:', name, '(%d자)' % len(md))
    print(md[:600])
    return 0


LAW_LIST_FIELDS = ('법령일련번호', '현행연혁코드', '법령명한글', '법령약칭명', '법령ID', '공포일자', '공포번호',
                   '제개정구분명', '소관부처코드', '소관부처명', '법령구분명', '시행일자')


def parse_law_list(data):
    root = ET.fromstring(data)
    return [{k: (e.findtext(k) or '').strip() for k in LAW_LIST_FIELDS} for e in root.iter('law')]


def norm_name(x):
    return re.sub(r'[\s]+', '', (x or '').replace('ㆍ', '·').replace('‧', '·'))


def law_source_url(meta):
    return 'https://www.law.go.kr/lsInfoP.do?lsiSeq=' + meta['법령일련번호']


def law_markdown(data, meta):
    root = ET.fromstring(data)
    fill_meta(meta, root)
    base = root.find('기본정보')
    info = {}
    if base is not None:
        for ch in base:
            v = (ch.text or '').strip()
            if v and len(v) <= 200 and len(ch) == 0:
                info[ch.tag] = v
            elif len(ch) and (ch.findtext('부서명') or ch.findtext('소관부처명') or ch.text):
                pass
    body = []
    art = root.find('조문')
    if art is not None:
        jos = list(art.iter('조문단위'))
        body += render_articles(jos) if jos else [all_text(art)]
    bu = root.find('부칙')
    if bu is not None and all_text(bu):
        body += ['', '## 부칙', '', all_text(bu)]
    bp = root.find('별표')
    if bp is not None and all_text(bp):
        body += ['', '## 별표·서식', '', all_text(bp)]
    text = '\n'.join(body).strip()
    if len(re.sub(r'\s', '', text)) < 30:
        raise ApiError('법령 본문이 비어 있거나 형식이 달라요: %s [최상위 태그 %s]' % (meta['법령명한글'], [c.tag for c in root]))
    fm = [('id', meta['법령ID']), ('name', meta['법령명한글']), ('kind', meta['법령구분명']), ('ministry', meta['소관부처명']),
          ('mst', meta['법령일련번호']), ('promulgated', meta['공포일자']), ('promulgation_no', meta['공포번호']),
          ('effective', meta['시행일자']), ('revision', meta['제개정구분명']), ('source', law_source_url(meta)), ('fetched', now())]
    used = {'법령ID', '법령명_한글', '공포일자', '공포번호', '시행일자', '제개정구분', '법종류'}
    fm += [(k, v) for k, v in info.items() if k not in used]
    head = '---\n' + '\n'.join('%s: %s' % (k, json.dumps(v, ensure_ascii=False)) for k, v in fm) + '\n---\n'
    return head + '\n# ' + meta['법령명한글'] + '\n\n' + text + '\n', info


def law_rel_path(meta):
    return 'laws/%s/%s_%s.md' % (safe(meta['법령구분명'] or '기타'), meta['법령ID'], safe(meta['법령명한글']))


def _rows_by_name(name, oc, nw, target='law', display='100'):
    t = time.time()
    rows = parse_law_list(fetch('lawSearch.do', {'target': target, 'type': 'XML', 'query': name,
                                                  'search': '1', 'display': display, 'nw': nw}, oc, tries=2, timeout=20))
    print('[개명]   검색 %s nw=%s: %d건 (%.1f초)' % (target, nw, len(rows), time.time() - t), flush=True)
    return rows


def fill_meta(meta, root):
    """시행일 법령(eflaw) 목록에는 없는 값(법 종류·소관부처 등)을 본문 응답에서 채워요."""
    b = root.find('기본정보')
    if b is None:
        return
    for k, tags in (('법령구분명', ('법종류',)), ('소관부처명', ('소관부처',)), ('제개정구분명', ('제개정구분',)),
                    ('공포번호', ('공포번호',)), ('공포일자', ('공포일자',)), ('시행일자', ('시행일자',))):
        if not meta.get(k):
            for t in tags:
                v = (b.findtext(t) or '').strip()
                if v:
                    meta[k] = v
                    break


def resolve_renamed(name, oc, idx):
    """현행 목록(law)에서 못 찾은 이름을 시행일 법령(eflaw) 목록에서 다시 찾아요.
    - eflaw nw=1은 옛 이름의 연혁 판을 이름 그대로 돌려줘요(법령ID 공통). 마지막 연혁 판을 옛 이름으로 저장해요
      (조례가 인용한 조문 번호 그대로).
    - eflaw nw=3은 같은 법령ID의 현행 판을 돌려줘요. 이름이 다르면 이름이 바뀐 거예요. 현행 판도 같이 저장해요.
    결과: result = renamed | current(이름 그대로 현행인데 처음 검색에서 놓친 경우) | repealed | none | error."""
    print('[개명] 연혁 확인 중:', name, flush=True)
    failed = False
    hist, cur_rows = [], []
    try:
        hist = [r for r in _rows_by_name(name, oc, '1', 'eflaw') if norm_name(r['법령명한글']) == norm_name(name)]
    except (ApiError, ET.ParseError) as e:
        print('[개명]   연혁 검색 실패: %s' % e, flush=True)
        failed = True
    try:
        cur_rows = _rows_by_name(name, oc, '3', 'eflaw')
    except (ApiError, ET.ParseError) as e:
        print('[개명]   현행 검색 실패: %s' % e, flush=True)
        failed = True
    same_cur = [r for r in cur_rows if norm_name(r['법령명한글']) == norm_name(name)]
    if not hist and not same_cur:
        return {'result': 'error' if failed else 'none'}
    lid = (sorted(hist, key=lambda r: (r['시행일자'], r['공포일자'], r['법령일련번호']))[-1] if hist else same_cur[0])['법령ID']
    cur_meta = None
    cands = [r for r in cur_rows if r['법령ID'] == lid and r['현행연혁코드'] in ('현행', '')]
    if cands:
        cur_meta = sorted(cands, key=lambda r: r['시행일자'])[-1]
    out = {'id': lid}
    if cur_meta and norm_name(cur_meta['법령명한글']) == norm_name(name):
        out['result'] = 'current'
    elif cur_meta:
        out['result'] = 'renamed'
        out['new_name'] = cur_meta['법령명한글']
    else:
        out['result'] = 'repealed'
    print('[개명]   판정: %s%s' % (out['result'], (' → ' + out['new_name']) if out.get('new_name') else ''), flush=True)

    def save_current(meta, note):
        data = fetch('lawService.do', {'target': 'law', 'type': 'XML', 'MST': meta['법령일련번호']}, oc, tries=2, timeout=30)
        md, info = law_markdown(data, meta)
        md = scrub(md, oc)
        pth = law_rel_path(meta)
        p = os.path.join(ROOT, pth)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, 'w', encoding='utf-8').write(md)
        ent = {'id': meta['법령ID'], 'name': meta['법령명한글'], 'kind': meta['법령구분명'], 'ministry': meta['소관부처명'],
               'mst': meta['법령일련번호'], 'promulgated': meta['공포일자'], 'promulgation_no': meta['공포번호'],
               'effective': meta['시행일자'], 'revision': meta['제개정구분명'], 'path': pth, 'sha256': sha(md),
               'source': law_source_url(meta), 'info': info, 'checked': now()}
        ent.update(note)
        idx[meta['법령ID']] = ent

    try:
        if out['result'] in ('current', 'renamed') and cur_meta:
            if out['result'] == 'renamed' and cur_meta['법령ID'] in idx:
                pass  # 이미 현행 판을 받아 둠
            else:
                save_current(cur_meta, {'replaces': name} if out['result'] == 'renamed' else {})
        if out['result'] in ('renamed', 'repealed') and hist:
            last = sorted(hist, key=lambda r: (r['시행일자'], r['공포일자'], r['법령일련번호']))[-1]
            data = fetch('lawService.do', {'target': 'law', 'type': 'XML', 'MST': last['법령일련번호']}, oc, tries=2, timeout=30)
            md, info = law_markdown(data, last)
            extra = 'historic: true\n' + ('renamed_to: %s\n' % json.dumps(out['new_name'], ensure_ascii=False) if out.get('new_name') else '')
            md = scrub(md.replace('\n---\n', '\n' + extra + '---\n', 1), oc)
            pth = 'laws/연혁/%s_%s_%s.md' % (lid, last['법령일련번호'], safe(name))
            p = os.path.join(ROOT, pth)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, 'w', encoding='utf-8').write(md)
            ent = {'id': 'H' + last['법령일련번호'], 'name': name, 'kind': last['법령구분명'], 'ministry': last['소관부처명'],
                   'mst': last['법령일련번호'], 'promulgated': last['공포일자'], 'promulgation_no': last['공포번호'],
                   'effective': last['시행일자'], 'revision': last['제개정구분명'], 'path': pth, 'sha256': sha(md),
                   'source': law_source_url(last), 'info': info, 'checked': now(), 'historic': True}
            if out.get('new_name'):
                ent['renamed_to'] = out['new_name']
            idx[ent['id']] = ent
            out['path'] = pth
    except (ApiError, ET.ParseError) as e:
        print('[개명]   본문 저장 실패:', name, e, flush=True)
        return {'result': 'error'}
    return out


def sync_laws(oc, mode):
    """laws.json에 적은 이름(정확히 같은 법령명)의 현행 법령을 받아 laws/ 에 저장해요."""
    cfg = jload('laws.json', {})
    names = []
    for g in cfg.get('groups', []):
        for n in g.get('names', []):
            if n not in names:
                names.append(n)
    if not names:
        print('[법령] laws.json이 없거나 비었어요. 건너뜀')
        return [], []
    idx = {r['id']: r for r in jload('indexes/laws.json', [])}
    new, errors, missing = [], [], []
    # 불필요한 반복 호출을 줄여요: 이미 받은 법령은 7일마다, 못 찾은 이름은 30일마다만 다시 확인해요.
    today = datetime.date.today()
    def days_ago(ts):
        try:
            return (today - datetime.date.fromisoformat(str(ts)[:10])).days
        except ValueError:
            return 9999
    by_name = {r.get('name'): r for r in idx.values()}
    miss_cache = jload('indexes/laws_missing.json', {})
    rn_cache = {k: v for k, v in jload('indexes/laws_renamed.json', {}).items() if v.get('v') == 2}   # 옛 방식(v1)으로 확인한 결과는 버려요   # 옛 이름 → 연혁 확인 결과(renamed·repealed·none)
    renamed = []
    rn_fail = 0
    for n, name in enumerate(names, 1):
        if mode != 'full':
            r0 = by_name.get(name)
            if r0 and os.path.exists(os.path.join(ROOT, r0['path'])) and days_ago(r0.get('checked')) < 7:
                continue
            rc = rn_cache.get(name)
            if rc and days_ago(rc.get('tried')) < 30:
                if rc.get('result') == 'none':
                    missing.append(name)
                continue
            if name in miss_cache and days_ago(miss_cache[name]) < 30 and rc is None:
                # 현행에는 없다고 이미 확인했으니 연혁 확인만 해요(처음 한 번)
                try:
                    res = resolve_renamed(name, oc, idx)
                except (ApiError, ET.ParseError) as e:
                    errors.append('%s(연혁): %s' % (name, e))
                    continue
                if res['result'] == 'error':
                    missing.append(name)
                    continue
                res['tried'] = today.isoformat()
                res['v'] = 2
                rn_cache[name] = res
                if res['result'] == 'none':
                    missing.append(name)
                else:
                    renamed.append(name)
                    print('[개명] %s: %s%s' % (name, res['result'], (' → ' + res.get('new_name', '')) if res.get('new_name') else ''), flush=True)
                continue
        if (time.time() - T0) / 60 > BUDGET_MIN + 10:
            print('[법령] 시간 한도라 여기까지 저장해요. 다음 실행이 이어받아요.', flush=True)
            break
        try:
            rows = parse_law_list(fetch('lawSearch.do', {'target': 'law', 'type': 'XML', 'query': name,
                                                          'search': '1', 'display': '100', 'nw': '3'}, oc))
            hit = [r for r in rows if norm_name(r['법령명한글']) == norm_name(name) and r['현행연혁코드'] in ('현행', '')]
            if not hit:
                miss_cache[name] = today.isoformat()
                print('[법령] 이름이 같은 현행 법령을 못 찾았어요. 연혁을 확인해요:', name, flush=True)
                res = resolve_renamed(name, oc, idx)
                if res['result'] == 'error':
                    missing.append(name)
                    continue
                res['tried'] = today.isoformat()
                res['v'] = 2
                rn_cache[name] = res
                if res['result'] == 'none':
                    missing.append(name)
                else:
                    renamed.append(name)
                    print('[개명] %s: %s%s' % (name, res['result'], (' → ' + res.get('new_name', '')) if res.get('new_name') else ''), flush=True)
                continue
            m = sorted(hit, key=lambda r: r['시행일자'])[-1]
            old = idx.get(m['법령ID'])
            if (mode != 'full' and old and old.get('mst') == m['법령일련번호']
                    and os.path.exists(os.path.join(ROOT, old['path']))):
                idx[m['법령ID']]['checked'] = now()
                continue
            md, info = law_markdown(fetch('lawService.do', {'target': 'law', 'type': 'XML', 'MST': m['법령일련번호']}, oc), m)
            md = scrub(md, oc)
            path = law_rel_path(m)
            if old and old['path'] != path and os.path.exists(os.path.join(ROOT, old['path'])):
                os.remove(os.path.join(ROOT, old['path']))
            p = os.path.join(ROOT, path)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, 'w', encoding='utf-8').write(md)
            idx[m['법령ID']] = {'id': m['법령ID'], 'name': name, 'kind': m['법령구분명'], 'ministry': m['소관부처명'],
                                'mst': m['법령일련번호'], 'promulgated': m['공포일자'], 'promulgation_no': m['공포번호'],
                                'effective': m['시행일자'], 'revision': m['제개정구분명'], 'path': path, 'sha256': sha(md),
                                'source': law_source_url(m), 'info': info, 'checked': now()}
            new.append(name)
            print('[법령] %d/%d %s (%s)' % (n, len(names), name, m['시행일자']), flush=True)
        except (ApiError, ET.ParseError) as e:
            errors.append('%s: %s' % (name, e))
            print('[법령] 오류', errors[-1], flush=True)
    jsave('indexes/laws.json', sorted(idx.values(), key=lambda r: r['id']))
    jsave('indexes/laws_missing.json', {k: v for k, v in miss_cache.items() if k in names})
    jsave('indexes/laws_renamed.json', {k: v for k, v in rn_cache.items() if k in names})
    print('[법령] 새로·개정 %d · 이름 바뀜/폐지(연혁본 저장) %d · 끝내 못 찾음 %d · 오류 %d' % (len(new), len(renamed), len(missing), len(errors)))
    return missing, errors


def run(mode, limit=None):
    oc = os.environ.get('LAW_OC', '').strip()
    if not oc:
        print('LAW_OC(법제처 인증키)가 없어요. 저장소 Settings → Secrets에 LAW_OC를 넣으세요.')
        return 2
    if mode == 'probe':
        return probe(oc)
    po = os.path.join(ROOT, 'probe_ordins.txt')
    if os.path.exists(po):
        # 확인용(실행은 계속해요): 옛 이름의 조례·규칙이 연혁 검색에 나오는지 로그에 찍어요.
        for nm in [l.strip() for l in open(po, encoding='utf-8') if l.strip()]:
            for nw in ('3', '1'):
                try:
                    raw = fetch('lawSearch.do', {'target': 'ordin', 'type': 'XML', 'query': nm, 'search': '1',
                                                 'display': '30', 'nw': nw}, oc, tries=2, timeout=20)
                    tot, rows = parse_list(raw)
                except (ApiError, ET.ParseError) as e:
                    print('[조례확인] %s nw=%s 실패: %s' % (nm, nw, e), flush=True)
                    continue
                print('[조례확인] "%s" nw=%s → 전체 %s건' % (nm, nw, tot), flush=True)
                for r in rows[:10]:
                    print('   |%s|%s|%s|ID=%s|MST=%s|시행=%s|공포=%s|%s' % (r['자치법규명'], r['지자체기관명'], r['자치법규종류'],
                          r['자치법규ID'], r['자치법규일련번호'], r['시행일자'], r['공포일자'], r['제개정구분명']), flush=True)
    pf = os.path.join(ROOT, 'probe_laws.txt')
    if os.path.exists(pf):
        # 확인용: probe_laws.txt에 법령 이름을 한 줄에 하나씩 적고 실행하면 검색 결과 표만 로그에 찍고 끝내요.
        for nm in [l.strip() for l in open(pf, encoding='utf-8') if l.strip()]:
            for nw in ('3', '1'):
                try:
                    rows = _rows_by_name(nm, oc, nw)
                except (ApiError, ET.ParseError) as e:
                    print('[확인] %s nw=%s 실패: %s' % (nm, nw, e), flush=True)
                    continue
                print('[확인] "%s" nw=%s → %d건' % (nm, nw, len(rows)), flush=True)
                for r in rows[:8]:
                    print('   |%s|%s|ID=%s|MST=%s|시행=%s|공포=%s|%s|%s' % (r['법령명한글'], r['현행연혁코드'], r['법령ID'], r['법령일련번호'],
                          r['시행일자'], r['공포일자'], r['제개정구분명'], r['법령구분명']), flush=True)
        for nm in [l.strip() for l in open(pf, encoding='utf-8') if l.strip()][:2]:
            for tg, nw in (('eflaw', '1'), ('eflaw', '3'), ('lsHstInf', '')):
                prm = {'target': tg, 'type': 'XML', 'query': nm, 'search': '1', 'display': '30'}
                if nw:
                    prm['nw'] = nw
                try:
                    raw = fetch('lawSearch.do', prm, oc, tries=2, timeout=20)
                except ApiError as e:
                    print('[확인2] %s %s nw=%s 실패: %s' % (nm, tg, nw, e), flush=True)
                    continue
                txt = raw.decode('utf-8', 'ignore')
                try:
                    rows = parse_law_list(raw)
                except ET.ParseError:
                    rows = []
                print('[확인2] "%s" target=%s nw=%s → 파싱 %d건' % (nm, tg, nw, len(rows)), flush=True)
                for r in rows[:12]:
                    print('   |%s|%s|ID=%s|MST=%s|시행=%s|공포=%s|%s' % (r['법령명한글'], r['현행연혁코드'], r['법령ID'], r['법령일련번호'],
                          r['시행일자'], r['공포일자'], r['제개정구분명']), flush=True)
                if not rows:
                    print('   원본:', re.sub(r'\s+', ' ', re.sub(r'(?i)OC=[^&<"\s]*', 'OC=***', txt))[:900], flush=True)
        print('[확인] 끝. probe_laws.txt를 지우고 다시 실행하세요.')
        return 0
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
    partial = False
    todo = sum(1 for it in items if mode == 'full' or idx.get(it['자치법규ID']) is None
               or idx[it['자치법규ID']].get('mst') != it['자치법규일련번호'] or idx[it['자치법규ID']].get('status') != 'active'
               or not os.path.exists(os.path.join(ROOT, idx[it['자치법규ID']]['path'])))
    print('본문을 새로 받을 것: %d건 (전체 %d건)' % (todo, len(items)), flush=True)
    done = 0
    for it in sorted(items, key=lambda r: r['자치법규ID']):
        i = it['자치법규ID']
        old = idx.get(i)
        path = rel_path(it)
        need = (mode == 'full' or old is None or old.get('mst') != it['자치법규일련번호']
                or old.get('status') != 'active' or not os.path.exists(os.path.join(ROOT, old['path'])))
        if need:
            if (time.time() - T0) / 60 > BUDGET_MIN:
                partial = True
                print('시간 한도(%.0f분)에 도달해서 여기까지 저장하고 멈춰요. 다음 실행이 이어받아요.' % BUDGET_MIN, flush=True)
                break
            done += 1
            if done % 25 == 0:
                print('본문 %d/%d건 (%.0f초)' % (done, todo, time.time() - T0), flush=True)
            try:
                data = fetch('lawService.do', {'target': 'ordin', 'type': 'XML', 'MST': it['자치법규일련번호']}, oc)
                name, md = to_markdown(data, it)
                info = base_info(data)
            except EmptyBody as e:
                name = it['자치법규명']
                md = stub_markdown(it, base_info(data), '본문 없음')
                info = base_info(data)
                print('경고 본문 없음, 목록 정보만 저장:', i, name, flush=True)
            except (ApiError, ET.ParseError) as e:
                errors.append('%s %s: %s' % (i, it['자치법규명'], e))
                print('오류', errors[-1])
                continue
            if old and old['path'] != path and os.path.exists(os.path.join(ROOT, old['path'])):
                os.remove(os.path.join(ROOT, old['path']))
            md = scrub(md, oc)
            p = os.path.join(ROOT, path)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, 'w', encoding='utf-8').write(md)
            (changed if old else new).append(i)
            digest = sha(md)
        else:
            digest = old['sha256']
            info = old.get('info', {})
        idx[i] = {'id': i, 'name': it['자치법규명'], 'kind': it['자치법규종류'], 'org': it['지자체기관명'],
                  'mst': it['자치법규일련번호'], 'promulgated': it['공포일자'], 'effective': it['시행일자'],
                  'revision': it['제개정구분명'], 'path': path, 'sha256': digest, 'status': 'active',
                  'source': source_url(it), 'info': info, 'checked': now()}
    lmiss, lerr = sync_laws(oc, mode)
    errors += lerr
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
                                       'changed': changed, 'absent': gone, 'errors': errors, 'laws_missing': lmiss})
    print('새로 %d · 개정 %d · 목록에서 사라짐 %d · 오류 %d%s' % (len(new), len(changed), len(gone), len(errors), ' · 부분 완료(이어받기 필요)' if partial else ''))
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
