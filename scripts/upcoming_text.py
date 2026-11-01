#!/usr/bin/env python3
"""개정 예정 법령의 바뀌는 조문 본문(이전·이후)을 받아 indexes/upcoming_text.json으로 저장함.

  LAW_OC=<인증키> python3 scripts/upcoming_text.py [--budget 40] [--limit 0]
    · 먼저 `delegation.py --mode upcoming`으로 indexes/upcoming.json을 만들어 둘 것.
    · 법령마다 시행예정 판을 시행일 순서로 받아, 첫 판은 저장소 laws/의 현행 본문과,
      그 다음 판은 바로 앞 판과 조 단위로 견줘 「이전·이후」 문장을 남김.
    · 이미 받은 판(mst)은 다시 받지 않음. 한 번에 다 못 끝나면 다음 실행에서 이어서 받음.
    · 시행이 지난 판은 목록(upcoming.json)에서 빠지므로 결과에서도 지움.

결과 형식 (indexes/upcoming_text.json)
  {"asof": "YYYY-MM-DD",
   "laws": {"법령명": [{"eff": "YYYYMMDD", "mst": "…", "base": "repo"|"prev"|"", "u": [[조, "n"|"c"|"d", 이전, 이후], …]}, …]}}
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


def current_units(name):
    """저장소 laws/에 있는 현행 본문을 조 단위로 읽음. 없으면 None."""
    hits = glob.glob(os.path.join(ROOT, 'laws', '*', '*_%s.md' % sync.safe(name)))
    hits = [h for h in hits if os.sep + '연혁' + os.sep not in h]
    if not hits:
        return None
    return history.units(open(sorted(hits)[0], encoding='utf-8').read())


def only_articles(u):
    return [x for x in u if x[0].startswith('제')]


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
    out, t0, done, fail, n = {}, time.time(), 0, 0, 0
    for name, vs in sorted(by.items()):
        vs.sort(key=lambda z: (z['eff'], z['mst']))
        cache = {e['mst']: e for e in old.get(name, [])}
        if any(z['mst'] not in cache for z in vs):   # 새 판이 하나라도 있으면 그 법령은 모든 판을 다시 받아 앞 판과 견줌
            cache = {}
        res, prev_units, base = [], None, 'repo'
        stop = False
        for z in vs:
            e = cache.get(z['mst'])
            fresh = e is None
            if fresh:
                if (time.time() - t0) / 60 > a.budget or (a.limit and n >= a.limit):
                    stop = True
                    break
                try:
                    data = sync.fetch('lawService.do', {'target': 'law', 'type': 'XML', 'MST': z['mst']}, oc, tries=2, timeout=60)
                    meta = {'법령ID': '', '법령명한글': name, '법령구분명': z.get('kind', ''), '소관부처명': '', '법령일련번호': z['mst'],
                            '공포일자': '', '공포번호': '', '시행일자': z['eff'], '제개정구분명': z.get('rev', '')}
                    md, _ = sync.law_markdown(data, meta)
                    cur = history.units(md)
                    n += 1
                except Exception as ex:
                    print('[예정본문] 실패 %s %s: %s' % (name, z['eff'], str(ex)[:90]), flush=True)
                    fail += 1
                    stop = True
                    break
                bu = prev_units if prev_units is not None else current_units(name)
                if bu is None:
                    e = {'eff': z['eff'], 'mst': z['mst'], 'base': '', 'u': []}
                else:
                    e = {'eff': z['eff'], 'mst': z['mst'], 'base': 'prev' if prev_units is not None else 'repo',
                         'u': only_articles(history.diff_units(bu, cur))}
                prev_units = cur
            else:
                prev_units = None   # 캐시된 판은 본문을 들고 있지 않으니, 다음 판은 현행 본문과 견주지 않고 건너뜀
            res.append(e)
        if res:
            out[name] = res if not stop else res
        done += 1
        if stop and (a.limit and n >= a.limit):
            break
    # 이번 목록에 없는 판은 지움(시행 끝남)
    keep = {}
    for name, es in out.items():
        ms = {z['mst'] for z in by.get(name, [])}
        es = [e for e in es if e['mst'] in ms]
        if es:
            keep[name] = es
    for name, es in old.items():       # 이번에 못 받은 법령은 이전 결과를 그대로 둠
        if name in by and name not in keep:
            ms = {z['mst'] for z in by[name]}
            es = [e for e in es if e['mst'] in ms]
            if es:
                keep[name] = es
    tmp = OUT + '.tmp'
    json.dump({'asof': history.today(), 'laws': keep}, open(tmp, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    os.replace(tmp, OUT)
    print('[예정본문] 법령 %d개 저장(새로 받은 판 %d건, 실패 %d건, %.1f분)' % (len(keep), n, fail, (time.time() - t0) / 60))


if __name__ == '__main__':
    main()
