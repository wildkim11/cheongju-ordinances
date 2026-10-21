# 청주시 자치법규 (조례·규칙)

청주시 조례와 규칙의 현행 본문을 마크다운으로 보관하는 저장소예요. 법제처 국가법령정보 공동활용 Open API에서 매일 새로 생기거나 개정된 것만 받아 와요. 개정 이력은 커밋 기록으로 남아요.

- `ordinances/조례/`, `ordinances/규칙/`: 자치법규 하나당 마크다운 한 개 (`<자치법규ID>_<이름>.md`)
- `indexes/ordinances.json`: ID·이름·공포일·시행일·제개정 구분·해시·원문 주소
- `manifest.json`, `reports/latest-sync.json`: 마지막 확인 시각과 이번에 바뀐 것, 오류
- 원문은 법제처가 공개한 자료이고, 공식 기록을 대체하지 않아요. 정확한 내용은 법제처 원문(각 파일의 `source`)을 확인하세요.

## 처음 설정 (한 번만)
1. 저장소 Settings → Secrets and variables → Actions → New repository secret
   이름 `LAW_OC`, 값은 법제처 Open API 인증키.
2. Actions 탭 → 왼쪽 「Update ordinances」 → Run workflow → `probe` 선택 → 실행.
   응답이 맞는지만 확인해요. 로그에 「본문 변환 성공」이 나오면 정상이에요.
3. 같은 방법으로 `full`을 한 번 실행하면 전체가 수집돼요(수 분~수십 분).
4. 이후에는 매일 자동으로 돌아요. 실패하면 GitHub가 메일로 알려 줘요.

## 검색 범위 조정 (선택)
- 기본은 이름에 「청주」가 들어간 자치법규를 찾고, 기관명이 「충청북도 청주시」로 시작하는 조례·규칙만 남겨요. 이름에 「청주」가 없는 조례는 빠질 수 있어요.
- 법제처 지자체 기관코드를 알면 Settings → Secrets and variables → Actions → Variables에서 `ORG`(시·도 코드), `SBORG`(시·군·구 코드)를 넣어요. 그러면 이름이 아니라 기관으로 걸러서 찾아요(이때 `QUERIES`는 비워 두세요).
- 검색어를 늘리려면 Variables에 `QUERIES`를 쉼표로 넣어요(예: `청주,위임`).

## 문제가 생기면
- 「인증키(OC) 또는 접속 주소를 확인하지 못했어요」: 인증키가 맞는지, 법제처 신청 때 서버 주소(IP·도메인) 조건이 있었는지 확인하세요.
- 목록이 이전보다 크게 줄면 안전을 위해 멈춰요(기존 자료는 그대로 유지).
- 목록에서 사라진 자치법규는 삭제하지 않고 색인에 `status: absent`로 표시해요(폐지 가능성).

로컬 실행: `LAW_OC=<인증키> python3 scripts/sync.py --mode probe` (Python 3.10 이상, 외부 패키지 없음)
