#!/usr/bin/env python3
"""조례·법령 변경 이력 만들기 — 모든 조(조문 단위) 비교.

  python3 scripts/history.py daily
      sync.py가 받은 새 본문(작업 폴더)과 직전 커밋(HEAD)을 견줘 오늘 바뀐 법령·조례를 기록함.
      sync.yml에서 커밋 바로 전에 실행. 법제처 접속 없음.
  LAW_OC=<인증키> python3 scripts/history.py backfill --kind both --since 20230101 [--limit 5] [--budget 300]
      법제처 연혁 판 목록과 판별 본문을 받아 since 이후 개정마다 조 단위로 견줘 기록함.
      한 번에 다 못 끝나면 history/_state.json에 진행 상황을 남기고, 다시 실행하면 이어서 함.

결과
  history/index.json        모든 변경의 목록(화면용, 조문 본문은 없음)
  history/l/<법령ID>.json    법령별 변경 내역(바뀐 조의 이전·이후 문장)
  history/o/<자치법규ID>.json 조례·규칙별 변경 내역
표준 라이브러리만 씀.
"""
import argparse, datetime, json, os, re, subprocess, sys, time
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.dirname(HERE)
HIST = os.path.join(ROOT, 'history')
KST = datetime.timezone(datetime.timedelta(hours=9))
CAP = 30000          # 한 단위(조·부칙·별표)에 남기는 최대 글자 수
T0 = time.time()


def today():
    return datetime.datetime.now(KST).strftime('%Y-%m-%d')


def ymd(s):
    s = re.sub(r'\D', '', s or '')
    return '%s-%s-%s' % (s[:4], s[4:6], s[6:8]) if len(s) >= 8 else ''


# ---------- 마크다운 → 조 단위 ----------
FM = re.compile(r'^---\n(.*?)\n---\n', re.S)
ART = re.compile(r'^(제\d+조(?:의\d+)?)(?=[\s(（]|$)')
HEAD = re.compile(r'^제\d+(?:편|장|절|관)(?:의\d+)?\s')


def front(md):
    m = FM.match(md or '')
    out = {}
    if m:
        for line in m.group(1).split('\n'):
            k, _, v = line.partition(': ')
            try:
                out[k.strip()] = json.loads(v)
            except Exception:
                out[k.strip()] = v.strip().strip('"')
    return out


def units(md):
    """{'제1조': 본문, …, '부칙': …, '별표': …} 순서 유지."""
    body = FM.sub('', md or '', count=1)
    body = re.sub(r'^\s*# [^\n]*\n', '', body, count=1)
    out, cur, buf, sec = {}, None, [], 'main'

    def flush():
        if cur is not None:
            t = '\n'.join(buf).strip()
            if cur in out:
                out[cur] += '\n' + t
            else:
                out[cur] = t
    for line in body.split('\n'):
        s = line.strip()
        if s == '## 부칙':
            flush(); cur, buf, sec = '부칙', [], 'bu'; continue
        if s.startswith('## 별표'):
            flush(); cur, buf, sec = '별표', [], 'bp'; continue
        if sec == 'main':
            if HEAD.match(s):
                continue
            m = ART.match(s)
            if m:
                flush(); cur, buf = m.group(1), [line]; continue
            if cur is None:
                cur = '머리'
        buf.append(line)
    flush()
    return {k: v for k, v in out.items() if v.strip()}


def norm(t):
    return re.sub(r'\s+', ' ', t or '').strip()


def cap(t):
    return t if len(t) <= CAP else t[:CAP] + '\n…(이하 생략: 전체 %d자)' % len(t)


def diff_units(a, b):
    """[[조, 'n'|'c'|'d', 이전, 이후], …] (조문 순서대로)."""
    res = []
    order = list(b.keys()) + [k for k in a if k not in b]
    for k in order:
        if k not in a:
            res.append([k, 'n', '', cap(b[k])])
        elif k not in b:
            res.append([k, 'd', cap(a[k]), ''])
        elif norm(a[k]) != norm(b[k]):
            res.append([k, 'c', cap(a[k]), cap(b[k])])
    return res


# ---------- 저장 ----------
def jload(p, d):
    try:
        with open(p, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return d


def jsave(p, obj, pretty=False):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        if pretty:
            json.dump(obj, f, ensure_ascii=False, indent=1)
        else:
            json.dump(obj, f, ensure_ascii=False, separators=(',', ':'))
    os.replace(tmp, p)


class Store:
    def __init__(self):
        self.idx = jload(os.path.join(HIST, 'index.json'), {'v': 1, 'ev': []})
        self.seen = {(e['t'], e['id'], e.get('m')) for e in self.idx['ev']}
        self.files = {}
        self.n = 0

    def ent(self, t, eid, name):
        k = (t, eid)
        if k not in self.files:
            p = os.path.join(HIST, t, eid + '.json')
            self.files[k] = jload(p, {'t': t, 'id': eid, 'n': name, 'ev': []})
        f = self.files[k]
        if name:
            f['n'] = name
        return f

    def add(self, t, eid, name, meta, prev_mst, diffs, date, src, note=''):
        mst = meta.get('mst') or ''
        if (t, eid, mst) in self.seen and mst:
            return False
        ev = {'d': date, 't': t, 'id': eid, 'n': name, 'k': meta.get('kind', ''), 'm': mst, 'pm': prev_mst or '',
              'pd': ymd(meta.get('promulgated', '')), 'ed': ymd(meta.get('effective', '')), 'rv': meta.get('revision', ''),
              'a': [[u[0], u[1]] for u in diffs], 's': src}
        if note:
            ev['x'] = note
        self.idx['ev'].append(ev)
        self.seen.add((t, eid, mst))
        f = self.ent(t, eid, name)
        f['ev'].append({k: ev[k] for k in ('d', 'm', 'pm', 'pd', 'ed', 'rv', 's')} | ({'x': note} if note else {}) | {'u': diffs})
        f['ev'].sort(key=lambda e: (e.get('pd') or e['d'], e['m']))
        self.n += 1
        return True

    def save(self):
        self.idx['ev'].sort(key=lambda e: (e.get('d', ''), e.get('pd', ''), e['t'], e['n']), reverse=True)
        self.idx['updated'] = datetime.datetime.now(KST).isoformat(timespec='seconds')
        self.idx['count'] = len(self.idx['ev'])
        jsave(os.path.join(HIST, 'index.json'), self.idx)
        for (t, eid), f in self.files.items():
            jsave(os.path.join(HIST, t, eid + '.json'), f)


# ---------- 매일: 직전 커밋과 비교 ----------
def git(*a):
    return subprocess.run(['git', '-c', 'core.quotepath=false', '-C', ROOT] + list(a), capture_output=True, text=True).stdout


def head_text(path):
    r = subprocess.run(['git', '-c', 'core.quotepath=false', '-C', ROOT, 'show', 'HEAD:' + path], capture_output=True)
    return r.stdout.decode('utf-8', 'ignore') if r.returncode == 0 else None


def daily():
    st = Store()
    lines = git('status', '--porcelain', '--untracked-files=all', '--', 'laws', 'ordinances').splitlines()
    old, new = {}, {}
    for ln in lines:
        code, path = ln[:2], ln[3:].strip().strip('"')
        if ' -> ' in path:
            a, b = path.split(' -> ', 1)
            old_t = head_text(a)
            if old_t:
                old[a] = old_t
            path = b
        if not path.endswith('.md'):
            continue
        if 'D' in code:
            t = head_text(path)
            if t:
                old[path] = t
            continue
        p = os.path.join(ROOT, path)
        if os.path.exists(p):
            with open(p, encoding='utf-8') as f:
                new[path] = f.read()
        t = head_text(path)
        if t is not None:
            old[path] = t
    def key(path, md):
        fm = front(md)
        return ('l' if path.startswith('laws/') else 'o', str(fm.get('id', '')), fm)
    olds = {}
    for p, md in old.items():
        t, i, fm = key(p, md)
        olds[(t, i)] = (md, fm)
    news = {}
    for p, md in new.items():
        t, i, fm = key(p, md)
        news[(t, i)] = (md, fm)
    d = today()
    for k, (md, fm) in news.items():
        t, i = k
        if not i:
            continue
        if k in olds:
            omd, ofm = olds[k]
            diffs = diff_units(units(omd), units(md))
            if not diffs and str(ofm.get('mst')) == str(fm.get('mst')):
                continue
            st.add(t, i, fm.get('name', ''), fm, ofm.get('mst', ''), diffs, d, 'd',
                   '' if diffs else '본문 변화 없음(판 번호만 바뀜)')
        else:
            st.add(t, i, fm.get('name', ''), fm, '', [], d, 'd', '추적 시작(새로 받은 법령·조례)')
    for k, (md, fm) in olds.items():
        if k not in news and k[1]:
            st.add(k[0], k[1], fm.get('name', ''), dict(fm, mst='gone-' + d), fm.get('mst', ''), [], d, 'd', '목록에서 빠짐(폐지 또는 추적 중단)')
    st.save()
    print('오늘(%s) 기록한 변경: %d건' % (d, st.n))


# ---------- 과거 연혁 채우기 ----------
def law_versions(sync, oc, lid, names):
    """법령ID가 같은 연혁 판 목록. nw=1(연혁)로 찾고, 안 되면 다른 방식을 시도함."""
    rows, tried = {}, []
    for nm in names:
        for target, nw in (('law', '1'), ('law', ''), ('eflaw', '1')):
            for page in range(1, 11):
                q = {'target': target, 'type': 'XML', 'query': nm, 'search': '1', 'display': '100', 'page': str(page)}
                if nw:
                    q['nw'] = nw
                try:
                    rs = sync.parse_law_list(sync.fetch('lawSearch.do', q, oc, tries=2, timeout=30))
                except Exception as e:
                    tried.append('%s/%s 오류 %s' % (target, nw, str(e)[:80]))
                    break
                hit = [r for r in rs if r.get('법령ID') == lid]
                for r in hit:
                    rows[r['법령일련번호']] = r
                if len(rs) < 100:
                    break
            tried.append('%s nw=%s → %d판' % (target, nw or '-', len(rows)))
            if len(rows) > 1:
                return sorted(rows.values(), key=lambda r: (r['공포일자'], r['법령일련번호'])), tried
    return sorted(rows.values(), key=lambda r: (r['공포일자'], r['법령일련번호'])), tried


def law_md(sync, oc, row):
    data = sync.fetch('lawService.do', {'target': 'law', 'type': 'XML', 'MST': row['법령일련번호']}, oc, tries=3, timeout=60)
    meta = {k: row.get(k, '') for k in ('법령ID', '법령명한글', '법령구분명', '소관부처명', '법령일련번호', '공포일자', '공포번호', '시행일자', '제개정구분명')}
    md, _ = sync.law_markdown(data, meta)
    return md


def ord_versions(sync, oc, oid, name):
    rows = {}
    for page in range(1, 6):
        d = sync.fetch('lawSearch.do', {'target': 'ordin', 'type': 'XML', 'query': name, 'search': '1', 'display': '100',
                                        'page': str(page), 'nw': '2'}, oc, tries=2, timeout=30)
        total, rs = sync.parse_list(d)
        for r in rs:
            if r.get('자치법규ID') == oid or (sync.norm_name(r['자치법규명']) == sync.norm_name(name)
                                             and r['지자체기관명'].startswith(sync.ORG_PREFIX)):
                rows[r['자치법규일련번호']] = r
        if not rs or page * 100 >= total:
            break
    return sorted(rows.values(), key=lambda r: (r['공포일자'], r['자치법규일련번호']))


def ord_md(sync, oc, row):
    data = sync.fetch('lawService.do', {'target': 'ordin', 'type': 'XML', 'MST': row['자치법규일련번호']}, oc, tries=3, timeout=60)
    _, md = sync.to_markdown(data, dict(row))
    return md


def pick(vs, since, datek, mstk):
    """since 이후 판 + 그 바로 앞 판(비교 기준)."""
    after = [v for v in vs if (v.get(datek) or '') >= since]
    before = [v for v in vs if (v.get(datek) or '') < since]
    return ([before[-1]] if before else []) + after


def backfill(kind, since, limit, budget):
    import sync
    oc = os.environ.get('LAW_OC', '').strip()
    if not oc:
        sys.exit('LAW_OC(법제처 인증키)가 없어요.')
    st = Store()
    state = jload(os.path.join(HIST, '_state.json'), {'l': {}, 'o': {}})
    rep = []
    todo = []
    if kind in ('laws', 'both'):
        for x in jload(os.path.join(ROOT, 'indexes', 'laws.json'), []):
            if x.get('id') and x['id'] not in state['l']:
                names = [x['name']] + [n for n in [((x.get('info') or {}).get('이전법령명') or '')] if n and n != x['name']]
                todo.append(('l', x['id'], x['name'], names))
    if kind in ('ordinances', 'both'):
        for x in jload(os.path.join(ROOT, 'indexes', 'ordinances.json'), []):
            if x.get('id') and x['id'] not in state['o'] and (x.get('status') or 'active') == 'active':
                todo.append(('o', x['id'], x['name'], [x['name']]))
    if limit:
        todo = todo[:limit]
    print('할 일: %d건 (법령 완료 %d · 조례 완료 %d)' % (len(todo), len(state['l']), len(state['o'])), flush=True)
    done = 0
    for t, eid, name, names in todo:
        if time.time() - T0 > budget * 60:
            print('시간 한도(%d분)에 닿아 멈춤. 다시 실행하면 이어서 함.' % budget, flush=True)
            break
        try:
            if t == 'l':
                vs, tried = law_versions(sync, oc, eid, names)
                vs = pick(vs, since, '공포일자', '법령일련번호')
                getmd, mk, dk = (lambda r: law_md(sync, oc, r)), '법령일련번호', '공포일자'
            else:
                vs, tried = pick(ord_versions(sync, oc, eid, name), since, '공포일자', '자치법규일련번호'), []
                getmd, mk, dk = (lambda r: ord_md(sync, oc, r)), '자치법규일련번호', '공포일자'
            n_ev = 0
            prev_md, prev_mst = None, ''
            for v in vs:
                md = getmd(v)
                if prev_md is None and (v.get(dk) or '') >= since:
                    fm = front(md)
                    if st.add(t, eid, fm.get('name') or name, fm, '', [], ymd(v.get(dk, '')), 'b', '제정(첫 판)'):
                        n_ev += 1
                if prev_md is not None:
                    fm = front(md)
                    diffs = diff_units(units(prev_md), units(md))
                    if st.add(t, eid, fm.get('name') or name, fm, prev_mst, diffs, ymd(v.get(dk, '')), 'b',
                              '' if diffs else '본문 변화 없음'):
                        n_ev += 1
                prev_md, prev_mst = md, v.get(mk, '')
            state[t][eid] = {'n': len(vs), 'ev': n_ev}
            rep.append('%s %s · 판 %d · 변경 %d%s' % ('법령' if t == 'l' else '조례', name, len(vs), n_ev,
                                                  (' · ' + ' / '.join(tried)) if tried and len(vs) < 2 else ''))
            print('[%s] %s 판 %d · 변경 %d' % (t, name, len(vs), n_ev), flush=True)
        except Exception as e:
            rep.append('오류 %s: %s' % (name, str(e)[:200]))
            print('[오류]', name, str(e)[:200], flush=True)
        done += 1
        if done % 25 == 0:
            st.save(); jsave(os.path.join(HIST, '_state.json'), state)
    st.save()
    jsave(os.path.join(HIST, '_state.json'), state)
    os.makedirs(os.path.join(ROOT, 'reports'), exist_ok=True)
    with open(os.path.join(ROOT, 'reports', 'history_backfill.md'), 'w', encoding='utf-8') as f:
        f.write('# 변경 이력 채우기 결과 (%s)\n\n' % datetime.datetime.now(KST).isoformat(timespec='minutes'))
        f.write('- 이번 실행: %d건 처리, 새 변경 %d건\n- 누적: 법령 %d건 · 조례 %d건 완료\n\n' % (done, st.n, len(state['l']), len(state['o'])))
        f.write('\n'.join('- ' + r for r in rep) + '\n')
    print('이번 실행: %d건 처리 · 새 변경 %d건' % (done, st.n))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['daily', 'backfill'])
    ap.add_argument('--kind', default='both', choices=['laws', 'ordinances', 'both'])
    ap.add_argument('--since', default='20230101')
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--budget', type=float, default=300)
    a = ap.parse_args()
    if a.mode == 'daily':
        daily()
    else:
        backfill(a.kind, re.sub(r'\D', '', a.since), a.limit, a.budget)


if __name__ == '__main__':
    main()
