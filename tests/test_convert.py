import json, os, sys, tempfile, threading, unittest, http.server, urllib.parse
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import sync

LIST = '''<?xml version="1.0" encoding="UTF-8"?><OrdinSearch><totalCnt>3</totalCnt>
<law><자치법규일련번호>100</자치법규일련번호><자치법규ID>A1</자치법규ID><자치법규명>청주시 테스트 조례</자치법규명><공포일자>20250101</공포일자><공포번호>1</공포번호><제개정구분명>일부개정</제개정구분명><지자체기관명>충청북도 청주시</지자체기관명><자치법규종류>조례</자치법규종류><시행일자>20250101</시행일자><자치법규상세링크>/DRF/lawService.do?target=ordin&amp;MST=100</자치법규상세링크></law>
<law><자치법규일련번호>200</자치법규일련번호><자치법규ID>B1</자치법규ID><자치법규명>청주시 테스트 조례 시행규칙</자치법규명><공포일자>20250102</공포일자><공포번호>2</공포번호><제개정구분명>제정</제개정구분명><지자체기관명>충청북도 청주시</지자체기관명><자치법규종류>규칙</자치법규종류><시행일자>20250102</시행일자><자치법규상세링크></자치법규상세링크></law>
<law><자치법규일련번호>300</자치법규일련번호><자치법규ID>C1</자치법규ID><자치법규명>청주시 다른기관 조례</자치법규명><공포일자>20250103</공포일자><공포번호>3</공포번호><제개정구분명>제정</제개정구분명><지자체기관명>충청북도 청원군</지자체기관명><자치법규종류>조례</자치법규종류><시행일자>20250103</시행일자><자치법규상세링크></자치법규상세링크></law>
</OrdinSearch>'''
BODY = '''<?xml version="1.0" encoding="UTF-8"?><LawService><자치법규기본정보><자치법규일련번호>%s</자치법규일련번호><자치법규명>%s</자치법규명><공포일자>20250101</공포일자><시행일자>20250101</시행일자></자치법규기본정보>
<조문><조><조문번호>0</조문번호><조문내용>제1장 총칙</조문내용></조>
<조><조문번호>1</조문번호><조문제목>목적</조문제목><조문내용>제1조(목적) 이 조례는 청주시의 시험을 위하여 필요한 사항을 정함을 목적으로 한다.</조문내용></조>
<조><조문번호>2</조문번호><조문내용>제2조(정의) 이 조례에서 사용하는 용어의 뜻은 다음과 같다.</조문내용><항><항내용>① 첫째 항 내용이다.</항내용><호><호내용>1. 첫째 호</호내용><목><목내용>가. 첫째 목</목내용></목></호></항></조></조문>
<부칙><부칙내용>제1조(시행일) 이 조례는 공포한 날부터 시행한다.</부칙내용></부칙><별표><별표제목>별표 1</별표제목><별표내용>별표 내용 예시 문장입니다 가나다라마바사</별표내용></별표></LawService>'''


class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if 'lawSearch' in self.path:
            out = LIST if q.get('page') == ['1'] else '<OrdinSearch><totalCnt>3</totalCnt></OrdinSearch>'
        else:
            m = q['MST'][0]
            out = BODY % (m, {'100': '청주시 테스트 조례', '200': '청주시 테스트 조례 시행규칙'}.get(m, 'x'))
        self.send_response(200); self.end_headers(); self.wfile.write(out.encode('utf-8'))


class T(unittest.TestCase):
    def test_law_markdown(self):
        body = '<법령><기본정보><법령ID>001</법령ID><법령명_한글>시험법</법령명_한글><소관부처>행정안전부</소관부처><전화번호>044-000-0000</전화번호></기본정보><조문><조문단위><조문번호>1</조문번호><조문여부>전문</조문여부><조문내용>제1장 총칙</조문내용></조문단위><조문단위><조문번호>1</조문번호><조문여부>조문</조문여부><조문내용>제1조(목적) 이 법은 시험을 위하여 필요한 사항을 정함을 목적으로 한다.</조문내용><항><항내용>① 첫째 항이다.</항내용></항></조문단위></조문><부칙><부칙단위><부칙내용>제1조(시행일) 이 법은 공포한 날부터 시행한다.</부칙내용></부칙단위></부칙></법령>'
        meta = {k: '' for k in sync.LAW_LIST_FIELDS}
        meta.update({'법령ID': '001', '법령명한글': '시험법', '법령일련번호': '9', '법령구분명': '법률', '소관부처명': '행정안전부'})
        md, info = sync.law_markdown(body.encode(), meta)
        self.assertIn('## 제1장 총칙', md)
        self.assertIn('제1조(목적)', md)
        self.assertIn('① 첫째 항이다.', md)
        self.assertEqual(info.get('소관부처'), '행정안전부')
        self.assertEqual(sync.norm_name('출자ㆍ출연 기관'), '출자·출연기관')

    def test_markdown(self):
        meta = {'자치법규ID': 'A1', '자치법규일련번호': '100', '자치법규명': '청주시 테스트 조례', '자치법규종류': '조례',
                '지자체기관명': '충청북도 청주시', '공포일자': '20250101', '시행일자': '20250101', '제개정구분명': '일부개정',
                '자치법규상세링크': ''}
        name, md = sync.to_markdown((BODY % ('100', '청주시 테스트 조례')).encode(), meta)
        self.assertIn('## 제1장 총칙', md)
        self.assertIn('제1조(목적)', md)
        self.assertIn('　1. 첫째 호', md)
        self.assertIn('## 부칙', md)
        self.assertIn('## 별표·서식', md)

    def test_pipeline(self):
        srv = http.server.HTTPServer(('127.0.0.1', 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        sync.API = 'http://127.0.0.1:%d/' % srv.server_port
        sync.PAUSE = 0
        tmp = tempfile.mkdtemp()
        sync.ROOT = tmp
        os.environ['LAW_OC'] = 'test'
        self.assertEqual(sync.run('incremental'), 0)
        idx = json.load(open(os.path.join(tmp, 'indexes', 'ordinances.json'), encoding='utf-8'))
        self.assertEqual(sorted(r['id'] for r in idx), ['A1', 'B1'])  # 다른 기관은 제외
        self.assertTrue(os.path.exists(os.path.join(tmp, idx[0]['path'])))
        rep = json.load(open(os.path.join(tmp, 'reports', 'latest-sync.json'), encoding='utf-8'))
        self.assertEqual(len(rep['new']), 2)
        self.assertEqual(sync.run('incremental'), 0)  # 두 번째는 변경 없음
        rep = json.load(open(os.path.join(tmp, 'reports', 'latest-sync.json'), encoding='utf-8'))
        self.assertEqual(rep['new'] + rep['changed'], [])
        srv.shutdown()


if __name__ == '__main__':
    unittest.main()
