#!/usr/bin/env python3
"""indexes/og.json(조직 연혁) -> indexes/org.json(소관 위원회·부서 트리, 고정 ID)

다른 프로그램이 위원회와 부서 트리를 가져다 쓰도록 만든 가벼운 파일.
  python scripts/og/og_org.py [og.json 경로] [org.json 경로]
기본값: indexes/og.json -> indexes/org.json

고정 ID 규칙
 - 위원회 C01.. : og.json의 CM 순서. 이름이 바뀌어도(행정문화위원회→행정안전위원회) 같은 ID.
 - 기관·부서 N001.. : 조직 시점(S)을 오래된 순으로 읽으며 처음 나온 순서로 매김.
   계보(LN)의 개칭·개편·이관은 앞 이름의 ID를 이어받고, 통합·분리·폐지는 새 ID(계보만 연결).
 - 연혁은 덧붙이기만 하므로 이미 매긴 ID는 바뀌지 않음.
"""
import json, sys, os

RENAME = ('개칭', '개편', '이관')


def ogkey(t, o, g):
    """분석기 ogKey와 같은 규칙: 부서(과)를 구분하는 이름"""
    if t in ('국·실', '보좌기관'):
        return g or o
    if t == '구청':
        return '구청 ' + g
    if not g:
        return o
    return o + ' ' + (g[2:] if (o == '도서관평생학습본부' and g.startswith('청주')) else g)


def build(og):
    S = sorted(og['S'], key=lambda s: s['f'])
    cm_id, cm_out = {}, []
    for i, c in enumerate(og['CM']):
        cid = 'C%02d' % (i + 1)
        names = [{'name': h[0], 'from': h[1], 'to': h[2]} for h in c[2]]
        cm_out.append({'id': cid, 'name': c[0], 'names': names})
        cm_id[c[0]] = cid
        for h in c[2]:
            cm_id.setdefault(h[0], cid)

    ren = {}
    for e in og['LN'] + og.get('LN0', []):
        if e[3] in RENAME:
            ren.setdefault(e[1], []).append(e[0])

    idmap, nodes, order = {}, {}, []

    def nid(name):
        if name in idmap:
            return idmap[name]
        for old in ren.get(name, []):
            if old in idmap:
                idmap[name] = idmap[old]
                return idmap[name]
        idmap[name] = 'N%03d' % (len(order) + 1)
        order.append(idmap[name])
        return idmap[name]

    def put(name, level, typ, parent, cm, P, mu=False):
        i = nid(name)
        nd = nodes.setdefault(i, {'id': i, 'level': level, 'hist': []})
        rec = {'from': P['f'], 'to': P['t'], 'name': name, 'type': typ,
               'parent': parent, 'committee': cm}
        if mu:
            rec['multi'] = True
        h = nd['hist']
        if h and all(h[-1].get(k) == rec.get(k) for k in ('name', 'type', 'parent', 'committee', 'multi')):
            h[-1]['to'] = rec['to']
        else:
            h.append(rec)
        return i

    for P in S:
        for n in P['N']:
            t, cmname, o, kids = n[0], n[1], n[2], n[3] or []
            cm = cm_id.get(cmname) if cmname else None
            if t == '읍면동':
                cm = cm_id.get('행정안전위원회')
            mu = (t == '구청')
            if t in ('국·실',):
                u = put(o, 'unit', t, None, cm, P)
                for g in kids:
                    put(ogkey(t, o, g), 'dept', '과', u, cm, P)
            elif t in ('보좌기관',):
                put(o, 'unit', t, None, cm, P)
            else:
                u = put(o, 'unit', t, None, cm, P, mu)
                for g in kids:
                    put(ogkey(t, o, g), 'dept', '과', u, cm, P, mu)

    last = S[-1]
    cur = []
    look = {}
    for i in order:
        nd = nodes[i]
        for r in nd['hist']:
            look.setdefault(r['name'], i)
        r = nd['hist'][-1]
        if r['to'] is None:
            c = {'id': i, 'name': r['name'], 'level': nd['level'], 'type': r['type'],
                 'parent': r['parent'], 'committee': r['committee']}
            if r.get('multi'):
                c['multi'] = True
            cur.append(c)
    lin = []
    for e in og['LN0'] + og['LN']:
        lin.append({'from': e[0], 'to': e[1], 'fromId': idmap.get(e[0]), 'toId': idmap.get(e[1]),
                    'date': e[2], 'kind': e[3], 'note': e[4]})
    ver = og['VER'][-1] if og.get('VER') else ''
    out = {
        'schema': 'cheongju-org/1',
        'ver': ver,
        'note': '청주시 소관 위원회·부서 트리. committees=위원회(이름 바뀌어도 ID 고정), nodes=기관·부서(hist=기간별 이름·소속·소관 위원회), '
                'current=지금 조직, lookup=옛 이름 포함 이름→ID, lineage=개편 계보. 읍면동은 모두 행정안전위원회 소관. 구청 과는 팀마다 위원회가 갈려 2개 이상일 수 있어 committee=null, multi=true(과가 최소 단위라 팀은 나누지 않음).',
        'periods': [{'k': s['k'], 'from': s['f'], 'to': s['t']} for s in S],
        'committees': cm_out,
        'nodes': [nodes[i] for i in order],
        'current': cur,
        'lookup': look,
        'lineage': lin,
    }
    return out


def main():
    a = sys.argv[1] if len(sys.argv) > 1 else 'indexes/og.json'
    b = sys.argv[2] if len(sys.argv) > 2 else 'indexes/org.json'
    og = json.load(open(a, encoding='utf-8'))
    out = build(og)
    os.makedirs(os.path.dirname(b) or '.', exist_ok=True)
    with open(b, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, separators=(',', ':'), sort_keys=False)
        f.write('\n')
    print('org.json', len(out['nodes']), '기관·부서', len(out['committees']), '위원회', len(out['current']), '현재')


if __name__ == '__main__':
    main()
