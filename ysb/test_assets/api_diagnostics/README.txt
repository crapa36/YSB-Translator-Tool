YSB API TEST ASSETS

구성
- images/: OCR / 인페인팅 사전점검용 샘플 원본 이미지 3종
- masks/: 인페인팅 사전점검용 마스크 3종
- meta/: 샘플 문장과 bbox 정보 JSON
- manifest.json: 전체 샘플 요약

추천 배치 위치
1) 개발용 고정 샘플로 둘 경우
   ysb/test_assets/api_diagnostics/
2) 실행 중 임시 복사본을 만들 경우
   <프로젝트 루트>/ysb/test_assets/api_diagnostics/
   또는 런타임 임시폴더(예: CreatorTemp/YSB_API_TEST_ASSETS/)

파일 설명
- *_sample.png
  검은 배경 + 검은 글자 + 흰 테두리
- *_sample_mask.png
  글자/테두리 영역만 흰색(255), 나머지 검은색(0)
  인페인팅 사전점검용 기본 마스크

권장 용도
- OCR 사전점검: images/만 사용
- 번역 사전점검: meta/*.json 의 lines 사용
- 인페인팅 사전점검: images/ + masks/ 함께 사용

English sample is exactly 3 lines: The build passed today, / but the warning log / still looks suspicious.
