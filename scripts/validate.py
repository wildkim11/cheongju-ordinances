#!/usr/bin/env python3
"""색인과 파일이 맞는지 점검합니다."""
import hashlib, json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
p = os.path.join(ROOT, 'indexes', 'ordinances.json')
if not os.path.exists(p):
    print('색인이 아직 없어요(첫 수집 전).')
    sys.exit(0)
idx = json.load(open(p, encoding='utf-8'))
bad = []
ids = set()
for r in idx:
    if r['id'] in ids:
        bad.append('중복 ID ' + r['id'])
    ids.add(r['id'])
    f = os.path.join(ROOT, r['path'])
    if not os.path.exists(f):
        bad.append('파일 없음 ' + r['path'])
        continue
    t = open(f, encoding='utf-8').read()
    if hashlib.sha256(t.encode('utf-8')).hexdigest() != r['sha256']:
        bad.append('해시 불일치 ' + r['path'])
    if not t.startswith('---\n') or len(t) < 100:
        bad.append('형식 이상 ' + r['path'])
files = {os.path.relpath(os.path.join(d, n), ROOT) for d, _, ns in os.walk(os.path.join(ROOT, 'ordinances')) for n in ns if n.endswith('.md')}
extra = files - {r['path'] for r in idx}
if extra:
    bad.append('색인에 없는 파일 %d개' % len(extra))
print('색인 %d건 점검, 문제 %d건' % (len(idx), len(bad)))
for b in bad[:20]:
    print(' ', b)
sys.exit(1 if bad else 0)
