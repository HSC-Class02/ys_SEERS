# 씨어스 DART 재무분석 Agent

[![🔗 대시보드 바로가기](https://img.shields.io/badge/%F0%9F%94%97-%EB%8C%80%EC%8B%9C%EB%B3%B4%EB%93%9C%20%EB%B0%94%EB%A1%9C%EA%B0%80%EA%B8%B0-9CCCF2?style=for-the-badge)](https://hsc-class02.github.io/ys_SEERS/)

OpenDART API에서 씨어스 관련 사업·반기·분기보고서의 재무제표 데이터를 수집하고 GitHub Pages 대시보드에 표시합니다.

## 설치
1. https://opendart.fss.or.kr/ 에서 API 인증키를 발급합니다.
2. 저장소 `Settings → Secrets and variables → Actions → New repository secret`에서 이름을 `DART_API_KEY`, 값은 발급받은 키로 설정합니다.
3. `Settings → Actions → General → Workflow permissions`에서 `Read and write permissions`를 허용합니다.
4. ZIP의 모든 파일과 `.github` 폴더를 저장소 루트에 업로드합니다.
5. `Settings → Pages → Build and deployment → Source`를 `GitHub Actions`로 설정합니다.
6. `Actions`에서 `DART data update`를 수동 실행합니다.

## 스케줄
워크플로는 `15 16 1 * *` UTC 기준 실행입니다. 이는 한국시간 기준 매월 2일 01:15이므로, 한국시간 매월 1일 실행이 꼭 필요하면 UTC 기준 `15 16 * * *` 일일 실행으로 변경하는 방법을 권장합니다. GitHub Actions 예약 실행은 지연될 수 있습니다.

## 회사명과 데이터
사용자가 입력한 “씨어스”를 기준으로 DART 법인코드 목록에서 이름을 검색합니다. 법인명 자동 매칭 결과는 `data/company_match.json`에 저장됩니다. 정식 법인명이 다르거나 다른 회사가 선택되면 `src/update_data.py`의 `COMPANY_NAME_CANDIDATES`를 수정하세요. 2010년부터 조회하지만, 회사 설립 전 데이터나 공시되지 않은 데이터는 존재하지 않을 수 있습니다.

## 지표
자산총계, 부채총계, 자본총계, 매출/영업수익, 영업이익, 당기순이익 및 계산 가능한 부채비율·자본비율·영업이익률·순이익률을 표시합니다. 첨부된 별도 재무지표 목록은 확인되지 않아 기본 지표로 구성했습니다. 분기·반기 손익은 누적 기준일 수 있어 연간 값과 직접 비교하지 마세요.

## Peer firms (참고군)
| 기업 | 참고 이유 | 웹사이트 |
|---|---|---|
| 씨어스테크놀로지 | 분석 대상: 웨어러블·원격 환자 모니터링 | https://seers.co.kr/ |
| 아이센스 | 바이오센서·의료기기 | https://www.i-sens.com/ |
| 인바디 | 의료·체성분 측정기기 | https://inbody.com/ |
| 루닛 | 의료 AI·디지털 헬스케어 | https://www.lunit.io/ |
| 오스템임플란트 | 의료기기 제조·판매, 사업 차이 큼 | https://www.osstem.com/ |

비교군은 정성적 참고 목록이며 완전히 동일한 사업모델을 뜻하지 않습니다. 투자 분석 전 사업·회계 구조와 공시 가능성을 확인하세요.

## 오류 해결
- `DART_API_KEY` 오류: Secret 이름과 값 확인
- Pages 404: Pages 소스를 GitHub Actions로 설정하고 배포 워크플로 성공 여부 확인
- `.github/workflows`는 자동화에 필요한 폴더입니다. ZIP에서 숨김 폴더를 생략하지 마세요.
