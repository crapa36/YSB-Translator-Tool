<p align="center">
  <img src="assets/ysb_logo.png" width="220" alt="YSB Tool Logo">
</p>

# 역식붕이 툴

이미지 번역, OCR, 마스킹, 인페인팅, 식질을 한 흐름으로 처리하는 반자동 역식 워크스테이션입니다.

<p align="center">
  <img src="assets/screenshots/ysb_main_screen_readme.png" width="900" alt="YSB Tool v1.5 main screen">
</p>

# YSB-Translator-Tool
Semi-automatic manga translation workstation with OCR, translation, masking, inpainting, and typesetting tools.

## 실행 방법 / Run from source

개발용으로 실행할 때는 프로젝트 루트의 `run_main_v2.0.1.bat`을 실행합니다.
이 BAT는 프로젝트 루트에 `.venv`를 만들거나 기존 `.venv`를 재사용한 뒤 `main.py`를 실행합니다.

```text
YSBTranslator/
- run_main_v2.0.1.bat
- main.py
- ysb/
- requirements_ysik_tool.txt
- .venv/                  # 자동 생성
```

For source execution, run `run_main_v2.0.1.bat` from the project root.
It creates or reuses `.venv` in the project root and starts `main.py`.

## 빌드 방법 / Build

EXE 빌드는 `build_tools/build_exe_v2.0.1.bat`을 실행합니다.
빌드 스크립트는 한 단계 위 폴더를 프로젝트 루트로 인식하고, 루트의 `.venv`를 재사용합니다.

```text
YSBTranslator/
- build_tools/
  - build_exe_v2.0.1.bat
  - version_main.txt
  - version_launcher.txt
- assets/
  - YSB_icon.ico
  - ysb_splash.png
  - ysb_splash_boot.png
```

빌드 결과는 루트의 `dist/` 폴더에 생성됩니다.

```text
dist/
- 역식붕이 툴 v2.0.1.exe
- YSB_Launcher.exe
```

## 폴더 구조 / Source layout

```text
YSBTranslator/
- main.py
- ysb_launcher.py
- run_main_v2.0.1.bat
- requirements_ysik_tool.txt
- assets/
- build_tools/
- ysb/
  - core/
  - engine/
  - i18n/
  - services/
  - settings/
  - ui/
  - utils/
```

`ysb_launcher.py` is the official launcher entry point.
The old `ysb_file_opener.py` path is deprecated and not required in the v2.0.1 layout.

## License

This project is licensed under the GNU General Public License v3.0.  
See the [LICENSE](./LICENSE) file for details.

Because this application uses PyQt6, the open-source distribution of this project is provided under the GPLv3 license.

## Copyright and Branding

© 2026 amule949. All rights reserved.

YSB Translator Tool, 역식붕이 툴, and ZeroStress8 are project names and marks used by amule949.

The GPLv3 license applies to the source code in this repository. It does not grant permission to use the project names, logos, icons, branding materials, or other identity elements in a way that implies official endorsement, authorship, sponsorship, or affiliation.

For more details, see [TRADEMARKS.md](./TRADEMARKS.md).

## 라이선스

이 프로젝트는 GNU General Public License v3.0에 따라 배포됩니다.  
자세한 내용은 [LICENSE](./LICENSE) 파일을 참고하세요.

이 애플리케이션은 PyQt6를 사용하므로, 오픈소스 배포판은 GPLv3 라이선스 기준으로 제공됩니다.

## 저작권 및 프로젝트명 고지

© 2026 amule949. All rights reserved.

YSB Translator Tool, 역식붕이 툴, ZeroStress8은 amule949가 사용하는 프로젝트명 및 표지입니다.

GPLv3 라이선스는 이 저장소의 소스 코드에 적용됩니다. 다만 프로젝트명, 로고, 아이콘, 브랜딩 자료, 기타 식별 요소를 공식 배포판, 공식 제작자, 공식 후원 또는 제휴처럼 오해될 수 있는 방식으로 사용할 권리를 부여하지 않습니다.

자세한 내용은 [TRADEMARKS.md](./TRADEMARKS.md)를 참고하세요.
