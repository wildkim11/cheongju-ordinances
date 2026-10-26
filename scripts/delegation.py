#!/usr/bin/env python3
"""상위법이 지방자치단체 조례로 정하도록 맡긴 조문 목록(indexes/delegations.json) 만들기.

사용:
  LAW_OC=<인증키> python3 scripts/delegation.py --mode upcoming   # 시행 예정인 법령 목록(indexes/upcoming.json)
  python3 scripts/delegation.py --mode repo                       # 저장소에 이미 있는 법령 본문만 훑음(인증키 필요 없음)
  LAW_OC=<인증키> python3 scripts/delegation.py --mode api        # 법제처 현행 법령 전체를 받아 훑음(이어받기 지원)
  LAW_OC=<인증키> python3 scripts/delegation.py --mode api --limit 30   # 맛보기: 30건만

법령 본문은 저장하지 않고, 조례로 맡긴 문장만 모아서 indexes/delegations.json에 적어요.
표준 라이브러리 + scripts/sync.py만 써요. 이미 받은 법령(법령일련번호 같음)은 다시 받지 않아요.
"""
import argparse, glob, json, os, re, sys, time
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sync  # noqa: E402

ROOT = sync.ROOT
OUT = os.path.join(ROOT, 'indexes', 'delegations.json')
KINDS = ('법률', '대통령령', '총리령', '부령')
BUDGET_MIN = float(os.environ.get('BUDGET_MIN') or '45')

# 「지방자치단체/시·도/시장·군수 …의 조례로 정한다」 꼴. 앞 문맥에 지자체가 나와야 하고, 문장 끝이 위임 표현이어야 해요.
ORD = re.compile(r'조례(?:로|에\s*따라|에서|가\s*정하는|에\s*위임)\s*[^.。\n]{0,12}?(?:정|위임|규정|따라)')
CTX = re.compile(r'지방자치단체|특별시|광역시|특별자치시|특별자치도|시ㆍ도|시·도|시ㆍ군|시·군|시장|군수|구청장|도지사|교육감|시ㆍ도의회|지방의회')
JO = re.compile(r'^(제\s*\d+\s*조(?:의\s*\d+)?)\s*\(([^)]*)\)')


def split_articles(text):
    """본문 텍스트를 (조, 제목, 본문) 목록으로 나눠요."""
    cur = None
    out = []
    for line in text.split('\n'):
        m = JO.match(line.strip())
        if m:
            if cur:
                out.append(cur)
            cur = [re.sub(r'\s+', '', m.group(1)), m.group(2).strip(), [line.strip()]]
        elif cur is not None:
            if line.startswith('## '):          # 장·부칙 머리 → 조문 끝
                out.append(cur)
                cur = None
            elif line.strip():
                cur[2].append(line.strip())
    if cur:
        out.append(cur)
    return [(a, b, '\n'.join(c)) for a, b, c in out]


def extract(text):
    """조문 하나씩 훑어 조례 위임 문장을 모아요. [{jo,title,s:[문장…]}]"""
    res = []
    body = text.split('\n## 부칙')[0]
    for jo, title, tx in split_articles(body):
        if re.search(r'삭제\s*<', tx[:60]) and len(tx) < 80:
            continue
        hits = []
        for ln in tx.split('\n'):
            for m in ORD.finditer(ln):
                pre = ln[max(0, m.start() - 60):m.start()]
                if not CTX.search(pre):
                    continue
                st = max(ln.rfind('. ', 0, m.start()) + 2, 0)
                en = ln.find('.', m.end())
                s = ln[st:(en + 1 if en >= 0 else len(ln))].strip()
                if s and s not in hits:
                    hits.append(s[:300])
        if hits:
            res.append({'jo': jo, 'title': title, 's': hits[:4]})
    return res


def load():
    try:
        return json.load(open(OUT, encoding='utf-8'))
    except Exception:
        return {'laws': {}}


def save(d):
    d['asof'] = sync.now()[:10]
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    tmp = OUT + '.tmp'
    json.dump(d, open(tmp, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'), sort_keys=True)
    os.replace(tmp, OUT)


def from_repo():
    d = load()
    n = 0
    for p in sorted(glob.glob(os.path.join(ROOT, 'laws', '*', '*.md'))):
        t = open(p, encoding='utf-8').read()
        fm = dict(re.findall(r'^(\w+): "([^"]*)"', t.split('\n---\n')[0], re.M))
        if not fm.get('name') or fm.get('kind') not in KINDS:
            continue
        if '이 법은 폐지' in t[:2000]:
            continue
        it = extract(t.split('\n---\n', 1)[-1])
        key = fm['name']
        if it:
            d['laws'][key] = {'kind': fm['kind'], 'mst': fm.get('mst', ''), 'eff': fm.get('effective', ''), 'src': 'repo', 'items': it}
            n += 1
        else:
            d['laws'].pop(key, None)
    save(d)
    print('[위임] 저장소 법령에서 조례 위임이 있는 법령 %d건' % n)


def retry(fn, what, tries=5):
    """일시적인 네트워크 오류(이름 해석 실패 등)는 기다렸다가 다시 시도해요."""
    for i in range(tries):
        try:
            return fn()
        except sync.ApiError as e:
            if i == tries - 1 or '인증키' in str(e):
                raise
            w = 30 * (i + 1)
            print('[위임] %s 실패(%s) → %d초 뒤 다시 시도 (%d/%d)' % (what, str(e)[:80], w, i + 1, tries - 1), flush=True)
            time.sleep(w)


def list_laws(oc, limit=None):
    rows, page = [], 1
    while True:
        raw = sync.fetch('lawSearch.do', {'target': 'law', 'type': 'XML', 'nw': '3', 'display': '100', 'page': str(page)}, oc)
        root = ET.fromstring(sync.fix_xml(raw))
        total = int((root.findtext('totalCnt') or '0').strip() or 0)
        got = sync.parse_law_list(raw)
        if not got:
            break
        rows += [r for r in got if r['현행연혁코드'] in ('현행', '') and r.get('법령구분명') in KINDS]
        print('[위임] 목록 %d쪽 (전체 %d건, 대상 %d건)' % (page, total, len(rows)), flush=True)
        if page * 100 >= total or (limit and len(rows) >= limit):
            break
        page += 1
    if len(rows) < 100 and not limit:
        raise sync.ApiError('법령 목록이 너무 적게 왔어요(%d건). 아무것도 바꾸지 않고 멈춰요.' % len(rows))
    return rows[:limit] if limit else rows


def from_api(oc, limit=None):
    d = load()
    rows = retry(lambda: list_laws(oc, limit), '법령 목록')
    t0, done, skip, fail = time.time(), 0, 0, 0
    for i, r in enumerate(rows, 1):
        name = r['법령명한글']
        old = d['laws'].get(name)
        if old and old.get('mst') == r['법령일련번호'] and old.get('src') == 'api':
            skip += 1
            continue
        if (time.time() - t0) / 60 > BUDGET_MIN:
            print('[위임] 시간이 다 돼 여기까지 저장하고 멈춰요. 다음 실행이 이어받아요.')
            break
        try:
            raw = sync.fetch('lawService.do', {'target': 'law', 'type': 'XML', 'MST': r['법령일련번호']}, oc, tries=2, timeout=40)
            root = ET.fromstring(sync.fix_xml(raw))
            art = root.find('조문')
            text = '\n'.join(sync.render_articles(list(art.iter('조문단위')))) if art is not None else ''
            it = extract(text)
        except Exception as e:                       # 한 건 실패는 건너뛰고 계속
            fail += 1
            print('[위임] 실패 %s: %s' % (name, str(e)[:100]), flush=True)
            continue
        if it:
            d['laws'][name] = {'kind': r['법령구분명'], 'mst': r['법령일련번호'], 'eff': r['시행일자'], 'src': 'api', 'items': it}
        else:
            d['laws'][name] = {'kind': r['법령구분명'], 'mst': r['법령일련번호'], 'eff': r['시행일자'], 'src': 'api', 'items': []}
        done += 1
        if done % 100 == 0:
            save(d)
            print('[위임] %d/%d (받음 %d, 건너뜀 %d, 실패 %d)' % (i, len(rows), done, skip, fail), flush=True)
    # 현행 목록에서 사라진 법령은 정리(제한 실행이 아닐 때만)
    prev_api = sum(1 for v in d['laws'].values() if v.get('src') == 'api')
    if not limit and (prev_api == 0 or len(rows) >= 0.9 * prev_api):   # 목록이 평소보다 크게 줄었으면 정리하지 않아요
        names = {r['법령명한글'] for r in rows}
        for k in [k for k, v in d['laws'].items() if v.get('src') == 'api' and k not in names]:
            d['laws'].pop(k)
    save(d)
    print('[위임] 끝: 받음 %d, 건너뜀 %d, 실패 %d, 저장 법령 %d건' % (done, skip, fail, len(d['laws'])))


def upcoming(oc):
    """법제처 「시행예정」 법령 목록 → indexes/upcoming.json (법령 본문은 받지 않아요)."""
    rows, page, total = [], 1, 0
    while True:
        raw = sync.fetch('lawSearch.do', {'target': 'law', 'type': 'XML', 'nw': '2', 'display': '100', 'page': str(page)}, oc)
        root = ET.fromstring(sync.fix_xml(raw))
        total = int((root.findtext('totalCnt') or '0').strip() or 0)
        got = sync.parse_law_list(raw)
        if not got:
            break
        rows += got
        if page * 100 >= total or page >= 60:
            break
        page += 1
    out = []
    for r in rows:
        if r.get('법령구분명') not in KINDS or not r.get('시행일자'):
            continue
        out.append({'name': r['법령명한글'], 'kind': r['법령구분명'], 'eff': r['시행일자'], 'rev': r.get('제개정구분명', ''), 'mst': r['법령일련번호']})
    out.sort(key=lambda z: (z['eff'], z['name']))
    p = os.path.join(ROOT, 'indexes', 'upcoming.json')
    try:
        old = {z['mst']: z for z in json.load(open(p, encoding='utf-8')).get('laws', [])}
    except Exception:
        old = {}
    t0 = time.time()
    for z in out:                                    # 시행예정 판 본문에서 옛 법령명·바뀌는 조문을 읽어요(실패해도 목록은 남김)
        o = old.get(z['mst'])
        if o and 'prev' in o:
            z['prev'], z['arts'] = o['prev'], o['arts']
            continue
        if (time.time() - t0) / 60 > 25:
            break
        try:
            root = ET.fromstring(sync.fix_xml(sync.fetch('lawService.do', {'target': 'law', 'type': 'XML', 'MST': z['mst']}, oc, tries=2, timeout=40)))
            base = root.find('기본정보')
            pv = (base.findtext('이전법령명') or '').strip() if base is not None else ''
            z['prev'] = pv if pv and pv != z['name'] else ''
            arts = []
            for u in root.iter('조문단위'):
                if (u.findtext('조문변경여부') or '').strip() != 'Y' or (u.findtext('조문여부') or '조문').strip() != '조문':
                    continue
                n, g = (u.findtext('조문번호') or '').strip(), (u.findtext('조문가지번호') or '').strip()
                if n:
                    arts.append(['제%s조%s' % (n, '의' + g if g else ''), (u.findtext('조문제목') or '').strip(), (u.findtext('조문시행일자') or z['eff']).strip()])
            z['arts'] = arts
        except Exception as e:
            print('[예정] 본문 읽기 실패 %s: %s' % (z['name'], str(e)[:80]), flush=True)
    tmp = p + '.tmp'
    json.dump({'asof': sync.now()[:10], 'laws': out}, open(tmp, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    os.replace(tmp, p)
    print('[예정] 시행예정 목록 %d건(전체 %d건 중 법률·시행령 등 %d건)' % (len(out), total, len(out)))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--mode', choices=['repo', 'api', 'upcoming'], default='repo')
    ap.add_argument('--limit', type=int)
    a = ap.parse_args()
    if a.mode == 'repo':
        from_repo()
    elif a.mode == 'upcoming':
        oc = os.environ.get('LAW_OC', '').strip()
        if not oc:
            sys.exit('LAW_OC(법제처 인증키)가 없어요.')
        retry(lambda: upcoming(oc), '시행예정 목록')
    else:
        oc = os.environ.get('LAW_OC', '').strip()
        if not oc:
            sys.exit('LAW_OC(법제처 인증키)가 없어요.')
        from_api(oc, a.limit)
