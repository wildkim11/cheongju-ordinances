#!/usr/bin/env python3
"""조직 연혁(og.json) 자동 생성: 정원조례·위원회조례 본문 + 시행규칙 별표(분장사무)에서 다시 만든다."""
import re, json, html, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import og_build as P

def unesc(t): return html.unescape(t)

def nm(x):
    x = re.sub(r'\s+', '', x)
    if x.startswith('청주시') and x != '청주시립미술관': x = x[3:]
    return x

def struct(dm, known=()):
    """별표(시트→[(제목,[사무])]) → [(구분,[(기관,[과])])]  (읍면동 제외)"""
    out = []
    for sh, rows in dm.items():
        if '읍면동' in sh: continue
        g = re.sub(r'^별표\d+\((.*)\)$', r'\1', sh); lst = []
        for h, ds in rows:
            if h.endswith('제3조 관련)'): continue
            if not ds and g in ('직속기관', '사업소'):
                lst.append([h, []]); continue
            if g in ('직속기관', '사업소') and ds and nm(h) in known:
                lst.append([h, [], 'leaf']); continue      # 독립 소속기관(예: 청주시립미술관) — 과가 아님
            if g in ('직속기관', '사업소') and lst: lst[-1][1].append(h)
            else:
                if not lst: lst.append([g, []])
                lst[-1][1].append(h)
        out.append((g, lst))
    return out

def sosok_map(cm):
    """위원회 소관 {위원회:[기관]} → {기관(공백제거):위원회}"""
    r = {}
    for c, l in cm.items():
        for o in l: r[nm(o)] = c
    return r

def snapshot(jw, cm, dm):
    """한 시점의 노드 목록 [구분, 위원회, 기관, [과]]"""
    sm = sosok_map(cm)
    def com(n):
        n = nm(n)
        if n in sm: return sm[n]
        for k, v in sm.items():
            if n.startswith(k) or k.startswith(n): return v
        return None
    N = []
    gk = {g: l for g, l in jw['guk']}
    for g in jw.get('guk_order') or [g for g, _ in jw['guk']]:
        N.append(['국·실', com(g), g, list(gk.get(g, []))])
    for b in jw['bojwa']: N.append(['보좌기관', com(b), b, []])
    st = struct(dm, set(sm))
    jsn = {n[2] for n in N}
    for g, l in st:
        if g in ('직속기관', '사업소'):
            for it in l:
                a, b = it[0], it[1]
                a2 = nm(a)
                if a2 in jsn: continue
                if a2 in ('상당보건소',):
                    N.append([g, com('보건소'), a2, [x for x in b if '보건소' not in x]])
                    for x in ('서원보건소', '흥덕보건소', '청원보건소'): N.append([g, com('보건소'), x, []])
                    continue
                N.append([g, com(a2), a2, list(b)])
        if g == '구':
            gu = l[0][1] if l else []
    N.append(['구청', None, '구청(상당·서원·흥덕·청원)', gu if st and any(g == '구' for g, _ in st) else []])
    N.append(['읍면동', None, '읍·면·동', []])
    return N


def load_local():
    import glob
    R = json.load(open('rg/duties.json'))
    def rd(f):
        t = unesc(open(f, encoding='utf-8').read())
        return re.sub(r'\n(부칙\()', r'\n## \1', t)
    hw = {os.path.basename(f)[:8]: P.parse_jungwon(rd(f)) for f in glob.glob('hw/2*.txt')}
    cm = {os.path.basename(f)[3:11]: P.parse_committee(rd(f)) for f in glob.glob('gs/GS_*.txt')}
    return R, hw, cm

def latest(d, dd):
    ks = [k for k in sorted(dd) if k <= d]
    return dd[ks[-1]] if ks else None

def latest_key(d, dd):
    ks = [k for k in sorted(dd) if k <= d]
    return ks[-1] if ks else None

def periods(R, hw, cm, canon=None):
    vers = sorted(R); snaps = []
    for v in vers:
        ck = latest_key(v, cm)
        if ck is None or latest(v, hw) is None: continue      # 조례 판이 아직 없는 이른 날짜
        c = cm[ck]
        if canon: c = {canon[(ck, n)]: l for n, l in c.items()}
        N = snapshot(latest(v, hw), c, R[v])
        snaps.append((v, N))
    # 기간 묶기(구조·소관이 같으면 같은 기간). 과 목록 순서·구청 과는 비교에 포함
    sig = lambda N: json.dumps(N, ensure_ascii=False, sort_keys=True)
    out = []
    for v, N in snaps:
        if out and sig(out[-1]['N']) == sig(N): out[-1]['vs'].append(v)
        else: out.append({'f': v, 'N': N, 'vs': [v]})
    return out

def _bg(s):
    s = s.replace('위원회', ''); return {s[i:i+2] for i in range(len(s)-1)}

def _score(a_name, a_org, b_name, b_org):
    A = {nm(x) for x in a_org}; B = {nm(x) for x in b_org}
    j = len(A & B) / max(1, len(A | B))
    x, y = _bg(a_name), _bg(b_name)
    return j + 0.5 * len(x & y) / max(1, len(x | y))

def cm_lineage(cms, confirmed=None, cm_from='2022-07-06', order=None):
    """위원회 조례 판별 소관({위원회:[기관]}) → (canon{(판,이름):최신이름}, CM, 확인필요[])"""
    ds = sorted(cms); canon = {}; flags = []
    for n in cms[ds[-1]]: canon[(ds[-1], n)] = n
    for i in range(len(ds) - 2, -1, -1):
        d, nx = ds[i], ds[i + 1]
        cur, nxt = cms[d], cms[nx]
        used = set(); match = {}
        for n in cur:                       # 같은 이름이면 같은 위원회
            if n in nxt: match[n] = n; used.add(n)
        cand = sorted(((_score(a, cur[a], b, nxt[b]), a, b) for a in cur if a not in match for b in nxt if b not in used), reverse=True)
        for sc, a, b in cand:
            if a in match or b in used: continue
            match[a] = b; used.add(b)
            if sc < 0.3 and (confirmed or {}).get(f'{nx}|{a}') != b: flags.append(f'위원회 {a}→{b} ({nx}) 연결 신뢰 낮음(점수 {sc:.2f}) — 확인 필요')
        for n in cur:
            canon[(d, n)] = canon[(nx, match[n])] if n in match else n
            if n not in match: flags.append(f'위원회 {n} ({d}) 이어지는 위원회 없음 — 확인 필요')
    # CM: [최신이름, 최신이름, [[이름, 시작, 끝]...]]
    iso = lambda d: f'{d[:4]}-{d[4:6]}-{d[6:]}'
    import datetime
    prev = lambda d: (datetime.date(int(d[:4]), int(d[4:6]), int(d[6:])) - datetime.timedelta(1)).isoformat()
    lines = {}
    for d in ds:
        for n in cms[d]:
            c = canon[(d, n)]; L = lines.setdefault(c, [])
            if not L or L[-1][0] != n: L.append([n, iso(d), None])
    for c, L in lines.items():
        for i in range(len(L) - 1): L[i][2] = prev(L[i + 1][1].replace('-', ''))
    out = []
    for c, L in lines.items():                      # 표시 시작일 이전은 잘라냄(기본 2022-07-06)
        L = [x for x in L if x[2] is None or x[2] >= cm_from]
        if L and L[0][1] < cm_from: L[0][1] = cm_from
        if L: out.append([c, c, L])
    if order:
        pos = {c: i for i, c in enumerate(order)}
        out.sort(key=lambda r: pos.get(r[0], 99))
    return canon, out, flags

def dname(org, gwa):
    if not org: return gwa
    if org == '상당보건소': return org + ' ' + gwa
    if org in ('서원보건소', '흥덕보건소', '청원보건소'): return org
    g = gwa
    if org == '도서관평생학습본부': g = re.sub(r'^청주', '', gwa)
    return org + ' ' + g

def dutymap(dm, known):
    """한 판의 {부서명: [분장사무]} (읍면동 포함: '읍·면·동 읍' 등)"""
    out = {}
    for sh, rows in dm.items():
        g = re.sub(r'^별표\d+\((.*)\)$', r'\1', sh); org = None
        for h, ds in rows:
            if h.endswith('제3조 관련)'): continue
            ds = [re.sub(r'\s+', ' ', x).strip() for x in ds]
            if g == '읍면동':
                if h in ('읍', '면', '동'): out['읍·면·동 ' + h] = ds
                continue
            if g in ('직속기관', '사업소'):
                if not ds: org = nm(h); continue
                if nm(h) in known: out[nm(h)] = ds; org = None; continue
                if h.startswith('서원'):
                    for x in ('서원보건소', '흥덕보건소', '청원보건소'): out[x] = ds
                    continue
                out[dname(org, h)] = ds
            elif g == '구': out['구청 ' + h] = ds
            else: out[h] = ds
    return out

def duties(R, known):
    vers = sorted(R); dm = {v: dutymap(R[v], known) for v in vers}; last = {}
    for v in vers:
        for k, d in dm[v].items(): last[k] = (v, d)
    DU = {k: d for k, (v, d) in last.items()}
    DEND = {k: v for k, (v, d) in last.items() if v != vers[-1]}
    DBEG = {}
    for v in vers:
        for k in dm[v]: DBEG.setdefault(k, v)
    DH = []
    for a, b in zip(vers, vers[1:]):
        for k in sorted(set(dm[a]) | set(dm[b])):
            A = dm[a].get(k); B = dm[b].get(k)
            if A is None or B is None: continue
            ad = [x for x in B if x not in A]; rm = [x for x in A if x not in B]
            if ad or rm: DH.append([b, k, ad, rm])
    return vers, DU, DEND, DBEG, DH

def _ov(a, b):
    a, b = set(a), set(b)
    return len(a & b) / len(a) if a else 0.0

def lineage(ps, dmaps, thr=0.25):
    """기간 경계마다 사라진 부서가 어디로 갔는지 분장사무 겹침으로 추정 → LN, 확인필요"""
    LN = []; flags = []
    iso = lambda d: f'{d[:4]}-{d[4:6]}-{d[6:]}'
    for p0, p1 in zip(ps, ps[1:]):
        A, B = dmaps[p0['vs'][-1]], dmaps[p1['vs'][0]]
        d = iso(p1['f'])
        # 과·본부 단위
        gone = [k for k in A if k not in B and not k.startswith('구청') and not k.startswith('읍·면·동')]
        new = [k for k in B if k not in A and not k.startswith('구청') and not k.startswith('읍·면·동')]
        for r in gone:
            tg = sorted(((_ov(A[r], B[a]), a) for a in B if a != r), reverse=True)
            tg = [(s, a) for s, a in tg if s >= thr][:3]
            if not tg:
                LN.append([r, '(폐지)', d, '폐지', '']); continue
            top = tg[0][0]
            for s, a in tg:
                kind = '개칭' if (s >= 0.8 and a in new) else ('이관' if a in A else '분리·통합')
                if kind == '분리·통합' and a not in new: kind = '이관'
                LN.append([r, a, d, kind, '' if s >= 0.5 else '확인 필요'])
                if s < 0.5: flags.append(f'{d} {r}→{a} 사무 겹침 {s:.0%} — 확인 필요')
        # 새로 생긴 부서가 존속 중인 부서에서 갈라져 나온 경우(분리)
        have = {(x[0], x[1]) for x in LN if x[2] == d}
        for a in new:
            src = sorted(((_ov(B[a], A[r]) if False else (len(set(B[a]) & set(A[r])) / max(1, len(B[a]))), r) for r in A if r in B and r != a), reverse=True)
            if src and src[0][0] >= 0.5 and (src[0][1], a) not in have:
                LN.append([src[0][1], a, d, '분리', '' if src[0][0] >= 0.7 else '확인 필요'])
                if src[0][0] < 0.7: flags.append(f'{d} {src[0][1]}→{a} 분리 추정(겹침 {src[0][0]:.0%}) — 확인 필요')
        # 국·실 단위
        def uni(N, org):
            for n in N:
                if n[2] == org and n[0] == '국·실': return n
        ga = {n[2]: n for n in p0['N'] if n[0] == '국·실'}; gb = {n[2]: n for n in p1['N'] if n[0] == '국·실'}
        for r in [k for k in ga if k not in gb]:
            ds = [x for g in ga[r][3] for x in A.get(g, [])]
            best = sorted(((_ov(ds, [x for g in gb[a][3] for x in B.get(g, [])]), a) for a in gb), reverse=True)[0]
            LN.insert(0, [r, best[1], d, '개편', '' if best[0] >= 0.3 else '확인 필요'])
            if best[0] < 0.3: flags.append(f'{d} {r}→{best[1]} 사무 겹침 {best[0]:.0%} — 확인 필요')
    return LN, flags

def _iso(d): return f'{d[:4]}-{d[4:6]}-{d[6:]}'

def events(ps, hw, cm, canon, DH, LN, min_move=8):
    """판 시행일마다 사건 한 줄 자동 생성. [날짜, 제목, 내용]"""
    ev = {}
    def add(d, t, c):
        ev.setdefault(d, []).append((t, c))
    pstart = {p['f'] for p in ps[1:]}
    ln_by = {}
    for a, b, d, k, n in LN: ln_by.setdefault(d, []).append((a, b, k))
    for p0, p1 in zip(ps, ps[1:]):
        d = _iso(p1['f']); A = {(n[0], n[2]): n for n in p0['N']}; B = {(n[0], n[2]): n for n in p1['N']}
        ad = [k[1] for k in B if k not in A]; rm = [k[1] for k in A if k not in B]
        bits = []
        ren = [f'{a}→{b}' for a, b, k in ln_by.get(d, []) if k in ('개칭', '개편') and a in {x[1] for x in A} and b in {x[1] for x in B}]
        ren = [x for x in ren if x.split('→')[0] in rm]
        if ren: bits.append('명칭·체계 변경 ' + ', '.join(ren))
        ad2 = [x for x in ad if not any(x == r.split('→')[1] for r in ren)]
        rm2 = [x for x in rm if not any(x == r.split('→')[0] for r in ren)]
        if ad2: bits.append('신설 ' + ', '.join(ad2))
        if rm2: bits.append('폐지 ' + ', '.join(rm2))
        gA = {k: set(n[3]) for k, n in A.items() if n[0] in ('국·실',)}
        for k, n in B.items():
            if k in A and n[0] == '국·실' and set(n[3]) != gA[k]:
                x = sorted(set(n[3]) - gA[k]); y = sorted(gA[k] - set(n[3]))
                bits.append(f'{k[1]} 과 변경' + (f'(신설 {", ".join(x)}' if x else '(') + (f'{", " if x else ""}폐지 {", ".join(y)}' if y else '') + ')')
        add(d, '기구 개편 시행', '; '.join(bits) if bits else '구조 변경')
    # 조례 판
    hws = sorted(hw); cds = sorted(cm); first = ps[0]['f']
    for d in hws:
        if d <= first or d in pstart: continue
        add(_iso(d), '기구 조례 개정', '본청 구조 불변')
    for d in cds:
        if d < '20220101': continue
        i = cds.index(d)
        if i == 0: add(_iso(d), '위원회 조례 시행', f'{len(cm[d])}개 상임위'); continue
        a = {canon[(cds[i-1], n)]: set(map(nm, l)) for n, l in cm[cds[i-1]].items()}
        b = {canon[(d, n)]: set(map(nm, l)) for n, l in cm[d].items()}
        bits = []
        for c in b:
            if c in a and a[c] != b[c]:
                x = sorted(b[c] - a[c]); y = sorted(a[c] - b[c])
                bits.append(f'{c} 소관 ' + ('+' + ','.join(x) if x else '') + (' -' + ','.join(y) if y else ''))
        for c in b:
            if c not in a: bits.append(f'{c} 신설')
        ren = [f'{n}→{[m for m in cm[d] if canon[(d, m)] == canon[(cds[i-1], n)]][0]}' for n in cm[cds[i-1]] if canon[(cds[i-1], n)] in {canon[(d, m)] for m in cm[d]} and n not in cm[d]]
        if ren: bits.insert(0, '명칭 변경 ' + ', '.join(ren))
        if bits: add(_iso(d), '위원회 조례 개정', '; '.join(bits))      # 소관이 그대로면 사건으로 남기지 않음
    cnt = {}
    for d, k, ad, rm in DH: cnt.setdefault(d, set()).add(k)
    for d, ks in cnt.items():
        if _iso(d) not in ev and len(ks) >= min_move: add(_iso(d), '분장사무 조정', f'조직 불변, {len(ks)}개 과 사무 이동')
    out = []
    for d in sorted(ev):
        ts = ev[d]
        if len(ts) == 1: out.append([d, ts[0][0], ts[0][1]])
        else: out.append([d, '·'.join(sorted({t for t, c in ts}, key=lambda x: x)), ' / '.join(c for t, c in ts)])
    return out
