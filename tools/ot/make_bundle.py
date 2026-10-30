#!/usr/bin/env python3
"""저장소 자료 → 업데이터가 받아 가는 자료 묶음.

사용(저장소 루트에서):
  ORD_REPO=. python3 tools/ot/make_bundle.py <출력폴더>
만드는 것
  ot_bundle.json.gz : {OT(조례 전문·인용 조문·위임·개정 예정·점검 결과), AU(인용 점검표), OD(조례·규칙 목록)}
  meta.json         : 자료 기준일과 변경 확인용 일련번호(ms), 건수
준비: node(v16 이상), python3. 저장소의 indexes/·ordinances/·laws/·reports/ 가 최신이어야 해요.
"""
import gzip, json, os, re, subprocess, sys, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def run(cmd, env):
    print('▶', ' '.join(cmd), flush=True)
    r = subprocess.run(cmd, cwd=HERE, env=env, capture_output=True, text=True)
    if r.returncode:
        sys.exit('실패: %s\n%s\n%s' % (' '.join(cmd), r.stdout[-800:], r.stderr[-800:]))


def build_ae(repo, ot):
    """화면에 표시할 점검 결과(삭제된 조문 인용·조문 없음·못 찾는 조례·옛 이름 인용)를 법령·조례 이름별로 묶음."""
    otn = lambda t: re.sub(r'\s+', '', t or '').replace('ㆍ', '·')
    aud = json.load(open(os.path.join(HERE, 'audit.json'), encoding='utf-8'))
    a6 = json.load(open(os.path.join(HERE, 'audit6.json'), encoding='utf-8'))
    laws = {x['name'] for x in json.load(open(os.path.join(repo, 'indexes', 'laws.json'), encoding='utf-8'))}
    oe = set((ot.get('oe') or {}).keys())
    ae = {'l': {}, 'o': {}, 'x': {}, 'n': {}}
    for r in aud.get('del', []):
        k = 'l' if r['law'] in laws else 'o'
        ae[k].setdefault(r['law'], {'d': [], 'm': []})['d'].append([r['ord'], r['where'], r['jo'], r.get('delx', ''), (r.get('ctx') or r.get('line') or '')[:110]])
    for r in aud.get('miss', []):
        k = 'l' if r.get('t') == 'l' else 'o'
        ae[k].setdefault(r['law'], {'d': [], 'm': []})['m'].append([r['ord'], r['where'], r['jo'], r.get('cls', ''), (r.get('ctx') or r.get('line') or '')[:110]])
    for r in aud.get('ext', []):
        ae['x'].setdefault(r['law'], []).append([r['ord'], r['where'], r['jo'], (r.get('line') or '')[:110]])
    for r in a6:
        if r.get('t') == 'o':
            ae['n'].setdefault(r['n'], []).append([r['ord'], r['where'], r['q'], 1 if otn(r['q']) in oe else 0, (r.get('line') or '')[:110]])
    print('점검 결과 표시용:', {k: len(v) for k, v in ae.items()})
    return ae


def build(repo):
    """(ot, au, od)를 돌려줌."""
    repo = os.path.abspath(os.path.expanduser(repo))
    if not os.path.isdir(os.path.join(repo, 'indexes')):
        sys.exit('조례 저장소 폴더가 아니에요(indexes 폴더가 없음): ' + repo)
    env = dict(os.environ, ORD_REPO=repo)
    run(['node', 'build_ot.js', 'ot.json'], env)
    ot = json.load(open(os.path.join(HERE, 'ot.json'), encoding='utf-8'))
    env['ASOF'] = ot.get('asof') or ''
    run(['node', 'audit.js'], env)
    run(['node', 'audit2.js'], env)
    run([sys.executable, 'mkaudit.py'], env)
    au = json.load(open(os.path.join(HERE, 'au.json'), encoding='utf-8'))
    ot['ae'] = build_ae(repo, ot)
    import od_build
    od = od_build.build(repo)
    return ot, au, od


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    out = os.path.abspath(sys.argv[1])
    repo = os.environ.get('ORD_REPO') or '.'
    os.makedirs(out, exist_ok=True)
    ot, au, od = build(repo)
    bundle = {'v': 1, 'asof': ot.get('asof', ''), 'OT': ot, 'AU': au, 'OD': od}
    hp = os.path.join(os.path.abspath(os.path.expanduser(repo)), 'history', 'index.json')
    if os.path.exists(hp):
        hi = json.load(open(hp, encoding='utf-8'))
        bundle['HI'] = {'updated': hi.get('updated', ''), 'ev': hi.get('ev', [])}
        print('변경 이력 %d건을 묶음에 넣음' % len(bundle['HI']['ev']))
    raw = json.dumps(bundle, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    gz = gzip.compress(raw, 9, mtime=0)
    open(os.path.join(out, 'ot_bundle.json.gz'), 'wb').write(gz)
    meta = {'v': 1, 'asof': ot.get('asof', ''), 'odasof': od.get('asof', ''), 'dga': ot.get('dga', ''), 'upa': ot.get('upa', ''),
            'built': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), 'ms': ot.get('ms', {}),
            'counts': {'ord': len(ot.get('o', {})), 'lawArts': sum(len(v) for v in ot.get('l', {}).values()), 'dg': len(ot.get('dg', {})), 'up': len(ot.get('up', []))},
            'size': len(gz)}
    json.dump(meta, open(os.path.join(out, 'meta.json'), 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    print('묶음 %.1f MB(압축) · 조례 전문 %d건 · 자료 기준일 %s' % (len(gz) / 1e6, meta['counts']['ord'], meta['asof']))


if __name__ == '__main__':
    main()
