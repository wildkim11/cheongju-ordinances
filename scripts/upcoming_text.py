#!/usr/bin/env python3
"""개정 예정 법령의 바뀌는 조문 본문(이전·이후)을 받아 indexes/upcoming_text.json으로 저장함.

  LAW_OC=<인증키> python3 scripts/upcoming_text.py [--budget 40] [--limit 0]
    · 먼저 `delegation.py --mode upcoming`으로 indexes/upcoming.json을 만들어 둘 것.
    · 시행예정 판마다 법제처 연혁에서 「공포 순서로 바로 앞 판」을 찾아 조 단위로 견줘 「이전·이후」 문장을 남김
      (시행일 순서가 아니라 공포 순서임. 먼저 공포됐지만 나중에 시행되는 판은 그 뒤에 공포된 개정이 빠져 있기 때문).
    · 견주는 조는 시행예정 목록(upcoming.json)에서 「조문 변경」으로 표시된 조만 남김.
    · 이미 받은 판(mst)은 다시 받지 않음. 한 번에 다 못 끝나면 다음 실행에서 이어서 받음.
    · 시행이 지난 판은 목록(upcoming.json)에서 빠지므로 결과에서도 지움.

결과 형식 (indexes/upcoming_text.json)
  {"asof": "YYYY-MM-DD",
   "laws": {"법령명": [{"eff": "YYYYMMDD", "mst": "…", "base": "pred"|"cur"|"repo"|"new"|"hist"|"none", "pm": 앞 판 mst, "u": [[조, "n"|"c"|"d", 이전, 이후], …]}, …]}}
표준 라이브러리만 씀.
"""
import argparse, glob, json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.dirname(HERE)
import sync, history  # noqa: E402

UP = os.path.join(ROOT, 'indexes', 'upcoming.json')
OUT = os.path.join(ROOT, 'indexes', 'upcoming_text.json')


def jload(p, d):
    try:
        return json.load(open(p, encoding='utf-8'))
    except Exception:
        return d


import xml.etree.ElementTree as ET


def only_articles(u):
    return [x for x in u if x[0].startswith('제')]


class Getter:
    """판(mst) 하나를 받아 조 단위로 돌려줌. 같은 실행 안에서는 한 번만 받음."""
    def current(self, lid, name, kind='', efyd=''):
        """법령ID로 지금 시행 중인 판(현행)을 받아 (일련번호, 조 단위)로 돌려줌."""
        q = {'target': 'eflaw', 'type': 'XML', 'ID': lid, 'efYd': efyd} if efyd else {'target': 'law', 'type': 'XML', 'ID': lid}
        data = sync.fetch('lawService.do', q, self.oc, tries=2, timeout=60)
        root = ET.fromstring(sync.fix_xml(data))
        mst = (root.findtext('기본정보/법령일련번호') or root.attrib.get('법령키') or '').strip() or 'cur:' + lid
        self.cureff = (root.findtext('기본정보/시행일자') or '').strip()
        if mst not in self.mem:
            meta = {'법령ID': lid, '법령명한글': name, '법령구분명': kind, '소관부처명': '', '법령일련번호': mst,
                    '공포일자': '', '공포번호': '', '시행일자': '', '제개정구분명': ''}
            md, _ = sync.law_markdown(data, meta)
            self.mem[mst] = history.units(md)
        return mst, self.mem[mst]

    def __init__(self, oc):
        self.cureff = ''
        self.oc, self.mem, self.lid = oc, {}, {}

    def units(self, mst, name, kind='', eff='', rev=''):
        if mst in self.mem:
            return self.mem[mst]
        data = sync.fetch('lawService.do', {'target': 'law', 'type': 'XML', 'MST': mst}, self.oc, tries=2, timeout=60)
        try:
            self.lid[mst] = (ET.fromstring(sync.fix_xml(data)).findtext('기본정보/법령ID') or '').strip()
        except Exception:
            self.lid[mst] = ''
        meta = {'법령ID': self.lid[mst], '법령명한글': name, '법령구분명': kind, '소관부처명': '', '법령일련번호': mst,
                '공포일자': '', '공포번호': '', '시행일자': eff, '제개정구분명': rev}
        md, _ = sync.law_markdown(data, meta)
        self.mem[mst] = history.units(md)
        return self.mem[mst]


def ef_rows(oc, lid, name):
    """시행일 기준 목록(eflaw)에서 법령ID가 같은 판들. 연혁·시행예정·현행을 함께 요청함."""
    out = {}
    for nw in ('1,2,3', ''):
        for page in range(1, 11):
            q = {'target': 'eflaw', 'type': 'XML', 'query': name, 'search': '1', 'display': '100', 'page': str(page)}
            if nw:
                q['nw'] = nw
            try:
                rs = sync.parse_law_list(sync.fetch('lawSearch.do', q, oc, tries=2, timeout=30))
            except Exception as e:
                print('[예정본문] 시행일 목록 실패 %s: %s' % (name, str(e)[:70]), flush=True)
                break
            for r in rs:
                if r.get('법령ID') == lid:
                    out[r['법령일련번호']] = r
            if len(rs) < 100:
                break
        if len(out) > 1:
            break
    return list(out.values())


def dayb(eff):
    """시행일 하루 전(YYYYMMDD). 그날 시행 중이던 판이 「이전 판」임."""
    import datetime
    try:
        return (datetime.date(int(eff[:4]), int(eff[4:6]), int(eff[6:8])) - datetime.timedelta(days=1)).strftime('%Y%m%d')
    except Exception:
        return ''


def repo_units(name):
    """저장소 laws/ 아래 현행 본문(연혁 제외)을 조 단위로. 없으면 None."""
    fs = [f for f in glob.glob(os.path.join(ROOT, 'laws', '*', '*_%s.md' % sync.safe(name))) if '연혁' not in f]
    return history.units(open(fs[0], encoding='utf-8').read()) if fs else None


def dated_articles(keep):
    """현행 본문 안에 「조문별 시행일」이 뒤로 잡힌 조(laws.json의 조문시행일자문자열)의 이전·이후를
    저장소 변경 이력(history/l/<ID>.json)에서 가져와 keep에 넣음. 법제처를 다시 부르지 않음.
    이력의 가장 최근 기록 가운데 그 조를 바꾼 기록의 이전·이후를 씀."""
    import re
    laws = jload(os.path.join(ROOT, 'indexes', 'laws.json'), [])
    td = history.today().replace('-', '')
    add = 0
    for x in laws:
        raw = (x.get('info') or {}).get('조문시행일자문자열', '')
        if not raw or not x.get('id'):
            continue
        by = {}
        for ln in raw.split('\n'):
            d, _, rest = ln.partition(':')
            if d.isdigit() and len(d) == 8 and d > td and rest:
                for a in rest.split(','):
                    m = re.match(r'제\d+조(?:의\d+)?', a.strip())
                    if m:
                        by.setdefault(d, []).append(m.group(0))
        if not by:
            continue
        hf = jload(os.path.join(ROOT, 'history', 'l', '%s.json' % x['id']), {})
        evs = list(reversed(hf.get('ev') or []))
        if not evs:
            continue
        name = x['name']
        for d, arts in sorted(by.items()):
            if any(e.get('eff') == d for e in keep.get(name, [])):
                continue
            u, seen = [], set()
            for a in arts:
                if a in seen:
                    continue
                seen.add(a)
                for ev in evs:
                    hit = [t for t in (ev.get('u') or []) if t[0] == a]
                    if hit:
                        u.append(list(hit[0]))
                        break
            if u:
                keep.setdefault(name, []).append({'eff': d, 'mst': x.get('mst', ''), 'base': 'hist', 'u': u})
                add += 1
    for name in keep:
        keep[name].sort(key=lambda e: (e['eff'], e.get('mst', '')))
    print('[예정본문] 조문별 시행일이 뒤인 조 %d건을 변경 이력에서 채움' % add)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--budget', type=float, default=40, help='분 단위 시간 한도')
    ap.add_argument('--limit', type=int, default=0, help='시험용: 이 건수만 받음')
    a = ap.parse_args()
    oc = os.environ.get('LAW_OC', '')
    if not oc:
        sys.exit('LAW_OC(인증키)가 없어요.')
    up = jload(UP, {}).get('laws', [])
    old = jload(OUT, {}).get('laws', {})
    by = {}
    for z in up:
        by.setdefault(z['name'], []).append(z)
    G, t0, n, fail = Getter(oc), time.time(), 0, 0
    keep, over = {}, False
    for name, vs in sorted(by.items()):
        vs.sort(key=lambda z: (z['eff'], z['mst']))
        cache = {e['mst']: e for e in old.get(name, []) if e.get('base') in ('pred', 'repo', 'cur', 'new')}   # pred·repo로 받은 판만 재사용(prev·빈 값은 옛 방식이라 다시 받음)
        res, rows, idx, ef = [], None, {}, None
        for z in vs:
            e = cache.get(z['mst'])
            if e is None and not over:
                if (time.time() - t0) / 60 > a.budget or (a.limit and n >= a.limit):
                    over = True
                else:
                    try:
                        cur = G.units(z['mst'], name, z.get('kind', ''), z['eff'], z.get('rev', ''))
                        if rows is None:
                            rows, _ = history.law_versions(sync, oc, G.lid.get(z['mst'], ''), [name])
                            idx = {r['법령일련번호']: i for i, r in enumerate(rows)}
                        i = idx.get(z['mst'])
                        pred = rows[i - 1] if (i is not None and i > 0) else None
                        if pred is None:
                            bu, cm, new = None, '', False
                            if ef is None:
                                ef = ef_rows(oc, G.lid.get(z['mst'], ''), name)
                            cand = [r for r in ef if r.get('시행일자') and r['시행일자'] < z['eff'] and r['법령일련번호'] != z['mst']]
                            if cand:      # 시행일 순으로 바로 앞(이 판 시행 직전까지 시행 중이던) 판
                                c = max(cand, key=lambda r: (r['시행일자'], r.get('공포일자', ''), r['법령일련번호']))
                                try:
                                    bu, cm = G.units(c['법령일련번호'], name, z.get('kind', ''), c['시행일자'], c.get('제개정구분명', '')), c['법령일련번호']
                                except Exception as ex2:
                                    print('[예정본문] 이전 판 받기 실패 %s: %s' % (name, str(ex2)[:70]), flush=True)
                            elif z.get('rev') == '제정':
                                new = True      # 새로 제정되는 법령이라 이전 판이 없음
                            if bu is None and not new:
                                bu = repo_units(name)      # 그래도 없으면 저장소 현행 본문과 견줌
                            if bu is None and new:
                                e = {'eff': z['eff'], 'mst': z['mst'], 'base': 'new', 'u': []}
                            elif bu is None:
                                print('[예정본문] 앞 판 없음 %s %s (연혁 %d판, 시행일 목록 %d판, 이 판 %s)' % (name, z['eff'], len(rows or []), len(ef or []), '있음' if i is not None else '없음'), flush=True)
                                e = {'eff': z['eff'], 'mst': z['mst'], 'base': 'none', 'u': []}
                            else:
                                want = {x[0] for x in z.get('arts', [])}
                                d = only_articles(history.diff_units(bu, cur))
                                if want:
                                    d = [x for x in d if x[0] in want]
                                e = {'eff': z['eff'], 'mst': z['mst'], 'base': 'cur' if (cm and bu is not None) else 'repo', 'u': d}
                        else:
                            bu = G.units(pred['법령일련번호'], name, z.get('kind', ''), pred.get('시행일자', ''), pred.get('제개정구분명', ''))
                            want = {x[0] for x in z.get('arts', [])}
                            d = only_articles(history.diff_units(bu, cur))
                            if want:
                                d = [x for x in d if x[0] in want]
                            e = {'eff': z['eff'], 'mst': z['mst'], 'base': 'pred', 'pm': pred['법령일련번호'], 'u': d}
                        n += 1
                    except Exception as ex:
                        print('[예정본문] 실패 %s %s: %s' % (name, z['eff'], str(ex)[:90]), flush=True)
                        fail += 1
                        e = None
            if e is None:      # 이번에 못 받은 판은 이전 결과가 있으면 그대로 둠
                e = next((o for o in old.get(name, []) if o['mst'] == z['mst']), None)
            if e:
                res.append(e)
        if res:
            keep[name] = res
    dated_articles(keep)
    tmp = OUT + '.tmp'
    json.dump({'asof': history.today(), 'laws': keep}, open(tmp, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    os.replace(tmp, OUT)
    print('[예정본문] 법령 %d개 저장(새로 받은 판 %d건, 실패 %d건, %.1f분%s)' % (len(keep), n, fail, (time.time() - t0) / 60, ', 시간 한도로 일부 남음' if over else ''))


if __name__ == '__main__':
    main()
