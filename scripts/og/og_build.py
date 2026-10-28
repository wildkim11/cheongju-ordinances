#!/usr/bin/env python3
"""조직 연혁 자동 생성의 부품: 조례 본문(행정기구·위원회)과 시행규칙 별표에서 시점별 조직 구조를 읽는다."""
import re, json

def _nz(s):
    return re.sub(r'\s+', '', s or '').replace('ㆍ', '·')

def _strip_rev(s):
    """<개정 …> [본조신설 …] 같은 이력 표기를 지움."""
    s = re.sub(r'<[^<>]*>', ' ', s)
    s = re.sub(r'\[[^\[\]]*(개정|신설|삭제|전문|제목)[^\[\]]*\]', ' ', s)
    return s

def split_names(s):
    s = re.sub(r'\s+', ' ', s).strip()
    s = re.sub(r'(을|를)\s*(각각\s*)?(둔다|설치한다).*$', '', s)
    return [x.strip() for x in re.split(r'[,，ㆍ·、]|\s및\s', s) if x.strip()]

def articles(text):
    """본문을 {조번호(예: '6의2'): (제목, 내용)} 으로 나눔(본칙만: 부칙 앞까지)."""
    body = text.split('\n## 부칙')[0]
    out = {}
    cur = None
    for line in body.split('\n'):
        m = re.match(r'^제(\d+)조(?:의(\d+))?\(([^)]*)\)\s*(.*)$', line)
        m2 = re.match(r'^제(\d+)조(?:의(\d+))?\s*$', line)
        if m:
            cur = m.group(1) + ('의' + m.group(2) if m.group(2) else '')
            out[cur] = [m.group(3), m.group(4)]
        elif cur and line.strip() and not line.startswith('#'):
            out[cur][1] += '\n' + line
    return out

def parse_jungwon(text):
    """행정기구 및 정원 조례 → 보좌기관, 국·실(과 목록). 폐지(삭제) 조항은 무시."""
    A = articles(text)
    res = {'bojwa': [], 'guk': []}
    for no, (title, body) in A.items():
        b = _strip_rev(body)
        if title.startswith('보좌기관'):
            names = []
            for part in re.findall(r'([^,]*?)을\s*,|([^,]*?)을\s*둔다', b):
                for g in part:
                    if g:
                        names += [x for x in re.split(r'[ㆍ·]', g) if x.strip()]
            m = re.search(r'보좌하기\s*위하여\s*(.*?)을,\s*부시장을\s*보좌하기\s*위하여\s*(.*?)을\s*둔다', re.sub(r'\s+', ' ', b))
            if m:
                names = [x.strip() for g in m.groups() for x in re.split(r'[ㆍ·]', g) if x.strip()]
            res['bojwa'] = names
        elif title.startswith('실') and '설치' in title:
            m = re.search(r'위하여\s*(.*?)을\s*두고', re.sub(r'\s+', ' ', b))
            if m:
                res['guk_order'] = split_names(m.group(1) + '을 둔다')
        else:
            m = re.match(r'^(.+?)에\s*두는\s*과$', title)
            if m and no != '':
                g = m.group(1)
                mm = re.match(r'^\s*' + re.escape(g) + r'에\s*(.*?)(?:을|를)\s*둔다', re.sub(r'\s+', ' ', b))
                if mm:
                    res['guk'].append((g, split_names(mm.group(1) + '를 둔다')))
    return res

def parse_committee(text):
    """위원회 조례 제6조 ② → {위원회: [소관 기관…]} (삭제 항목 제외)."""
    A = articles(text)
    body = None
    for no, (title, b) in A.items():
        if no == '6':
            body = b
    if body is None:
        return {}
    out = {}
    cur = None
    for line in body.split('\n'):
        line = line.strip()
        m = re.match(r'^\d+\.\s*(.+?위원회)\b', line)
        if m:
            cur = m.group(1)
            out[cur] = []
            continue
        m = re.match(r'^[가-힣]\.\s*(.*)$', line)
        if m and cur:
            t = _strip_rev(m.group(1)).strip()
            if t.startswith('삭제'):
                continue
            t = re.sub(r'\s*소관에\s*관한\s*사항.*$', '', t)
            t = re.sub(r'\s*소관에\s*속하는.*$', '', t)
            out[cur] += [x.strip() for x in re.split(r'[,，]', t) if x.strip()]
    return out
