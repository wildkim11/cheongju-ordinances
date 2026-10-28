#!/usr/bin/env python3
"""조직 연혁 og.json 만들기.
입력(캐시 폴더):  hw/<시행일>.txt  정원조례 판 본문
                   gs/<시행일>.txt  위원회 조례 판 본문
                   rule/<시행일>.json  시행규칙 판별 별표 {시트:[[제목,[사무…]]…]}
설정(선택): og_config.json {s_from, cm_from, min_move, confirmed{}}
수동 보정(선택): og_manual.json {EV:[[날짜,제목,내용]…], LN:[[이전,이후,날짜,종류,비고]…], nt:{시작일:문구}}
출력: og.json, og_report.md(변경 요약·확인 필요)"""
import sys, os, re, json, glob, html
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import og_build as P, og_gen as G

def rd(f):
    t = html.unescape(open(f, encoding='utf-8').read())
    return re.sub(r'\n(부칙\()', r'\n## \1', t)

def dot(d):  # 20240701 → 2024.7.1
    return f'{int(d[:4])}.{int(d[4:6])}.{int(d[6:])}'

def load(cache):
    key = lambda f: os.path.splitext(os.path.basename(f))[0]
    hw = {key(f): P.parse_jungwon(rd(f)) for f in glob.glob(os.path.join(cache, 'hw', '*.txt'))}
    cm = {key(f): P.parse_committee(rd(f)) for f in glob.glob(os.path.join(cache, 'gs', '*.txt'))}
    R = {key(f): json.load(open(f, encoding='utf-8')) for f in glob.glob(os.path.join(cache, 'rule', '*.json'))}
    return R, hw, cm

def build_og(cache, cfg=None, manual=None, prev=None):
    cfg = cfg or {}; manual = manual or {}
    s_from = cfg.get('s_from', '20220930'); cm_from = cfg.get('cm_from', '2022-07-06')
    R, hw, cm = load(cache)
    if not (R and hw and cm):
        sys.exit('내려받은 자료가 비어 있어요(정원조례 %d판·위원회조례 %d판·시행규칙 %d판). 연혁을 만들지 않고 멈춰요.' % (len(hw), len(cm), len(R)))
    flags = []
    mf = os.path.join(cache, 'fetch_meta.json')
    if os.path.exists(mf):
        for nmx, dx, why in json.load(open(mf, encoding='utf-8')).get('missing', []):
            flags.append(f'{nmx} {dx}판을 받지 못함({why}) — 확인 필요')
    for v in sorted(R):
        bad = [t for t in R[v] if not re.match(r'^별표\d+\(.+\)$', t)]
        if bad or not R[v]:
            flags.append(f'시행규칙 {v}판 별표 시트 형식이 달라 제외함({", ".join(bad[:3]) or "비어 있음"}) — 확인 필요'); R.pop(v)
    known = {G.nm(x) for c in cm.values() for l in c.values() for x in l}
    canon, CM, fl = G.cm_lineage(cm, cfg.get('confirmed'), cm_from, [c[0] for c in (prev or {}).get('CM', [])] or None)
    flags += fl
    allp = G.periods(R, hw, cm, canon)
    dmaps = {v: G.dutymap(R[v], known) for v in R}
    vers, DU, DEND, DBEG, DH = G.duties(R, known)
    LNall, fl = G.lineage(allp, dmaps)
    ign = set(cfg.get('ignore_ln', []))
    LNall = [x for x in LNall if f'{x[0]}|{x[1]}|{x[2]}' not in ign]
    # 확인 완료된 연결은 확인 필요 표시를 지움
    conf = set(cfg.get('confirmed_ln', []))
    LNall = [[a, b, d, k, '' if f'{a}|{b}|{d}' in conf else n] for a, b, d, k, n in LNall]
    EV = G.events(allp, hw, cm, canon, DH, LNall, cfg.get('min_move', 8))
    # 기간: s_from 이후만 S로, 이전 경계는 LN0
    first = next((i for i, p in enumerate(allp) if p['f'] >= s_from), 0)
    ps = allp[first:]
    s0 = G._iso(ps[0]['f'])
    S = []
    for i, p in enumerate(ps):
        f = G._iso(p['f']); t = None
        if i + 1 < len(ps):
            import datetime
            n = ps[i + 1]['f']; t = (datetime.date(int(n[:4]), int(n[4:6]), int(n[6:])) - datetime.timedelta(1)).isoformat()
        lb = dot(p['f']) + '~' + (dot(t.replace('-', '')) if t else '')
        ev = [e for e in EV if e[0] == f]
        nt = (manual.get('nt') or {}).get(p['f']) or (f"{dot(p['f'])} {ev[0][1]}" if ev else f"{dot(p['f'])} 기준")
        S.append({'k': f'P{i}', 'f': f, 't': t, 'lb': lb, 'nt': nt, 'N': p['N']})
    LN = [x for x in LNall if x[2] > s0]; LN0 = [x for x in LNall if x[2] <= s0]
    for m in manual.get('LN', []):
        for L in (LN, LN0):
            L[:] = [x for x in L if (x[0], x[1], x[2]) != tuple(m[:3])]
        (LN if m[2] > s0 else LN0).append(m)
    md = {e[0] for e in manual.get('EV', [])}
    EV = [e for e in EV if e[0] not in md] + manual.get('EV', [])
    EV.sort(key=lambda e: e[0])
    for a, b, d, k, n in LN + LN0:
        if n == '확인 필요': flags.append(f'계보 {d} {a}→{b} ({k}) — 확인 필요 [맞으면 confirmed_ln에 "{a}|{b}|{d}" 추가, 아니면 ignore_ln에 추가]')
    ds = lambda dd: f'{dot(min(dd))}~{dot(max(dd))}'
    SRC = [['청주시 행정기구 및 정원 조례', f'{ds(hw)} ({len(hw)}개판)'],
           ['청주시 행정기구 및 정원 조례 시행규칙', f'{ds(R)} ({len(R)}개판, 별표 분장사무)'],
           ['청주시의회 교섭단체 및 위원회 구성과 운영에 관한 조례', ', '.join(dot(d) for d in sorted(cm)) + '판 제5·6조'],
           ['청주시의회 회의록', '소관·출석 교차 확인']]
    og = {'S': S, 'CM': CM, 'LN': LN, 'EV': EV, 'SRC': SRC, 'DU': DU, 'DEND': DEND, 'DBEG': DBEG, 'DH': DH, 'VER': vers, 'LN0': LN0}
    if prev:
        po = {s['f']: s for s in prev.get('S', [])}
        for sn in S[:-1]:
            so = po.get(sn['f'])
            if so and [tuple(x) for x in so['N']] != [tuple(x) for x in sn['N']]:
                flags.append(f'과거 기간 {sn["f"]}의 구조가 기존 값과 달라졌어요 — 확인 필요')
        pv = set(prev.get('VER', []))
        if pv and not pv <= set(vers):
            flags.append('기존에 있던 판 ' + ', '.join(sorted(pv - set(vers))) + '을(를) 이번에 받지 못했어요 — 확인 필요')
        ph = {json.dumps(x, ensure_ascii=False) for x in prev.get('DH', [])}
        lost = ph - {json.dumps(x, ensure_ascii=False) for x in DH}
        if lost:
            flags.append(f'기존 분장사무 개정 이력 {len(lost)}건이 이번 결과에 없어요 — 확인 필요')
    return og, sorted(set(flags))

def report(new, old, flags):
    L = ['# 조직 연혁 자동 생성 결과', '']
    if old:
        ov, nv = set(old.get('VER', [])), set(new['VER'])
        L.append(f'- 판: {len(ov)}개 → {len(nv)}개' + (f' (새 판 {", ".join(sorted(nv - ov))})' if nv - ov else ''))
        L.append(f'- 기간(S): {len(old["S"])}개 → {len(new["S"])}개')
        for k in ('LN', 'EV', 'DH'):
            L.append(f'- {k}: {len(old.get(k, []))} → {len(new[k])}')
        so = {(n[0], n[2]): n[1] for n in old['S'][-1]['N']} if old.get('S') else {}
        sn = {(n[0], n[2]): n[1] for n in new['S'][-1]['N']}
        add = [k[1] for k in sn if k not in so]; rm = [k[1] for k in so if k not in sn]
        if add or rm: L.append(f'- 최신 기간 변동: 신설 {", ".join(add) or "없음"} / 폐지 {", ".join(rm) or "없음"}')
    L += ['', '## 확인 필요', ''] + ([f'- {x}' for x in flags] or ['- 없음'])
    return '\n'.join(L) + '\n'

if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('cache'); ap.add_argument('--out', default='og.json'); ap.add_argument('--config'); ap.add_argument('--manual'); ap.add_argument('--prev'); ap.add_argument('--report', default='og_report.md')
    a = ap.parse_args()
    j = lambda f: json.load(open(f, encoding='utf-8')) if f and os.path.exists(f) else None
    prev = j(a.prev)
    og, flags = build_og(a.cache, j(a.config), j(a.manual), prev)
    json.dump(og, open(a.out, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    open(a.report, 'w', encoding='utf-8').write(report(og, prev, flags))
    print(open(a.report, encoding='utf-8').read())
