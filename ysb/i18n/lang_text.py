# -*- coding: utf-8 -*-
"""
Centralized user-visible text table for YSB Tool.

Rule:
- Put every user-visible fixed string here.
- Program logic, OCR text, translated script, and project data must not be translated here.
- Add Korean and English together when adding a new UI/log/message string.
"""

LANG_KO = "ko"
LANG_EN = "en"


def normalize_language(value=None):
    lang = str(value or LANG_KO).lower()
    if lang.startswith("en"):
        return LANG_EN
    return LANG_KO


def tr_from_table(table, text, lang=LANG_KO, **kwargs):
    text = str(text)
    if normalize_language(lang) == LANG_EN:
        out = table.get(text, text)
    else:
        out = text
    if kwargs:
        try:
            return out.format(**kwargs)
        except Exception:
            return out
    return out


def tr_ui(text, lang=LANG_KO, **kwargs):
    return tr_from_table(UI_KO_EN, text, lang, **kwargs)


def tr_api(text, lang=LANG_KO, **kwargs):
    return tr_from_table(API_TR_KO_EN, text, lang, **kwargs)


def tr_shortcut(text, lang=LANG_KO, **kwargs):
    return tr_from_table(SHORTCUT_TR_KO_EN, text, lang, **kwargs)


UI_KO_EN = {
 '작업 로그': 'Work Log',
 '로그 숨기기': 'Hide Log',
 '로그 열기': 'Open Log',
 '작업 로그를 아래 막대로 접습니다.': 'Collapse the work log to the bottom bar.',
 '숨긴 작업 로그를 다시 엽니다.': 'Open the hidden work log again.',
 '프로젝트 나가기': 'Exit Project',
 '현재 프로젝트를 닫고 홈화면으로 이동합니다.': 'Close the current project and go to the Home screen.',
 '페이지 목록': 'Page List',
 '페이지 없음': 'No pages',
 '프로젝트 생성 위치 없음': 'Project Location Not Found',
 '마지막 프로젝트 생성 위치를 찾을 수 없습니다. 새 생성 위치를 선택해 주세요.': 'Could not find the last project creation location. Please choose a new location.',
 '이미지 없이 YSBT 프로젝트 파일을 먼저 만들고, 나중에 이미지 불러오기로 페이지를 추가합니다.': 'Create the YSBT project file first without images, then add pages later with Import Images.',
 '빈 YSBT 프로젝트를 만들 수 없습니다.': 'Could not create an empty YSBT project.',
'.ysbt 확장자 연결': '.ysbt File Association',
 '.ysbt 확장자 연결 갱신': 'Refresh .ysbt Association',
 '.ysbt 확장자 연결 등록': 'Register .ysbt Association',
 '.ysbt 확장자 연결 등록/갱신 완료': '.ysbt association registered/refreshed.',
 '.ysbt 확장자 연결 등록에 실패했습니다.': 'Failed to register .ysbt file association.',
 '.ysbt 확장자 연결 해제에 실패했습니다.': 'Failed to unregister .ysbt file association.',
 '.ysbt 확장자 연결을 현재 실행 중인 역식붕이 툴로 등록했습니다.\n아이콘 표시는 Windows 아이콘 캐시 때문에 조금 늦게 갱신될 수 있습니다.': '.ysbt file association has '
                                                                                         'been registered to the '
                                                                                         'currently running YSB Tool.\n'
                                                                                         'The icon may take a moment '
                                                                                         'to update due to the Windows '
                                                                                         'icon cache.',
 '.ysbt 확장자 연결이 등록되어 있지 않습니다.\n등록하지 않아도 프로그램 사용은 가능하지만, .ysbt 파일을 더블클릭해서 바로 열 수는 없습니다.\n\n지금 등록할까요?': '.ysbt file '
                                                                                                      'association is '
                                                                                                      'not '
                                                                                                      'registered.\n'
                                                                                                      'You can still '
                                                                                                      'use the program '
                                                                                                      'without '
                                                                                                      'registering it, '
                                                                                                      'but '
                                                                                                      'double-clicking '
                                                                                                      '.ysbt files '
                                                                                                      'will not open '
                                                                                                      'them directly.\n'
                                                                                                      '\n'
                                                                                                      'Register it '
                                                                                                      'now?',
 '.ysbt 확장자가 현재 실행 중인 역식붕이 툴에 이미 연결되어 있습니다.': '.ysbt is already associated with the currently running YSB Tool.',
 '.ysbt 확장자 연결 해제': 'Unregister .ysbt Association',
 '1. 원본': '1. Original',
 '2. 분석도': '2. Analysis',
 '3. 텍스트 마스크': '3. Text Mask',
 '4. 페인팅 마스크': '4. Painting Mask',
 '5. 최종결과': '5. Final Result',
 'AI 번역 API에 함께 전달할 프롬프트를 입력합니다.\n확인을 누르면 옵션 캐시에 저장되고, 닫기를 누르면 저장하지 않고 나갑니다.': 'Enter the prompt to send together with '
                                                                               'the AI translation API.\n'
                                                                               'OK saves it to the options cache. '
                                                                               'Cancel closes without saving.',
 'API 관리': 'API Settings',
 'API 설정 캐시': 'API settings cache',
 'API 설정 캐시 Save complete': 'API settings cache saved',
 'API 설정 캐시 Save 완료': 'API settings cache saved',
 'API 설정 캐시 저장 완료': 'API settings cache saved',
 'API 설정 필요': 'API Settings Required',
 'API 설정이 비어 있거나 잘못되어 엔진을 시작하지 못했습니다.': 'The API settings are empty or invalid, so the engine could not start.',
 'API 키 없음': 'Missing API Key',
 'CLOVA OCR로 재분석': 'Re-analyzing with CLOVA OCR',
 'Custom': 'Custom',
 'Custom 번역 API 설정이 비어있습니다.': 'Custom translation API settings are empty.',
 'English': 'English',
 'Google Vision OCR로 재분석': 'Re-analyzing with Google Vision OCR',
 'JSON 가져오기': 'Import JSON',
 'JSON 파일로 열기': 'Open JSON Project',
 'LaMa inpainting started': 'LaMa inpainting started',
 'Lama inpainting started': 'LaMa inpainting started',
 'Magic Wand Select 되돌림': 'Magic Wand selection undone',
 'Move 모드': 'Move Mode',
 'OFF 페인팅 마스크 없음': 'No OFF painting mask',
 'ON은 분석 기반, OFF는 직접 칠한 마스크를 사용합니다.': 'ON uses the analysis-based mask. OFF uses only manually painted masks.',
 'ON이면 이후 새로 칠하는 브러시가 텍스트보다 위 레이어에 그려집니다.': 'When ON, newly painted brush strokes are drawn above the text layer.',
 'RGB 허용범위': 'RGB Tolerance',
 'Save complete': 'saved',
 'Stable Diffusion inpainting started': 'Stable Diffusion inpainting started',
 'Stable Diffusion 인페인팅 시작': 'Stable Diffusion inpainting started',
 'Stable Diffusion 인페인팅 완료': 'Stable Diffusion inpainting complete',
 'TXT 없음': 'TXT missing',
 'TXT 파일을 다시 읽지 못했습니다:': 'Could not reread the TXT file:',
 'TXT 파일을 읽지 못했습니다:': 'Could not read the TXT file:',
 'YSBT 열기 실패': 'Failed to Open YSBT',
 'YSBT 저장 실패': 'Failed to Save YSBT',
 'YSBT 파일을 저장하지 못했습니다.': 'Could not save the YSBT file.',
 'YSBT 프로젝트 열기': 'Open YSBT Project',
 'YSBT 프로젝트를 열지 못했습니다.': 'Could not open the YSBT project.',
 '[옵션 > API 관리]에서 키를 저장한 뒤 다시 시도해주세요.': 'Save the key in [Options > API Settings] and try again.',
 '[옵션 > API 관리]에서 키를 저장해주세요.': 'Please save the key in [Options > API Settings].',
 '[프로젝트 저장] 또는 [다른 이름으로 저장]을 눌러 .ysbt로 저장하세요.': 'Use [Save Project] or [Save As] to save it as a .ysbt file.',
 '⚡ 분석': '⚡ Analyze',
 '같은 이름의 프리셋이 이미 있습니다.': 'A preset with the same name already exists.',
 '개 삭제': 'items deleted',
 '개별 글꼴 프리셋': 'Item Font Preset',
 '개별 글꼴 프리셋 관리': 'Item Font Presets',
 '개별 글꼴 프리셋 불러오기': 'Load Item Font Preset',
 '개별 번역': 'Translate Current',
 '개별 번역문 불러오기': 'Import Translation Current',
 '개별 분석': 'Analyze Current',
 '개별 인페인팅': 'Inpaint Current',
 '개별 지문 추출': 'Extract Text Current',
 '개별 출력': 'Export Current',
 '개별 텍스트 정리': 'Clean Text Current',
 '개별 프리셋 삭제': 'Delete Item Preset',
 '개별 프리셋 추가': 'Add Item Preset',
 '갱신': 'Refresh',
 '갱신 실패': 'Refresh Failed',
 '갱신 완료': 'Refresh Complete',
 '갱신할 파일 없음': 'No File to Refresh',
 '결과물 출력': 'Export Result',
 '결과물이 비어있습니다.': 'The result is empty.',
 '경로 오류': 'Path Error',
 '관리': 'Manage',
 '구버전 프로젝트 폴더 선택': 'Select Legacy Project Folder',
 '굵게': 'Bold',
 '굵기': 'Bold',
 '글자 수': 'Characters',
 '글자 정렬': 'Text Alignment',
 '기울임': 'Italic',
 '기존 TXT 파일 경로를 찾을 수 없습니다. 다시 불러오기를 해주세요.': 'The existing TXT file path could not be found. Please load it again.',
 '기존 TXT 파일 내용으로 단어장 캐시를 갱신했습니다.': 'Glossary cache has been refreshed from the existing TXT file.',
 '내용': 'Content',
 '너비': 'Width',
 '높이': 'Height',
 '누적': 'total',
 '다른 이름으로 YSBT 저장': 'Save YSBT As',
 '다른 이름으로 저장': 'Save As',
 '다른 이름으로 저장 완료': 'Save As complete',
 '다음 페이지': 'Next Page',
 '다크 테마': 'Dark Theme',
 '단어장': 'Glossary',
 '단어장 TXT 불러오기': 'Load Glossary TXT',
 '단어장 초기화': 'Reset Glossary',
 '단어장을 캐시에 반영했습니다. 닫기를 누르면 유지됩니다.': 'Glossary has been applied to the cache. Close to keep it.',
 '단일 실행 경고': 'Single Instance Warning',
 '단일 실행 서버를 시작하지 못했습니다.\n프로그램은 계속 실행되지만 중복 실행 차단이 정상 동작하지 않을 수 있습니다.': 'Could not start the single-instance server.\n'
                                                                       'The program will continue, but '
                                                                       'duplicate-instance blocking may not work '
                                                                       'correctly.',
 '단축키': 'Shortcut',
 '단축키 통합 관리': 'Shortcut Manager',
 '닫기': 'Cancel',
 '대상': 'Targets',
 '덮어쓰기': 'Overwrite',
 '데이터 없음': 'No data',
 '데이터가 없습니다.': 'No data.',
 '도구': 'Tool',
 '도구:': 'Tool:',
 '도구: Brush': 'Tool: Brush',
 '도구: Eraser': 'Tool: Eraser',
 '도구: Move': 'Tool: Move',
 '도구: Text': 'Tool: Text',
 '되돌리기': 'Undo',
 '되돌림': 'undone',
 '등록 실패': 'Registration Failed',
 '등록 완료': 'Registration Complete',
 '를 삭제할까요?': 'Delete?',
 '마스크 ON/OFF': 'Mask ON/OFF',
 '마스크 되돌림': 'Mask undo',
 '마스크 자동 저장': 'Mask auto-saved',
 '마스킹': 'Masking',
 '마스킹 칠하기': 'Fill Mask',
 '마스킹 칠하기는 텍스트 마스크/페인팅 마스크 탭에서만 가능합니다.': 'Fill Mask is only available in the Text Mask or Painting Mask tab.',
 '마지막 설정': 'Last Settings',
 '매크로 관리': 'Macro Manager',
 '매크로 실행 중': 'Macro Running',
 '먼저 불러오기로 TXT 파일을 선택해주세요.': 'Please load a TXT file first.',
 '먼저 요술봉으로 영역을 선택하세요.': 'Select an area with the Magic Wand first.',
 '먼저 인페인팅된 이미지가 있어야 원본으로 가져올 수 있습니다.': 'An inpainted image is required before it can be used as the source.',
 '모드': 'Mode',
 '묶음': 'Chunk',
 '묶음 수': 'Chunk size',
 '문자 너비': 'Character Width',
 '문자 높이': 'Character Height',
 '문자 색상': 'Text Color',
 '문자색': 'Text Color',
 '밀림 방지를 위해 결과 반영을 중단했습니다.': 'Stopped applying results to prevent shifted translations.',
 '박스 클릭 토글': 'Box click toggle',
 '반영할 배경 이미지가 없습니다.': 'There is no base image to apply the final paint to.',
 '반영할 최종 페인팅이 없습니다.': 'There is no final paint to apply.',
 '번역': 'Translate',
 '번역 개수 불일치': 'Translation count mismatch',
 '번역 건너뜀': 'Translation skipped',
 '번역 엔진': 'Translation engine',
 '번역 오류': 'Translation Error',
 '번역 완료': 'Translation complete',
 '번역 요청 중... (화면이 잠시 멈출 수 있습니다)': 'Requesting translation... (the screen may pause briefly)',
 '번역 중 에러 발생': 'Translation error occurred',
 '번역 참고 자료로 사용할 TXT 파일을 캐시에 저장합니다.\n배경 설명, 단어 해설, 1대1 대체 규칙 등을 넣어둘 수 있습니다.': 'Save a TXT file as translation reference '
                                                                             'material in the cache.\n'
                                                                             'You can include background notes, term '
                                                                             'explanations, and one-to-one replacement '
                                                                             'rules.',
 '번역 프롬프트 입력': 'Translation Prompt',
 '번역AI': 'Translate AI',
 '번역문 TXT 불러오기': 'Load Translation TXT',
 '번역문 내용 지우기': 'Clear Translation Current',
 '번역문 내용 지우기 완료': 'Translations cleared',
 '번역문 불러오기 완료': 'Translation import complete',
 '번역문만': 'Translation Only',
 '번역할 데이터가 없습니다.': 'No data to translate.',
 '변경 사항은 작업 캐시에만 저장됩니다.': 'Changes are saved only to the work cache.',
 '변경 사항이 실제 프로젝트에 바로 저장됩니다.': 'Changes are saved directly to the actual project.',
 '복사할 텍스트가 없습니다.': 'There is no text to copy.',
 '분석': 'Analyze',
 '분석 결과 반영 완료': 'analysis result applied',
 '불러오기': 'Load',
 '불러오기 실패': 'Load Failed',
 '불러오기 완료': 'Load Complete',
 '불러올 텍스트 번호가 없습니다.': 'There are no text IDs to load.',
 '불투명도': 'Opacity',
 '붙여넣은 뒤 실제로 움직인 뒤 클릭하면 붙여넣습니다. ESC로 Canceled.': 'After pasting, move it and click to place it. Press ESC to cancel.',
 '붙여넣은 뒤 실제로 움직인 뒤 클릭하면 붙여넣습니다. ESC로 취소됩니다.': 'After pasting, move it and click to place it. Press ESC to cancel.',
 '붙여넣을 텍스트가 없습니다.': 'There is no text to paste.',
 '브러시': 'Brush',
 '브러시/지우개는 마스크 탭 또는 최종화면에서만 사용할 수 있습니다.': 'Brush/Eraser can only be used in mask tabs or the final screen.',
 '사용': 'Use',
 '사용 선택 이름': 'Use / Select / Name',
 '사용자지정': 'Custom',
 '삭제': 'deleted',
 '삭제 / 번호 재정렬': 'deleted / IDs reordered',
 '삭제하고 번호를 재정렬할까요?': 'Delete and reorder IDs?',
 '삭제할 체크 해제 항목이 없습니다.': 'There are no unchecked items to delete.',
 '삭제할 텍스트가 없습니다.': 'There is no text to delete.',
 '삭제할까요?': 'Delete?',
 '새 Brush를 텍스트 위에 그리기': 'Draw new Brush above text',
 '새 브러시를 텍스트 위에 그리기': 'Draw new brush above text',
 '새 임시 프로젝트 생성': 'New temporary project created',
 '새 텍스트 영역 생성 대기': 'Waiting for new text area',
 '새 텍스트 입력 Canceled': 'New text input canceled',
 '새 텍스트 입력 취소': 'New text input canceled',
 '새 텍스트 추가 완료': 'New text added',
 '새 프로젝트 만들기': 'New Project',
 '새 프로젝트에 넣을 이미지 선택': 'Select Images for New Project',
 '새로 등록할 실행 명령': 'New command to register',
 '선택': 'Select',
 '선택 영역 확장': 'Expand Selection',
 '선택 텍스트': 'Selected Text',
 '선택한 텍스트': 'Selected text',
 '선택한 텍스트 ': 'Selected text ',
 '선택한 텍스트 라인을 삭제할까요?': 'Delete the selected text line?',
 '선택한 폴더에서 원본 이미지 파일명과 같은 TXT 파일을 찾지 못했거나, 맞는 텍스트 번호를 찾지 못했습니다.': 'Could not find TXT files matching the original '
                                                                  'image filenames, or matching text IDs were not '
                                                                  'found.',
 '선택한 폴더의 TXT 번역문을': 'Apply TXT translations from the selected folder to',
 '선택한 행을 삭제할까요?': 'Delete the selected row?',
 '설정 완료': 'Settings Saved',
 '스크립트 저장': 'Script saved',
 '스포이드: Alt+마우스 좌클릭': 'Eyedropper: Alt + left click',
 '시작 완료': 'Ready',
 '식질 실패': 'Typesetting failed',
 '실패': 'failed',
 '실행할까요?': 'Run it?',
 '아직 YSBT 파일로 저장되지 않았습니다.': 'This project has not been saved as a YSBT file yet.',
 '아직 불러온 단어장이 없습니다.': 'No glossary has been loaded yet.',
 '압축 해제 완료 · 인터페이스 로딩 중...': 'Extraction complete · Loading interface...',
 '언어': 'Language',
 '언어 변경': 'Language changed',
 '언어 설정': 'Language Settings',
 '없음': 'None',
 '에러': 'Error',
 '에러가 발생했습니다:': 'An error occurred:',
 '엔진 초기화 실패': 'Engine Initialization Failed',
 '엔진이 아직 준비되지 않았습니다.': 'The engine is not ready yet.',
 '역식붕이 툴 작업 폴더 설정': 'YSB Tool Workspace Folder Settings',
 '연결된 YSBT 파일': 'Linked YSBT file',
 '열 수 있는 프로젝트 파일이 아닙니다.': 'This is not a project file that can be opened.',
 '영역 재분석 중': 're-analyzing selected area',
 '영역 확장 범위': 'Expansion Range',
 '영역확장': 'Expand Area',
 '예:': 'Example:',
 '예: 일본어를 한국어로 자연스럽게 번역해줘. 캐릭터 말투와 줄바꿈을 유지해줘.': 'Example: Translate Japanese into natural Korean. Keep each '
                                                "character's tone and line breaks.",
 '오류': 'Error',
 '오류 발생': 'Error occurred',
 '옵션': 'Options',
 '옵션 > API 관리에서 Base URL, Model, API Key를 입력해주세요.': 'Enter Base URL, Model, and API Key in Options > API Settings.',
 '완료': 'complete',
 '외부 YSBT 파일 열기': 'Open External YSBT File',
 '요술봉': 'Magic Wand',
 '요술봉 RGB 허용범위': 'Magic Wand RGB Tolerance',
 '요술봉 기준 이미지가 없습니다.': 'There is no source image for Magic Wand.',
 '요술봉 선택': 'Magic Wand selection',
 '요술봉 선택 되돌림': 'Magic Wand selection undone',
 '요술봉 선택 실패': 'Magic Wand selection failed',
 '요술봉 선택 영역을 현재 마스크에 칠했습니다.': 'Magic Wand selection has been filled into the current mask.',
 '요술봉 선택 추가': 'Magic Wand selection added',
 '요술봉 영역 확장': 'Magic Wand selection expanded',
 '요술봉 영역확장': 'Magic Wand expansion',
 '요술봉 영역확장 범위': 'Magic Wand Expansion Range',
 '요술봉은 텍스트 마스크/페인팅 마스크 탭에서 사용하세요.': 'Use Magic Wand in the Text Mask or Painting Mask tab.',
 '요술봉은 텍스트 마스크/페인팅 마스크 탭에서만 사용할 수 있습니다.': 'Magic Wand can only be used in the Text Mask or Painting Mask tab.',
 '요청': 'Requested',
 '원문': 'Original',
 '원문+번역문': 'Original + Translation',
 '원문만': 'Original Only',
 '원본 탭의 기준 이미지를 실제 원본으로 되돌렸습니다.': 'The Original tab base image has been restored to the real original image.',
 '원본으로 돌아가기': 'Restore Original Source',
 '은(는) 일괄 작업이 끝난 뒤 다시 시도해 주세요.': 'can be tried again after the batch job finishes.',
 '응답': 'Returned',
 '이 YSBT 파일은 이미 작업 폴더로 가져온 적이 있습니다.\n기존 작업 폴더를 열까요?\n\n[아니오]를 누르면 새 복사본으로 다시 가져옵니다.': 'This YSBT file has already been '
                                                                                      'imported into a workspace.\n'
                                                                                      'Open the existing workspace?\n'
                                                                                      '\n'
                                                                                      'Choose [No] to import it again '
                                                                                      'as a new copy.',
 '이 작업은 Windows의 확장자 연결 정보만 덮어씁니다. 기존 .ysbt 프로젝트 파일은 변경되지 않습니다.': 'This only overwrites the Windows file association. '
                                                                  'Existing .ysbt project files are not changed.',
 '이동': 'Move',
 '이동 예약 완료': 'Workspace Move Scheduled',
 '이름': 'Name',
 '이름 변경 실패': 'Rename Failed',
 '이미 가져온 프로젝트': 'Already Imported Project',
 '이미 등록됨': 'Already Registered',
 '이미 실행 중인 매크로가 있습니다. 현재 매크로가 끝난 뒤 다시 실행해주세요.': 'A macro is already running. Please run it again after the current '
                                                'macro finishes.',
 '이미 일괄 작업이 진행 중입니다.\n현재 작업이 끝난 뒤 다시 실행해 주세요.': 'A batch job is already running.\n'
                                                'Please run it again after the current job finishes.',
 '이미지 변환 실패': 'Image Conversion Failed',
 '이미지 없음': 'No image',
 '이전 페이지': 'Previous Page',
 '인터페이스 로딩 중...': 'Loading interface...',
 '인페인팅': 'Inpaint',
 '인페인팅 건너뜀': 'Inpainting skipped',
 '인페인팅 결과 없음': 'No inpainting result',
 '인페인팅 결과 이미지를 원본 탭에 표시할 수 없습니다.': 'Could not display the inpaint result image on the Original tab.',
 '인페인팅 결과 해상도 보정': 'Inpaint result size normalized',
 '인페인팅 결과를 원본 탭의 작업중 기준 이미지로 가져왔습니다.': 'Inpaint result has been imported as the working source image for the Original '
                                       'tab.',
 '인페인팅 마스크 해상도 보정': 'Inpaint mask size normalized',
 '인페인팅 서버에서 응답이 없습니다. (API 토큰/모델 설정 확인 필요)': 'No response from the inpainting server. Check API token/model settings.',
 '인페인팅 시작': 'Inpainting started',
 '인페인팅 완료': 'Inpainting complete',
 '인페인팅 입력': 'Inpainting input',
 '인페인팅을 먼저 해주세요.': 'Please run inpainting first.',
 '인페인팅을 원본으로': 'Use Inpainted as Source',
 '일괄': 'Batch',
 '일괄 analyze 완료!': 'Batch analyze complete!',
 '일괄 inpaint 완료!': 'Batch inpaint complete!',
 '일괄 translate 완료!': 'Batch translate complete!',
 '일괄 번역': 'Batch Translate',
 '일괄 번역문 TXT 폴더 선택': 'Select Batch Translation TXT Folder',
 '일괄 번역문 내용 지우기': 'Batch Clear Translation',
 '일괄 번역문 내용 지우기 완료': 'Batch translations cleared',
 '일괄 번역문 불러오기': 'Batch Import Translation',
 '일괄 번역문 불러오기 완료': 'Batch translation import complete',
 '일괄 분석': 'Batch Analyze',
 '일괄 불러오기 실패': 'Batch Import Failed',
 '일괄 인페인팅': 'Batch Inpaint',
 '일괄 자동 줄 내림': 'Batch Auto Line Break',
 '일괄 자동 줄 내림 완료': 'Batch Auto Line Break complete',
 '일괄 자동 텍스트 크기 조정': 'Batch Auto Text Size',
 '일괄 자동 텍스트 크기 조정 완료': 'Batch Auto Text Size complete',
 '일괄 작업': 'Batch Work',
 '일괄 작업 중': 'Batch Work Running',
 '일괄 작업 중 차단됨': 'Blocked during batch work',
 '일괄 작업 중에는 프로그램을 종료할 수 없습니다.\n작업이 끝난 뒤 다시 종료해 주세요.': 'The program cannot be closed during batch work.\n'
                                                      'Please close it after the current work finishes.',
 '일괄 정리할 체크 해제 항목이 없습니다.': 'There are no unchecked items to clean in batch.',
 '일괄 지문 추출': 'Batch Extract Text',
 '일괄 지문 추출 완료': 'Batch text extraction complete',
 '일괄 지문 추출 취소': 'Batch extract text canceled',
 '일괄 출력': 'Batch Export',
 '일괄 텍스트 갱신': 'Batch Text Refresh',
 '일괄 텍스트 정리': 'Batch Clean Text',
 '일괄 텍스트 정리 완료': 'Batch text cleanup complete',
 '임시 프로젝트 삭제': 'Temporary project deleted',
 '임시 프로젝트를 작업 폴더로 승격': 'Temporary project promoted to workspace',
 '임시 프로젝트를 작업 폴더로 옮기지 못했습니다.': 'Could not move the temporary project to the workspace folder.',
 '자간': 'Letter',
 '자동': 'Auto',
 '자동 줄 내림': 'Auto Line Break',
 '자동 줄 내림 완료': 'Auto Line Break complete',
 '자동 줄 내림을': 'Run Auto Line Break on',
 '자동 텍스트 크기 조정': 'Auto Text Size',
 '자동 텍스트 크기 조정 완료': 'Auto Text Size complete',
 '자동 텍스트 크기 조정을': 'Run Auto Text Size on',
 '자동저장 모드': 'Auto Save Mode',
 '자동저장 모드 OFF': 'Auto Save Mode OFF',
 '자동저장 모드 OFF: 변경 사항은 작업 캐시에만 저장됩니다.': 'Auto Save Mode OFF: changes are saved only to the work cache.',
 '자동저장 모드 ON': 'Auto Save Mode ON',
 '자동저장 모드 ON: 변경 사항이 실제 프로젝트에 바로 저장됩니다.': 'Auto Save Mode ON: changes are saved directly to the actual project.',
 '자동저장 전환': 'Switch Auto Save',
 '자동화 작업': 'Automation',
 '작업': 'Work',
 '작업 세션 시작': 'Work session started',
 '작업 취소': 'Undo',
 '작업 재실행': 'Redo',
 '되돌릴 수 있는 작업이 있으면 이전 상태로 돌아갑니다.': 'Return to the previous state when an undoable action exists.',
 '되돌린 작업을 다시 적용합니다.': 'Reapply the last undone action.',
 '다시 실행할 내역이 없습니다.': 'There is no action to redo.',
 '작업 캐시 시작': 'Work cache started',
 '작업 폴더 경로가 올바르지 않습니다.': 'The workspace folder path is invalid.',
 '작업 폴더 설정': 'Workspace Folder Settings',
 '작업 폴더 설정 변경 취소': 'Workspace folder settings change canceled',
 '작업 폴더 설정 확인': 'Workspace folder settings confirmed',
 '작업 폴더 설정을 저장하지 못했습니다.': 'Failed to save workspace folder settings.',
 '작업 폴더 설정을 저장했습니다.': 'Workspace folder settings have been saved.',
 '작업 폴더 위치': 'Workspace Folder',
 '작업 폴더 위치 변경': 'Change Workspace Folder',
 '작업 폴더 위치 변경이 예약되었습니다.\n프로그램을 재실행하면 아래 위치로 이동됩니다.': 'Workspace folder change has been scheduled.\n'
                                                     'Restart the program to move it to the location below.',
 '작업 폴더를 설정했습니다.': 'Workspace folder has been set.',
 '작업탭 변경': 'Change Work Tab',
 '재분석': 'Re-analyze',
 '저장': 'Save',
 '저장 실패': 'Save Failed',
 '저장 안 함': "Don't Save",
 '저장 완료': 'saved',
 '저장 위치': 'Save location',
 '저장된 단어장 캐시를 지울까요?': 'Clear the saved glossary cache?',
 '저장된 작업 폴더 경로를 읽을 수 없습니다.\n작업 폴더 위치를 다시 지정해 주세요.': 'The saved workspace folder path could not be read.\n'
                                                    'Please select the workspace folder again.',
 '저장된 작업 폴더를 찾을 수 없습니다.\n작업 폴더 위치를 다시 지정해 주세요.': 'The saved workspace folder could not be found.\n'
                                                 'Please select the workspace folder again.',
 '저장하지 않은 작업': 'Unsaved Work',
 '저장하지 않은 작업이 있습니다.': 'There are unsaved changes.',
 '저장하지 않은 작업이 있습니다.\n현재 작업 캐시를 프로젝트에 저장하고 자동저장 모드로 전환할까요?': 'There are unsaved changes.\n'
                                                            'Save the current work cache to the project and switch to '
                                                            'Auto Save Mode?',
 '저장할 이미지/프로젝트가 없습니다.': 'There are no images or project data to save.',
 '전체 마스크': 'full mask',
 '전체 분석 시작': 'full analysis started',
 '전체 선택': 'Select All',
 '전체 적용': 'Apply All',
 '전체 체크 상태 자동 갱신': 'All check states auto-refreshed',
 '전체 페이지에 적용': 'Apply to All Pages',
 '전체 페이지에서': 'Across all pages',
 '정렬': 'Alignment',
 '제거 항목': 'Removed items',
 '제거할 연결 항목이 없었습니다.': 'No association entries were found to remove.',
 '종료 오류': 'Close Error',
 '종료하기 전에 프로젝트를 저장할까요?': 'Save the project before exiting?',
 '지문 추출': 'Extract Text',
 '지문 추출 TXT를': 'Create text extraction TXT files for',
 '지문 추출 완료': 'Text extraction complete',
 '지우개': 'Eraser',
 '지울 번역문이 없습니다.': 'There are no translations to clear.',
 '지원 안내': 'Not Supported',
 '찾아보기': 'Browse',
 '처음 실행입니다.\n작업 폴더 위치를 확인해 주세요.': 'First run.\nPlease confirm the workspace folder location.',
 '체크 상태 자동 갱신': 'Check state auto-refreshed',
 '체크 해제된 텍스트': 'unchecked text items',
 '체크된 번역 대상이 없습니다.': 'No checked translation targets.',
 '체크된 항목 없음': 'No checked items',
 '체크한 옵션만 프리셋에 포함됩니다. 이 창의 미리보기는 단일 텍스트 도구입니다.': 'Only checked options are included in the preset. This preview uses a '
                                                 'single text tool.',
 '체크한 옵션만 프리셋에 포함됩니다. 이 창의 미리보기는 닫을 때 원래대로 복구됩니다.': 'Only checked options are included in the preset. This preview is '
                                                    'restored when the window closes.',
 '초기화': 'Reset',
 '총': 'total',
 '최종 브러시 불투명도': 'Final brush opacity',
 '최종 브러시 불투명도 감소': 'Decrease Final Brush Opacity',
 '최종 브러시 불투명도 증가': 'Increase Final Brush Opacity',
 '최종 이미지 저장': 'Final image saved',
 '최종 텍스트 도구': 'Final Text Tool',
 '최종 페인팅 Auto Save': 'Final paint auto-saved',
 '최종 페인팅 색상': 'Final paint color',
 '최종 페인팅 자동 저장': 'Final paint auto-saved',
 '최종 페인팅을 배경으로 반영': 'Apply Final Paint to Background',
 '최종 페인팅을 원본 탭 기준 이미지로 반영했습니다.': 'Final paint has been applied to the Original tab base image.',
 '최종화면 브러시 색상의 알파값을 조절합니다.': 'Adjusts the alpha value of final-screen brush color.',
 '최종화면에서만 사용할 수 있습니다.': 'This can only be used on the final screen.',
 '최종화면을 클릭하면 텍스트 영역을 만듭니다. 내용 작성 후 Ctrl+Return을 누르거나 다른 곳을 클릭하면 작성이 완료됩니다.': 'Click the final screen to create a text '
                                                                             'area. After writing, press Ctrl+Return '
                                                                             'or click elsewhere to finish editing.',
 '추가할 프리셋 이름:': 'Preset name to add:',
 '추출할 내용:': 'Content to extract:',
 '출력': 'Export',
 '취소': 'Canceled',
 '취소됨': 'Canceled',
 '취소선': 'Strikethrough',
 '칠했습니다': 'filled',
 '캐시에만 저장됨': 'Saved in cache only',
 '크기': 'Size',
 '테마 변경': 'Theme changed',
 '테마 설정': 'Theme Settings',
 '텍스트': 'Text',
 '텍스트 Refresh Complete': 'Text refresh complete',
 '텍스트 갱신': 'Text refresh',
 '텍스트 갱신 완료': 'Text refresh complete',
 '텍스트 넘버 크기 변경': 'Change Text Number Size',
 '텍스트 도구': 'Text Tool',
 '텍스트 도구는 최종화면에서만 사용할 수 있습니다.': 'Text Tool can only be used on the final screen.',
 '텍스트 마스크 자동 저장': 'Text mask auto-saved',
 '텍스트 마스크 재분석': 'Text Mask Re-analyze',
 '텍스트 마스크 재분석은 텍스트 마스크 탭에서만 사용할 수 있습니다.': 'Text mask re-analysis is only available in the Text Mask tab.',
 '텍스트 박스가 없어서 번역할 게 없습니다.': 'No text boxes to translate.',
 '텍스트 변형': 'Text Transform',
 '텍스트 변형 모드 OFF': 'Text transform mode OFF',
 '텍스트 변형 모드 ON': 'Text transform mode ON',
 '텍스트 변형 모드 종료': 'Text transform mode ended',
 '텍스트 변형 적용': 'Text transform applied',
 '텍스트 복사 완료': 'Text copy complete',
 '텍스트 붙여넣기': 'Paste Text',
 '텍스트 붙여넣기 완료': 'Paste text complete',
 '텍스트 붙여넣기 위치 지정': 'Set paste text position',
 '텍스트 붙여넣기는 최종화면에서만 사용할 수 있습니다.': 'Paste Text can only be used on the final screen.',
 '텍스트 삭제': 'Delete Text',
 '텍스트 삭제 완료': 'Text deletion complete',
 '텍스트 영역/비율 조정': 'Text area/scale adjustment',
 '텍스트 영역/비율 조정 Undo': 'Text area/scale undo',
 '텍스트 위 페인팅 ON/OFF': 'Paint Above Text ON/OFF',
 '텍스트 위 페인팅 출력 합성 실패': 'Failed to composite paint-above-text output',
 '텍스트 위에 페인팅': 'Paint Above Text',
 '텍스트 이동': 'Text Move',
 '텍스트 이동 적용': 'Text move applied',
 '텍스트 이동됨': 'Text moved',
 '텍스트 정리': 'Clean Text',
 '텍스트 정리 완료': 'Text cleanup complete',
 '텍스트 직접 수정 변화 없음': 'No direct text edit changes',
 '텍스트 직접 수정 완료': 'Direct text edit complete',
 '텍스트 직접 수정 취소': 'Direct text edit canceled',
 '텍스트 직접 편집 시작': 'Direct text edit started',
 '텍스트 표시': 'Show Text',
 '텍스트 표시 ON/OFF': 'Show Text ON/OFF',
 '텍스트 회전': 'Text Rotation',
 '텍스트 회전 각도 지정': 'Text rotation angle set',
 '파란 테두리/핸들을 조작하세요. Alt+드래그로 이동, Ctrl+Enter 또는 배경 클릭으로 종료': 'Use the blue border/handles. Alt+drag to move. Press '
                                                            'Ctrl+Enter or click the background to finish.',
 '파일 없음': 'No files',
 '파일이 필요합니다.': 'file.',
 '페이지': 'Page',
 '페이지 /': 'page(s) /',
 '페이지 글꼴 프리셋 관리': 'Page Font Presets',
 '페이지 글꼴 프리셋 불러오기': 'Load Page Font Preset',
 '페이지 기준으로 생성합니다.': 'page(s).',
 '페이지 이동': 'Go to Page',
 '페이지 적용': 'Apply Page',
 '페이지 프리셋 추가': 'Add Page Preset',
 '페이지라면': 'page requires',
 '페이지에 적용합니다.': 'pages.',
 '페인팅 마스크 ON/OFF': 'Painting Mask ON/OFF',
 '페인팅 마스크 자동 저장': 'Painting mask auto-saved',
 '페인팅 마스크 저장됨': 'Painting mask saved',
 '페인팅 마스크 토글': 'Painting mask toggle',
 '페인팅 마스크 토글: OFF': 'Painting mask toggle: OFF',
 '페인팅 마스크 토글: ON': 'Painting mask toggle: ON',
 '포함/내용': 'Included / Content',
 '폰트': 'Font',
 '표시 언어를 선택하세요.\n확인을 누르면 즉시 적용되고, 닫기를 누르면 변경하지 않습니다.': 'Select the display language.\n'
                                                       'OK applies it immediately. Cancel leaves it unchanged.',
 '프로그램 종료 처리 중 오류가 발생했습니다.\n작업 보호를 위해 종료를 취소합니다.': 'An error occurred while closing the program.\n'
                                                   'Closing has been canceled to protect your work.',
 '프로젝트': 'Project',
 '프로젝트 JSON 열기': 'Open Project JSON',
 '프로젝트 없음': 'No Project',
 '열려고 하는 파일:': 'File to open:',
 '현재 열려있는 프로젝트를 닫고 새 프로젝트를 열까요?\n\n[예] 기존 프로젝트를 닫고 새 프로젝트를 엽니다.\n[아니오] 열기를 취소합니다.': 'Close the currently open project and open the new project?\n\n[Yes] Close the current project and open the new project.\n[No] Cancel opening.',
 '프로젝트 열기': 'Open Project',
 '최종 페인팅 실행 Canceled': 'Final paint action canceled',
 '실행 Canceled': 'Action canceled',
 '실행 Canceled할 내역이 없습니다.': 'There is no action to undo.',
 'Select 해제': 'Selection cleared',
 '프로젝트 열림': 'Project opened',
 '프로젝트 이동 실패': 'Project Move Failed',
 '프로젝트 저장': 'Project saved',
 '프로젝트 저장 완료': 'Project save complete',
 '프로젝트가 없습니다. 새 프로젝트를 먼저 만들어주세요.': 'No project. Please create a new project first.',
 '프로젝트는 작업 폴더에 저장했지만, YSBT 파일 저장에 실패했습니다.': 'The project was saved to the workspace folder, but saving the YSBT file '
                                            'failed.',
 '프로젝트에 넣을 이미지 선택': 'Select Images for Project',
 '프리셋 JSON을 읽지 못했습니다.': 'Could not read the preset JSON file.',
 '프리셋 삭제': 'Delete Preset',
 '프리셋 이름': 'Preset Name',
 '프리셋 이름:': 'Preset name:',
 '프리셋 저장': 'Save Preset',
 '프리셋에 포함할 옵션': 'Options to include in preset',
 '프리셋을 삭제할까요?': 'Delete this preset?',
 '프리셋이 이미 있습니다. 덮어쓸까요?': 'This preset already exists. Overwrite it?',
 '한 번의 API 요청에 묶어서 보낼 텍스트 줄 수': 'Number of text items sent in one API request',
 '한국어': 'Korean',
 '해당 영역의 마스크도 함께 지워집니다.': 'The mask for that area will also be cleared.',
 '해당 텍스트 영역의 마스크도 함께 지워집니다.': 'The masks for those text areas will also be cleared.',
 '해제 실패': 'Unregistration Failed',
 '해제 완료': 'Unregistration Complete',
 '행 삭제': 'Delete Row',
 '행간': 'Line',
 '허용범위': 'tolerance',
 '현재 .ysbt 확장자가 다른 위치의 역식붕이 툴에 연결되어 있습니다.': '.ysbt is currently associated with YSB Tool in another location.',
 '현재 단어장': 'Current glossary',
 '현재 등록된 실행 명령': 'Current registered command',
 '현재 마스크': 'current mask',
 '현재 사용자 계정에 .ysbt 확장자 연결을 등록합니다.\n등록 후 .ysbt 파일을 더블클릭하면 역식붕이 툴로 열립니다. 계속할까요?': 'Register .ysbt file association for '
                                                                                'the current Windows user account.\n'
                                                                                'After registration, double-clicking a '
                                                                                '.ysbt file opens it with YSB Tool. '
                                                                                'Continue?',
 '현재 사용자 계정의 .ysbt 연결을 해제합니다.\n이전 테스트 버전에서 이 프로그램이 등록한 .ysb 연결도 함께 정리합니다.\n다른 프로그램에 연결된 .ysb는 변경하지 않습니다.\n\n계속할까요?': 'This '
                                                                                                                     'will '
                                                                                                                     'unregister '
                                                                                                                     'the '
                                                                                                                     '.ysbt '
                                                                                                                     'association '
                                                                                                                     'for '
                                                                                                                     'the '
                                                                                                                     'current '
                                                                                                                     'Windows '
                                                                                                                     'user '
                                                                                                                     'account.\n'
                                                                                                                     'It '
                                                                                                                     'will '
                                                                                                                     'also '
                                                                                                                     'clean '
                                                                                                                     'up '
                                                                                                                     'any '
                                                                                                                     '.ysb '
                                                                                                                     'association '
                                                                                                                     'registered '
                                                                                                                     'by '
                                                                                                                     'earlier '
                                                                                                                     'test '
                                                                                                                     'versions '
                                                                                                                     'of '
                                                                                                                     'this '
                                                                                                                     'program.\n'
                                                                                                                     '.ysb '
                                                                                                                     'associations '
                                                                                                                     'owned '
                                                                                                                     'by '
                                                                                                                     'other '
                                                                                                                     'programs '
                                                                                                                     'will '
                                                                                                                     'not '
                                                                                                                     'be '
                                                                                                                     'changed.\n'
                                                                                                                     '\n'
                                                                                                                     'Continue?',
 '현재 설정을 새 개별 프리셋으로 추가': 'Add Current Settings as New Item Preset',
 '현재 스타일을 새 프리셋으로 추가': 'Add Current Style as New Preset',
 '현재 실행 중인 프로그램으로 연결을 갱신할까요?': 'Refresh the association to the currently running program?',
 '현재 일괄 작업이 진행 중입니다.': 'A batch job is currently running.',
 '현재 탭에 마스크 레이어가 없습니다.': 'There is no mask layer in the current tab.',
 '현재 페이지': 'current page',
 '현재 페이지 텍스트 번호와 맞는 번역문을 찾지 못했습니다.': 'Could not find translations matching the current page text IDs.',
 '현재 페이지에 적용': 'Apply to Current Page',
 '현재 프로젝트를 닫기 전에 저장할까요?': 'Save before closing the current project?',
 '화면 구성 마무리 중...': 'Finishing interface setup...',
 '화면에 적용할 테마를 선택하세요.\n확인을 누르면 즉시 적용되고, 닫기를 누르면 변경하지 않습니다.': 'Select the theme to apply.\n'
                                                            'OK applies it immediately. Cancel leaves it unchanged.',
 '화이트 테마': 'Light Theme',
 '확인': 'OK',
 '확장 범위': 'Expand Range',
 '확장자 연결 해제': 'Unregister File Association',
 '확장자 연결 해제는 Windows에서만 지원합니다.': 'File association unregistering is only supported on Windows.',
 '확장자 연결 해제를 완료했습니다.': 'File association has been unregistered.',
 '확장자 연결 해제에 실패했습니다.': 'Failed to unregister file association.',
 '환경 준비 중...': 'Preparing environment...',
 '회색': 'Gray',
 '회전 각도(도):': 'Rotation angle (degrees):',
 '획': 'Stroke',
 '획 색상': 'Stroke Color',
 '획색': 'Stroke Color',
 '🌐 번역': '🌐 Translate',
 '🎨 인페인팅': '🎨 Inpaint',
 '📤 결과물 출력': '📤 Export Result',
 '🔄 재분석': '🔄 Re-analyze',
 '🧹 텍스트 정리': '🧹 Clean Text'}



# v1.8.0 launcher/start screen strings
UI_KO_EN.update({
    '시작 화면': 'Start Screen',
    '최근 프로젝트': 'Recent Projects',
    '새로 만들기': 'New',
    'JSON으로 열기': 'Open as JSON',
    '저장하기': 'Save',
    '다른 이름으로 저장하기': 'Save As',
    '복구하기': 'Recover',
    '홈화면으로 가기': 'Go to Home Screen',
    '새 프로젝트 만들기': 'New Project',
    '프로젝트 열기': 'Open Project',
    '마지막 작업 복구': 'Recover Last Work',
    '클라우드 설정 백업': 'Cloud Settings Backup',
    '클라우드에서 설정 불러오기': 'Restore Settings from Cloud',
    '옵션 / 설정': 'Options / Settings',
    '도움말 / 매뉴얼': 'Help / Manual',
    '프로젝트는 YSBT로 보존하고, 작업환경은 설정 캐시로 이어갑니다.': 'Projects are preserved as YSBT files, and your work environment continues through settings cache.',
    '최근 프로젝트는 로컬 경로를 기본 화면에 직접 노출하지 않습니다.': 'Local paths are not shown directly on the main recent-project screen.',
    '아직 최근 프로젝트가 없습니다. 왼쪽에서 새 프로젝트를 만들거나 기존 YSBT를 열어주세요.': 'No recent projects yet. Create a new project or open an existing YSBT from the left.',
    '썸네일 없음': 'No Thumbnail',
    '제목 없음': 'Untitled',
    '마지막 열기': 'Last opened',
    '페이지': ' pages',
    '로컬 있음': 'Local file available',
    '파일을 찾을 수 없음': 'File not found',
    '열기': 'Open',
    '폴더 위치 열기': 'Open Folder Location',
    '최근 목록에서 제거': 'Remove from Recent List',
    '준비 중': 'Coming Soon',
    '클라우드 설정 백업은 다음 단계에서 연결됩니다. 현재 런처에는 진입점만 준비되어 있습니다.': 'Cloud settings backup will be connected in the next stage. The launcher currently provides the entry point only.',
    '런처 화면에서는 새 프로젝트, 프로젝트 열기, 마지막 작업 복구, 최근 프로젝트 열기를 바로 사용할 수 있습니다.': 'From the launcher, you can create a new project, open a project, recover the last work, or reopen recent projects directly.',
    '폴더 열기 실패': 'Failed to Open Folder',
})



# v1.8.0 launcher/settings overview strings
UI_KO_EN.update({
    '설정': 'Settings',
    '설정 / 옵션': 'Settings / Options',
    '작업 폴더 위치': 'Workspace Folder Location',
    'YSBT 파일 연결': 'YSBT File Association',
    '설정은 프로그램 환경, 옵션은 작업 기능 관리 항목입니다. 자주 쓰는 설정은 이 창에서 바로 바꾸고, 복잡한 항목은 관리 버튼으로 엽니다.': 'Settings are program environment items, while options manage work features. Frequently used settings can be changed here, and complex items open their dedicated management windows.',
    '프로그램의 기본 동작, 표시 방식, 작업 폴더, 임시 파일, YSBT 연결처럼 환경에 가까운 항목입니다.': 'Environment-level items such as basic behavior, display, workspace folder, temporary files, and YSBT association.',
    'API, 프롬프트, 단어장, 단축키, 매크로, 프리셋처럼 작업 기능을 관리하는 항목입니다. 복잡한 항목은 기존 전용 창으로 엽니다.': 'Work-feature items such as APIs, prompts, glossary, shortcuts, macros, and presets. Complex items open their existing dedicated windows.',
    'ON이면 변경 사항이 실제 프로젝트에 바로 저장되고, OFF이면 작업 캐시에만 저장됩니다.': 'When ON, changes are saved directly to the real project. When OFF, changes are saved only to the work cache.',
    '창과 작업 화면의 밝기 테마를 바꿉니다.': 'Changes the brightness theme of the window and work area.',
    '사용자 인터페이스 표시 언어를 바꿉니다.': 'Changes the user interface display language.',
    '프로젝트 작업 폴더와 캐시가 저장되는 기준 위치입니다.': 'The base location where project work folders and caches are saved.',
    '임시 작업 폴더 자동 삭제 주기를 정하고, 필요하면 즉시 삭제합니다.': 'Sets the auto-delete interval for temporary work folders and can delete them immediately if needed.',
    '.ysbt 파일을 더블클릭했을 때 역식붕이 툴로 바로 열리게 합니다.': 'Allows .ysbt files to open directly in YSB Tool when double-clicked.',
    '.ysbt 확장자 연결 해제': 'Unregister .ysbt Association',
})



# v2.0.0 추가 메뉴/작업 문구 번역 보강
UI_KO_EN.update({
    '페이지 탭 표시명 설정': 'Page Tab Display Name Settings',
    '출력 표시명 설정': 'Output Display Name Settings',
    '출력물 삭제': 'Delete Outputs',
    '클라우드 백업 삭제': 'Delete Cloud Backup',
    '전체 이미지탭 삭제': 'Delete All Image Tabs',
    '현재 페이지 이름 보기': 'Show Current Page Name',
    '페이지 탭 파일명 변경': 'Rename Page Tab File Name',
    '현재 페이지 원본 파일명 변경': 'Rename Current Page Source File',
    '현재 이미지탭 삭제': 'Delete Current Image Tab',
    '현재 텍스트 기준 영역 재설정': 'Reset Current Text Reference Area',
    '일괄 텍스트 기준 영역 재설정': 'Batch Reset Text Reference Area',
    '번역 내용 지우기 완료': 'Translation cleared',
    '일괄 번역문 내용 지우기 완료': 'Batch translations cleared',
    '출력물 삭제 확인': 'Confirm Delete Outputs',
    '선택한 출력물을 삭제할까요?': 'Delete the selected outputs?',
    '삭제할 출력물이 없습니다.': 'There are no outputs to delete.',
    '먼저 프로젝트를 열어주세요.': 'Please open a project first.',
    '일부 파일을 삭제하지 못했습니다.': 'Some files could not be deleted.',
    '최종결과 이미지': 'Final Result Images',
    '포토샵 스크립트': 'Photoshop Scripts',
    'TXT 지문': 'TXT Text Extracts',
})

# Reverse lookup table for restoring simple fixed UI strings when switching back to Korean.
# Values are generated from UI_KO_EN after the table is fully declared.
UI_EN_KO = {en: ko for ko, en in UI_KO_EN.items()}

API_TR_KO_EN = {'API 관리': 'API Settings',
 'API 정보는 사용자 설정 캐시 파일에 저장됩니다.\nOCR / 인페인팅 / 번역 API는 분류별로 하나씩 선택해 사용합니다.\n캐시 위치: ': 'API settings are saved to the '
                                                                                    'user settings cache file.\n'
                                                                                    'Select one provider for each '
                                                                                    'category: OCR / Inpainting / '
                                                                                    'Translation.\n'
                                                                                    'Cache path: ',
 'Custom / OpenAI-Compatible': 'Custom / OpenAI-Compatible',
 'JSON 파일 선택': 'Select JSON File',
 'OpenAI Chat Completions 호환 API만 사용할 수 있습니다. Base URL, Model, API Key를 입력하세요.': 'Only OpenAI Chat Completions '
                                                                                 'compatible APIs are supported. Enter '
                                                                                 'Base URL, Model, and API Key.',
 'OpenAI Chat Completions 호환 API만 사용할 수 있습니다. Base URL, Model, API Key를 입력하세요.\n호환 예시: OpenRouter, Groq, xAI Grok, Together, LM Studio, vLLM, Ollama OpenAI 호환 서버': 'Only '
                                                                                                                                                                    'OpenAI '
                                                                                                                                                                    'Chat '
                                                                                                                                                                    'Completions '
                                                                                                                                                                    'compatible '
                                                                                                                                                                    'APIs '
                                                                                                                                                                    'are '
                                                                                                                                                                    'supported. '
                                                                                                                                                                    'Enter '
                                                                                                                                                                    'Base '
                                                                                                                                                                    'URL, '
                                                                                                                                                                    'Model, '
                                                                                                                                                                    'and '
                                                                                                                                                                    'API '
                                                                                                                                                                    'Key.\n'
                                                                                                                                                                    'Compatible '
                                                                                                                                                                    'examples: '
                                                                                                                                                                    'OpenRouter, '
                                                                                                                                                                    'Groq, '
                                                                                                                                                                    'xAI '
                                                                                                                                                                    'Grok, '
                                                                                                                                                                    'Together, '
                                                                                                                                                                    'LM '
                                                                                                                                                                    'Studio, '
                                                                                                                                                                    'vLLM, '
                                                                                                                                                                    'Ollama '
                                                                                                                                                                    'OpenAI-compatible '
                                                                                                                                                                    'servers',
 '닫기': 'Cancel',
 '번역 API': 'Translation API',
 '이': 'this',
 '인페인팅 API': 'Inpainting API',
 '입력칸 비우기': 'Clear Fields',
 '입력칸을 전부 비울까요?': 'Clear all input fields?',
 '제공자를 사용합니다.': 'provider will be used.',
 '찾아보기': 'Browse',
 '키 보이기': 'Show Keys',
 '호환 예시: OpenRouter, Groq, xAI Grok, Together, LM Studio, vLLM, Ollama OpenAI 호환 서버': 'Compatible examples: '
                                                                                      'OpenRouter, Groq, xAI Grok, '
                                                                                      'Together, LM Studio, vLLM, '
                                                                                      'Ollama OpenAI-compatible '
                                                                                      'servers',
 '확인': 'OK'}

API_TR_KO_EN.update({
    "OCR / 인페인팅 / 번역 API를 분류별로 선택하고, 외부 API 주소·키·모델명을 관리합니다.\n확인을 누르면 사용자 설정 캐시에 저장되고, 닫기를 누르면 저장하지 않습니다.": "Select OCR / inpainting / translation APIs by category, and manage external API URLs, keys, and model names.\nOK saves them to the user settings cache. Cancel closes without saving.",
    "캐시 위치: ": "Cache path: ",
    "이미지의 글자를 읽어올 OCR 제공자를 선택합니다. 선택한 제공자 한 개만 분석 작업에 사용됩니다.": "Choose the OCR provider used to read text from images. Only the selected provider is used for analysis.",
    "마스크 영역의 배경을 복원할 인페인팅 제공자를 선택합니다. 선택한 제공자 한 개만 인페인팅 작업에 사용됩니다.": "Choose the inpainting provider used to restore the background inside mask areas. Only the selected provider is used for inpainting.",
    "AI 번역에 사용할 번역 제공자를 선택합니다. 선택한 제공자 한 개만 번역 작업에 사용됩니다.": "Choose the translation provider used for AI translation. Only the selected provider is used for translation.",
    "Model": "Model",
    "Invoke URL": "Invoke URL",
    "Secret Key": "Secret Key",
    "Model / Mode": "Model / Mode",
    "API Key": "API Key",
    "Language Hints": "Language Hints",
    "Prompt": "Prompt",
    "API Token": "API Token",
    "Preset Name": "Preset Name",
    "Base URL": "Base URL",
})

SHORTCUT_TR_KO_EN = {'.ysbt 확장자 연결 등록': 'Register .ysbt Association',
 '설정 / 옵션': 'Settings / Options',
 '설정': 'Settings',
 '.ysbt 확장자 연결 해제': 'Unregister .ysbt Association',
 'API 관리': 'API Settings',
 'JSON 파일로 열기': 'Open JSON Project',
 '가로장음(―)': 'Horizontal Dash (―)',
 '가운데 정렬': 'Align Center',
 '가운뎃점(·)': 'Middle Dot (·)',
 '개별 글꼴 프리셋 관리': 'Item Font Presets',
 '개별 번역': 'Translate Current',
 '개별 번역문 불러오기': 'Import Translation Current',
 '개별 분석': 'Analyze Current',
 '개별 인페인팅': 'Inpaint Current',
 '개별 지문 추출': 'Extract Text Current',
 '개별 출력': 'Export Current',
 '개별 텍스트 작업 옵션': 'Item Text',
 '개별 텍스트 정리': 'Clean Text Current',
 '검은 동그라미(●)': 'Black Circle (●)',
 '검은하트(♥)': 'Black Heart (♥)',
 '겹낫표(『』)': 'Double Corner Brackets (『』)',
 '그림판 옵션': 'Canvas Tools',
 '글꼴 선택': 'Select Font',
 '글꼴 축소': 'Decrease Font Size',
 '글꼴 확대': 'Increase Font Size',
 '기능': 'Functions',
 '기능 없음': 'No Functions',
 '기능 추가': 'Add Function',
 '기능은 더블클릭하거나 검색창/목록에 포커스를 둔 상태에서 실제 단축키를 눌러 추가합니다. Enter는 기능 추가가 아니라 확인으로 동작합니다. 확인을 누르면 현재 매크로 기능 목록을 저장하고, 닫기를 누르면 저장하지 않고 나갑니다. 단축키 OFF/없음은 단축키 상태 표시일 뿐, 매크로 실행에는 영향 없습니다.': 'Double-click a function or press the actual shortcut while the search box/list has focus to add it. Press OK to save the current macro function list, or Close to leave without saving. Shortcut OFF/none is only a shortcut status; it does not affect macro execution.',
 '기능 선택': 'Select Function',
 '기능명 / 그룹 / 단축키 검색  예: 자동 줄 내림, Ctrl+B': 'Search function / group / shortcut  e.g. Auto Line Break, Ctrl+B',
 '기능을 더블클릭하거나, 선택 후 [기능 추가]를 누르면 창을 닫지 않고 계속 추가됩니다. 검색창/목록에 포커스를 둔 상태에서 실제 단축키를 누르면 즉시 추가됩니다. 단축키 OFF/없음은 단축키 상태 표시일 뿐, 매크로 실행에는 영향 없습니다.': 'Double-click '
                                                                                                                                            'a '
                                                                                                                                            'function, '
                                                                                                                                            'or '
                                                                                                                                            'select '
                                                                                                                                            'one '
                                                                                                                                            'and '
                                                                                                                                            'press '
                                                                                                                                            '[Add '
                                                                                                                                            'Function] '
                                                                                                                                            'to '
                                                                                                                                            'keep '
                                                                                                                                            'adding '
                                                                                                                                            'without '
                                                                                                                                            'closing '
                                                                                                                                            'the '
                                                                                                                                            'window. '
                                                                                                                                            'If '
                                                                                                                                            'the '
                                                                                                                                            'search '
                                                                                                                                            'box/list '
                                                                                                                                            'has '
                                                                                                                                            'focus, '
                                                                                                                                            'pressing '
                                                                                                                                            'an '
                                                                                                                                            'actual '
                                                                                                                                            'shortcut '
                                                                                                                                            'adds '
                                                                                                                                            'it '
                                                                                                                                            'immediately. '
                                                                                                                                            'Shortcut '
                                                                                                                                            'OFF/None '
                                                                                                                                            'only '
                                                                                                                                            'indicates '
                                                                                                                                            'shortcut '
                                                                                                                                            'status '
                                                                                                                                            'and '
                                                                                                                                            'does '
                                                                                                                                            'not '
                                                                                                                                            'affect '
                                                                                                                                            'macro '
                                                                                                                                            'execution.',
 '기본값 복구': 'Restore Defaults',
 '기울이기': 'Italic',
 '기존 단축키 비활성화 확인': 'Disable Existing Shortcut',
 '다른 이름으로 저장': 'Save As',
 '다음 페이지': 'Next Page',
 '단어장': 'Glossary',
 '단축키': 'Shortcut',
 '단축키 OFF': 'Shortcut OFF',
 '단축키 ON': 'Shortcut ON',
 '단축키 교체 확인': 'Swap Shortcut',
 '단축키 없음': 'No Shortcut',
 '단축키 통합 관리': 'Shortcut Manager',
 '단축키는 프로그램 폴더의 캐시 파일에 저장됩니다.\n같은 단축키를 지정하면 기존 항목과 서로 교체됩니다.\n체크를 끄면 해당 단축키는 사용하지 않으며 입력칸이 비워집니다.\n캐시 위치: ': 'Shortcuts '
                                                                                                             'are '
                                                                                                             'saved to '
                                                                                                             'the '
                                                                                                             'program '
                                                                                                             'cache '
                                                                                                             'file.\n'
                                                                                                             'If you '
                                                                                                             'assign '
                                                                                                             'the same '
                                                                                                             'shortcut, '
                                                                                                             'it will '
                                                                                                             'be '
                                                                                                             'swapped '
                                                                                                             'with the '
                                                                                                             'existing '
                                                                                                             'item.\n'
                                                                                                             'If you '
                                                                                                             'uncheck '
                                                                                                             'an item, '
                                                                                                             'that '
                                                                                                             'shortcut '
                                                                                                             'will be '
                                                                                                             'disabled '
                                                                                                             'and the '
                                                                                                             'input '
                                                                                                             'box will '
                                                                                                             'be '
                                                                                                             'cleared.\n'
                                                                                                             'Cache '
                                                                                                             'path: ',
 '단축키를 전부 기본값으로 돌릴까요?': 'Restore all shortcuts to their defaults?',
 '닫기': 'Close',
 '마스킹 칠하기': 'Fill Mask',
 '말줄임표(…)': 'Ellipsis (…)',
 '매크로 관리': 'Macro Manager',
 '매크로 기능 선택': 'Select Macro Function',
 '매크로 단축키 비활성화 확인': 'Disable Macro Shortcut',
 '매크로 단축키 중복': 'Duplicate Macro Shortcut',
 '매크로 삭제': 'Delete Macro',
 '매크로 이름': 'Macro Name',
 '매크로 이름:': 'Macro name:',
 '매크로 추가': 'Add Macro',
 '매크로는 여러 기능을 추가한 순서대로 연속 실행합니다.\n매크로 단축키가 기존 단축키와 겹치면, 확인 후 기존 단축키를 비활성화합니다.': 'Macros run multiple functions in the '
                                                                                'order they were added.\n'
                                                                                'If a macro shortcut overlaps with an '
                                                                                'existing shortcut, the existing '
                                                                                'shortcut can be disabled after '
                                                                                'confirmation.',
 '매크로를 삭제할까요?': 'Delete this macro?',
 '문자 색상 팔레트': 'Text Color Palette',
 '번역 프롬프트 입력': 'Translation Prompt',
 '번역문 내용 지우기': 'Clear Translation Current',
 '브러시': 'Brush',
 '비어 있음': 'Empty',
 '사용': 'Use',
 '삭제': 'Delete',
 '새 매크로': 'New Macro',
 '새 프로젝트': 'New Project',
 '서로 교체해서 사용할까요?': 'Swap these shortcuts?',
 '세로장음(│)': 'Vertical Dash (│)',
 '아직 추가된 기능이 없습니다.': 'No functions have been added yet.',
 '언어 설정': 'Language Settings',
 '오른쪽 정렬': 'Align Right',
 '옵션': 'Options',
 '왼쪽 정렬': 'Align Left',
 '요술봉 선택': 'Magic Wand Select',
 '요술봉 영역 확장': 'Expand Magic Wand Area',
 '요술봉 허용범위 감소': 'Decrease Magic Wand Tolerance',
 '요술봉 허용범위 증가': 'Increase Magic Wand Tolerance',
 '요술봉 확장범위 감소': 'Decrease Magic Wand Expansion',
 '요술봉 확장범위 증가': 'Increase Magic Wand Expansion',
 '원본으로 돌아가기': 'Restore Original Source',
 '음표(♪)': 'Music Note (♪)',
 '이동': 'Move',
 '이름': 'Name',
 '이미 사용 중인 단축키입니다.': 'This shortcut is already in use.',
 '이전 페이지': 'Previous Page',
 '인페인팅을 원본으로': 'Use Inpaint as Source',
 '일괄 번역': 'Batch Translate',
 '일괄 번역문 내용 지우기': 'Batch Clear Translation',
 '일괄 번역문 불러오기': 'Batch Import Translation',
 '일괄 분석': 'Batch Analyze',
 '일괄 인페인팅': 'Batch Inpaint',
 '일괄 자동 줄 내림': 'Batch Auto Line Break',
 '일괄 자동 텍스트 크기 조정': 'Batch Auto Text Size',
 '일괄 작업 옵션': 'Batch Work',
 '일괄 지문 추출': 'Batch Extract Text',
 '일괄 출력': 'Batch Export',
 '일괄 텍스트 정리': 'Batch Clean Text',
 '자동 줄 내림': 'Auto Line Break',
 '자동 텍스트 크기 조정': 'Auto Text Size',
 '자동저장 모드': 'Auto Save Mode',
 '자동화 작업 옵션': 'Automation',
 '작업 옵션': 'Work',
 '작업 취소': 'Undo',
 '작업 재실행': 'Redo',
 '되돌릴 수 있는 작업이 있으면 이전 상태로 돌아갑니다.': 'Return to the previous state when an undoable action exists.',
 '되돌린 작업을 다시 적용합니다.': 'Reapply the last undone action.',
 '다시 실행할 내역이 없습니다.': 'There is no action to redo.',
 '작업 폴더 위치 변경': 'Change Workspace Folder',
 '작업탭 변경': 'Change Work Tab',
 '재분석': 'Re-analyze',
 '정확히 일치하는 단축키가 없습니다. 기능명 검색 후 항목을 더블클릭하거나 실제 단축키를 눌러주세요.': 'No exact shortcut match was found. Search by function name, then double-click an item or press the actual shortcut.',
 '줄내림': 'Line Break',
 '지우개': 'Eraser',
 '최종 브러시 불투명도 감소': 'Decrease Final Brush Opacity',
 '최종 브러시 불투명도 증가': 'Increase Final Brush Opacity',
 '최종 텍스트 도구': 'Final Text Tool',
 '최종 페인팅 색상': 'Final Paint Color',
 '최종 페인팅을 배경으로 반영': 'Apply Final Paint to Background',
 '추가할 기능을 선택해주세요.': 'Please select a function to add.',
 '축소': 'Zoom Out',
 '클릭하면 이 기능을 매크로에서 제거합니다.': 'Click to remove this function from the macro.',
 '테마 설정': 'Theme Settings',
 '텍스트 넘버 크기 변경': 'Change Text Number Size',
 '텍스트 위 페인팅 ON/OFF': 'Paint Above Text ON/OFF',
 '텍스트 입력 옵션': 'Text Input',
 '텍스트 표시 ON/OFF': 'Show Text ON/OFF',
 '페이지 글꼴 프리셋 관리': 'Page Font Presets',
 '페인팅 마스크 ON/OFF': 'Painting Mask ON/OFF',
 '프로젝트 열기': 'Open Project',
 '시작 화면': 'Start Screen',
 '프로젝트 옵션': 'Project',
 '프로젝트 저장': 'Save Project',
 '하얀하트(♡)': 'White Heart (♡)',
 '현재 매크로 기능': 'Current Macro Functions',
 '홑낫표(「」)': 'Single Corner Brackets (「」)',
 '확대': 'Zoom In',
 '획 색상 팔레트': 'Stroke Color Palette',
 '획 축소': 'Decrease Stroke',
 '획 확대': 'Increase Stroke',
 '확인(Y)': 'Confirm (Y)',
 '취소(N)': 'Cancel (N)',
 'Enter 또는 Y 키로 확인합니다.': 'Press Enter or Y to confirm.',
 'N 키로 취소합니다.': 'Press N to cancel.',
 '개별 프리셋 단축키 비활성화 확인': 'Disable Individual Preset Shortcut?',
 '개별 글꼴 프리셋 단축키 변경': 'Change Individual Font Preset Shortcut',
 '마지막 작업 복구': 'Recover Last Work',
 '임시 파일 삭제': 'Delete Temporary Files',
 '복구할 작업 없음': 'No Recoverable Work',
 '복구할 수 있는 임시 작업 파일을 찾지 못했습니다.': 'No recoverable temporary work files were found.',
 '마지막 작업 폴더를 복구할까요?': 'Recover the last work folder?',
 '복구한 작업은 아직 정식 YSBT 파일이 아닐 수 있습니다. 필요한 경우 [프로젝트 저장]으로 다시 저장해 주세요.': 'The recovered work may not be a finalized YSBT file yet. Use [Save Project] to save it again if needed.',
 '마지막 작업을 복구하지 못했습니다.': 'Could not recover the last work.',
 '복구 실패': 'Recovery Failed',
 '임시 파일 삭제 완료': 'Temporary Files Deleted',
 '삭제할 임시 파일 없음': 'No Temporary Files to Delete',
 '삭제할 수 있는 임시 작업 파일이 없습니다.': 'There are no temporary work files that can be deleted.',
 '현재 열려 있는 작업을 제외한 임시 작업 폴더를 삭제합니다.': 'Temporary work folders except the currently open work will be deleted.',
 '대상 폴더 수': 'Target folders',
 '예상 용량': 'Estimated size',
 '삭제 후에는 해당 임시 작업을 복구할 수 없습니다. 계속할까요?': 'After deletion, those temporary works cannot be recovered. Continue?',
 '임시 파일 삭제가 완료되었습니다.': 'Temporary file deletion is complete.',
 '자동 임시 파일 정리': 'Automatic Temporary File Cleanup',
 '자동 임시 파일 정리: 오래된 임시 파일 없음': 'Auto temp cleanup: no old temporary files.',
 '오래된 임시 작업 폴더는 한 달에 한 번 자동으로 정리됩니다.': 'Old temporary work folders are cleaned automatically once a month.',
 '임시 파일 관리': 'Temporary File Management',
 '임시파일 삭제': 'Delete Temporary Files',
 '임시파일 자동삭제': 'Auto-delete Temporary Files',
 '임시 파일 삭제와 자동 삭제 주기를 설정합니다.': 'Delete temporary files and configure the auto-delete period.',
 '자동 삭제는 선택한 기간마다 실행되며, 선택한 기간 이상 지난 임시 작업 폴더만 삭제합니다.': 'Auto-delete runs at the selected period and only deletes temporary work folders older than the selected period.',
 '한달': '1 Month',
 '3개월': '3 Months',
 '6개월': '6 Months',
 '12개월': '12 Months',
 '자동 임시 파일 정리: 꺼짐': 'Auto temp cleanup is disabled.',
 '일주일': '1 Week',
 '임시 프로젝트': 'Temporary Projects',
 '작업 캐시': 'Work Sessions',
 '총합': 'Total',
 '임시 파일 상태를 읽지 못했습니다.': 'Could not read temporary file status.'}

# v1.8.0 hotfix3 settings/options overview strings
UI_KO_EN.update({
    '확인을 누르면 이 창에서 바꾼 설정이 저장됩니다. 닫기나 X를 누르면 이 창에서 바꾼 설정은 저장하지 않습니다. 복잡한 항목은 오른쪽 버튼으로 전용 관리창을 엽니다.': 'Click OK to save the settings changed in this window. Click Close or X to leave without saving changes made in this window. Complex items open their dedicated management windows from the button on the right.',
    '프로그램의 기본 동작과 작업 환경을 정하는 항목입니다. 여기서 직접 바꾼 값은 확인을 눌러야 저장됩니다.': 'Items that define the program behavior and work environment. Values changed directly here are saved only when you click OK.',
    'ON이면 변경 사항을 실제 프로젝트에 바로 저장합니다. OFF이면 임시 작업 캐시에 먼저 저장하고, 프로젝트 저장 시 확정합니다.': 'When ON, changes are saved directly to the real project. When OFF, changes are saved to the temporary work cache first and finalized when the project is saved.',
    '프로그램 전체의 밝기 테마를 정합니다. 확인을 누르면 선택한 테마가 적용됩니다.': 'Sets the brightness theme for the whole program. The selected theme is applied when you click OK.',
    '메뉴와 안내 문구의 표시 언어를 정합니다. 확인을 누르면 선택한 언어가 적용됩니다.': 'Sets the display language for menus and guidance text. The selected language is applied when you click OK.',
    '프로젝트 작업 폴더와 캐시가 저장되는 기준 위치입니다. 변경은 전용 작업 폴더 설정창에서 확인을 눌러야 적용됩니다.': 'The base location where project work folders and caches are stored. Changes are applied only when you click OK in the dedicated workspace folder dialog.',
    '위치 변경': 'Change Location',
    '자동삭제': 'Auto Delete',
    '오래된 임시 작업 폴더를 자동으로 정리할지 정합니다. 즉시 삭제는 별도 확인 후 바로 실행됩니다.': 'Sets whether old temporary work folders are cleaned automatically. Immediate cleanup runs after a separate confirmation.',
    '지금 정리': 'Clean Now',
    'YSBT 파일 연결 등록': 'Register YSBT File Association',
    'YSBT 파일 연결 해제': 'Unregister YSBT File Association',
    '.ysbt 파일을 더블클릭했을 때 현재 역식붕이 툴로 바로 열리게 Windows 연결을 등록합니다.': 'Registers the Windows association so .ysbt files open directly with the current YSB Tool when double-clicked.',
    '현재 사용자 계정의 .ysbt 연결을 해제합니다. 이전 테스트용 .ysb 연결도 함께 정리합니다.': 'Unregisters the .ysbt association for the current user account and also cleans up the older test .ysb association.',
    '등록': 'Register',
    '해제': 'Unregister',
    '작업 기능을 관리하는 항목입니다. 이 창 안에 전부 펼치면 복잡해지므로, 각 항목의 버튼으로 기존 전용 관리창을 엽니다.': 'Items that manage work features. To avoid making this window too complex, each item opens its existing dedicated management window from its button.',
    'OpenAI, DeepSeek, OpenAI 호환 서버, 인페인팅 API 같은 외부 API 주소와 키, 모델명을 관리합니다. 유료 API 정보가 들어갈 수 있으니 저장 전 확인이 필요합니다.': 'Manages external API URLs, keys, and model names such as OpenAI, DeepSeek, OpenAI-compatible servers, and inpainting APIs. This may include paid API information, so review it before saving.',
    '관리': 'Manage',
    'AI 번역에 사용할 기본 지침을 편집합니다. 작품 말투, 번역 규칙, 금지 표현 같은 지시문을 이곳에서 관리합니다.': 'Edits the default instructions for AI translation. Use this to manage tone, translation rules, and prohibited expressions.',
    '편집': 'Edit',
    '반복해서 나오는 이름, 고유명사, 말투 규칙, 번역 고정어를 관리합니다. 번역 품질을 일정하게 유지하는 데 쓰입니다.': 'Manages recurring names, proper nouns, tone rules, and fixed translation terms. This helps keep translation quality consistent.',
    '작업, 일괄 처리, 텍스트 입력, 옵션 기능에 연결된 단축키를 한곳에서 바꿉니다. 충돌 확인과 비활성화도 여기서 처리합니다.': 'Changes shortcuts for work actions, batch actions, text input, and options in one place. Conflict checks and disabling shortcuts are also handled here.',
    '여러 작업을 하나의 사용자 단축키로 묶어 실행하는 매크로를 관리합니다. 반복 작업을 줄이는 자동화용 기능입니다.': 'Manages macros that bundle multiple actions into one user shortcut. This is used to reduce repetitive work.',
    '현재 페이지 또는 전체 페이지에 적용할 글꼴 스타일 묶음을 관리합니다. 페이지 단위 식질 스타일을 빠르게 맞출 때 사용합니다.': 'Manages font style sets applied to the current page or all pages. Use this to quickly match page-level typesetting styles.',
    '선택한 텍스트 박스 하나에 적용할 글꼴, 크기, 테두리, 색상 같은 개별 스타일 프리셋을 관리합니다.': 'Manages individual style presets such as font, size, outline, and color for a selected text box.',
    '⚙️ 설정 / 옵션 변경 취소': '⚙️ Settings / Options changes canceled',
    '⚙️ 설정 / 옵션 저장 완료': '⚙️ Settings / Options saved',
})


# hotfix5 additions: launcher/session close and confirmation dialogs
_HOTFIX5_UI_KO_EN = {
    '역식붕이 툴': 'YSB Tool',
    '예': 'Yes',
    '아니오': 'No',
    '열기': 'Open',
    '취소': 'Cancel',
    '저장': 'Save',
    '최근 프로젝트 열기': 'Open Recent Project',
    '이 최근 프로젝트를 열까요?': 'Open this recent project?',
    '최근 프로젝트 파일을 찾을 수 없습니다.\n최근 목록에서 제거하거나 파일 위치를 확인해 주세요.': 'The recent project file could not be found.\nRemove it from the recent list or check the file location.',
    '설정 저장': 'Save Settings',
    '이 창에서 바꾼 설정을 저장할까요?': 'Save the settings changed in this window?',
    '설정 저장 완료': 'Settings Saved',
    '설정이 저장되었습니다.': 'Settings have been saved.',
    '⚙️ 설정 / 옵션 저장 취소': '⚙️ Settings / Options save canceled',
    '일괄 작업 중에는 홈화면으로 이동할 수 없습니다.\n작업이 끝난 뒤 다시 시도해 주세요.': 'You cannot go to the home screen while a batch job is running.\nTry again after the job finishes.',
    '🏠 프로젝트를 닫고 홈화면으로 이동했습니다.': '🏠 Closed the project and moved to the home screen.',
    '↩️ 홈화면 이동 취소': '↩️ Home screen move canceled',
    '↩️ 최근 프로젝트 열기 취소': '↩️ Recent project open canceled',
}
UI_KO_EN.update(_HOTFIX5_UI_KO_EN)
UI_EN_KO.update({en: ko for ko, en in _HOTFIX5_UI_KO_EN.items()})


# hotfix7 additions: English cleanup and current project work folder shortcut
_HOTFIX7_UI_KO_EN = {
    '임시 파일 관리': 'Temporary File Management',
    '일주일': '1 Week',
    '한달': '1 Month',
    '3개월': '3 Months',
    '6개월': '6 Months',
    '12개월': '12 Months',
    '영어': 'English',
    '작업 폴더 열기': 'Open Work Folder',
    '작업 폴더 열기 실패': 'Failed to Open Work Folder',
    '현재 열린 프로젝트가 없습니다.': 'No project is currently open.',
    '현재 프로젝트 작업 폴더를 찾을 수 없습니다.': 'Could not find the current project work folder.',
    '현재 프로젝트 작업 폴더를 열었습니다.': 'Opened current project work folder',
    '현재 프로젝트의 작업 폴더로 이동하기': 'Open Current Project Work Folder',
}
UI_KO_EN.update(_HOTFIX7_UI_KO_EN)
UI_EN_KO.update({en: ko for ko, en in _HOTFIX7_UI_KO_EN.items()})

# hotfix8 additions: analysis mask expansion ratio settings
_HOTFIX8_UI_KO_EN = {
    '분석 마스크 확장 비율': 'Analysis Mask Expansion Ratio',
    'OCR/분석 결과로 만들어지는 마스크의 여유 범위를 조절합니다. 글자 테두리가 덜 잡히면 값을 올리고, 배경까지 너무 넓게 잡히면 값을 낮추세요.': 'Adjusts the extra margin of masks created from OCR/analysis results. Increase the value if text outlines are not fully captured, and lower it if too much background is included.',
    '텍스트 마스크 확장 비율': 'Text Mask Expansion Ratio',
    '분석 결과의 텍스트 마스크를 묶고 확장하는 비율입니다. 말풍선 글자 테두리가 덜 잡히면 이 값을 올리세요.': 'Controls how much the text mask from analysis is grouped and expanded. Increase this when speech bubble text outlines are not fully captured.',
    '페인트 마스크 확장 비율': 'Paint Mask Expansion Ratio',
    '인페인팅/페인트 마스크를 만들 때 글자 주변을 얼마나 여유 있게 지울지 정합니다. 배경까지 너무 많이 잡히면 이 값을 낮추세요.': 'Controls how much extra area around text is cleared when creating the inpainting/paint mask. Lower this if too much background is included.',
    '기본값으로 돌아가기': 'Restore Defaults',
    '분석 마스크 설정 저장': 'Save Analysis Mask Settings',
    '분석 마스크 확장 비율을 저장할까요?': 'Save the analysis mask expansion ratios?',
    '분석 마스크 설정 저장 완료': 'Analysis Mask Settings Saved',
    '분석 마스크 확장 비율이 저장되었습니다.': 'Analysis mask expansion ratios have been saved.',
    '🎭 분석 마스크 확장 비율 저장 취소': '🎭 Analysis mask expansion ratio save canceled',
    'OCR/분석 결과로 만들어지는 마스크의 여유 범위를 조절합니다. 글자 테두리가 덜 잡히면 값을 올리고, 배경까지 너무 넓게 잡히면 값을 낮추세요.': 'Adjusts the extra margin of masks created from OCR/analysis results. Increase the value if text outlines are not fully captured, and lower it if too much background is included.',
}
UI_KO_EN.update(_HOTFIX8_UI_KO_EN)
UI_EN_KO.update({en: ko for ko, en in _HOTFIX8_UI_KO_EN.items()})
try:
    SHORTCUT_TR_KO_EN.update({'분석 마스크 확장 비율': 'Analysis Mask Expansion Ratio'})
except Exception:
    pass

# hotfix9 additions: analysis mask minimum expansion size settings
_HOTFIX9_UI_KO_EN = {
    'OCR/분석 결과로 만들어지는 마스크의 여유 범위와 최소 확장 크기를 조절합니다. 최소 확장 크기를 0px로 두면 강제 최소 확장을 사용하지 않습니다.': 'Adjusts the extra mask margin and minimum expansion size created from OCR/analysis results. Set the minimum expansion size to 0px to disable forced minimum expansion.',
    '텍스트 마스크 최소 확장 크기': 'Text Mask Minimum Expansion Size',
    '텍스트 마스크를 만들 때 비율 계산값이 작아도 최소로 확장할 픽셀 크기입니다. 0px이면 최소 확장 강제를 사용하지 않습니다.': 'The minimum pixel size used to expand the text mask even when the ratio-based value is small. Set it to 0px to disable forced minimum expansion.',
    '페인트 마스크 최소 확장 크기': 'Paint Mask Minimum Expansion Size',
    '페인트 마스크를 만들 때 비율 계산값이 작아도 최소로 확장할 픽셀 크기입니다. 0px이면 최소 확장 강제를 사용하지 않습니다.': 'The minimum pixel size used to expand the paint mask even when the ratio-based value is small. Set it to 0px to disable forced minimum expansion.',
    '분석 마스크 확장 설정을 저장할까요?': 'Save the analysis mask expansion settings?',
    '분석 마스크 확장 설정이 저장되었습니다.': 'Analysis mask expansion settings have been saved.',
    '🎭 분석 마스크 확장 설정 저장 취소': '🎭 Analysis mask expansion settings save canceled',
}
UI_KO_EN.update(_HOTFIX9_UI_KO_EN)
UI_EN_KO.update({en: ko for ko, en in _HOTFIX9_UI_KO_EN.items()})

# hotfix10 additions: mask wrapping tool
_HOTFIX10_UI_KO_EN = {
    '마스크 랩핑': 'Mask Wrapping',
    '마스크 랩핑 사각형': 'Mask Wrapping Rectangle',
    '마스크 랩핑 자유형': 'Mask Wrapping Freeform',
    '▭ 사각형': '▭ Rectangle',
    '✎ 자유형': '✎ Freeform',
    '사각형으로 영역 그리기': 'Draw Rectangular Area',
    '자유형으로 영역 그리기': 'Draw Freeform Area',
    '영역 안의 떨어진 마스크들을 하나의 채움 영역으로 감싸줍니다.': 'Wraps separated masks inside the selected area into one filled area.',
    '윈도우 캡처처럼 사각형 범위를 잡고 그 안의 마스크들을 하나로 감싸 채웁니다.': 'Drag a rectangular area like Windows capture, then wrap and fill the masks inside it.',
    '드래그한 자유형 범위 안에서만 마스크들을 하나로 감싸 채웁니다.': 'Wraps and fills masks only inside the freeform area you drag.',
    '선택한 영역 안의 떨어진 마스크들을 하나의 채움 영역으로 감싸줍니다.': 'Wraps separated masks inside the selected area into one filled area.',
    '⚠️ 마스크 랩핑은 텍스트 마스크/페인팅 마스크 탭에서 사용하세요.': '⚠️ Use Mask Wrapping on the Text Mask or Painting Mask tab.',
    '⚠️ 마스크 랩핑 영역이 비어 있습니다.': '⚠️ The mask wrapping area is empty.',
    '⚠️ 선택한 영역 안에 랩핑할 마스크가 2개 이상 필요합니다.': '⚠️ At least two mask islands are required for wrapping inside the selected area.',
    '⚠️ 마스크 랩핑 영역 안에서 마스크를 찾지 못했습니다.': '⚠️ Could not find masks inside the mask wrapping area.',
    '⚠️ 마스크 랩핑 실패:': '⚠️ Mask wrapping failed:',
    '⚠️ 마스크 랩핑으로 추가될 영역이 없습니다.': '⚠️ Mask wrapping has no area to add.',
    '🩹 마스크 랩핑 완료:': '🩹 Mask wrapping complete:',
    '🩹 도구: 마스크 랩핑': '🩹 Tool: Mask Wrapping',
    '🩹 마스크 랩핑 모드: 사각형': '🩹 Mask Wrapping Mode: Rectangle',
    '🩹 마스크 랩핑 모드: 자유형': '🩹 Mask Wrapping Mode: Freeform',
}
UI_KO_EN.update(_HOTFIX10_UI_KO_EN)
UI_EN_KO.update({en: ko for ko, en in _HOTFIX10_UI_KO_EN.items()})
try:
    SHORTCUT_TR_KO_EN.update({
        '마스크 랩핑': 'Mask Wrapping',
        '마스크 랩핑 사각형': 'Mask Wrapping Rectangle',
        '마스크 랩핑 자유형': 'Mask Wrapping Freeform',
    })
except Exception:
    pass



# v1.8.0 cloud hotfix13 security / action dialog strings
UI_KO_EN.update({
    '연결 대상': 'Connection Target',
    '보안 안내': 'Security Notice',
    'OAuth 토큰은 현재 PC의 로컬 캐시에 저장됩니다. 등록 해제 시 이 토큰을 삭제하고, 가능하면 Google 인증 토큰 해제도 함께 시도합니다.': 'The OAuth token is saved in the local cache on this PC. Unregistering deletes this token and, when possible, also attempts to revoke the Google auth token.',
    '클라우드 백업/불러오기를 사용하려면 먼저 Google Drive 계정을 연결해야 합니다.': 'Connect a Google Drive account before using cloud backup/restore.',
    '해제 범위': 'Unregister Scope',
    '주의': 'Warning',
    '등록 해제는 로컬 연결 정보를 지우는 작업입니다. 클라우드에 이미 올라간 백업 파일은 별도 삭제하지 않습니다.': 'Unregistering deletes the local connection information. It does not separately delete backup files already uploaded to the cloud.',
    '이 PC에서 클라우드 연결을 끊는 전용 창입니다.': 'This dialog disconnects cloud access on this PC.',
    '백업 대상': 'Backup Target',
    '옵션, 단축키, 매크로, 글꼴 프리셋, 번역 프롬프트, 단어장 같은 작업환경 캐시를 클라우드에 백업합니다.': 'Back up work-environment cache such as options, shortcuts, macros, font presets, translation prompts, and glossary to the cloud.',
    'API 키까지 백업': 'Back up API keys too',
    'API 키는 유료 API 접근 정보일 수 있으므로, 선택한 경우 암호화가 필수입니다.': 'API keys may grant access to paid APIs, so encryption is required when this is selected.',
    '기본값은 API 키 제외입니다. API 키까지 백업을 체크하면 업로드 전 반드시 암호화하고, 클라우드에서 불러올 때 반드시 복호화합니다. 암호화/복호화가 준비되지 않은 상태에서는 API 키 포함 백업을 실행하지 않습니다.': 'The default is to exclude API keys. If you check API key backup, they must be encrypted before upload and decrypted when restoring from the cloud. API-key backup will not run until encryption/decryption is ready.',
    '보안 규칙': 'Security Rule',
    'API 키는 평문으로 클라우드에 올리지 않습니다. API 키 포함 백업은 암호화 ZIP 또는 암호화된 별도 파일로 저장하고, 불러오기 단계에서 복호화 후 적용합니다.': 'API keys are not uploaded to the cloud in plain text. API-key backups are saved as an encrypted ZIP or a separately encrypted file, and are applied only after decryption during restore.',
    'API 키까지 포함하여 작업환경 캐시를 클라우드로 백업할까요? API 키는 업로드 전에 반드시 암호화됩니다.': 'Back up the work-environment cache including API keys? API keys must be encrypted before upload.',
    'API 키 포함 캐시 백업은 암호화 모듈이 연결된 뒤에만 실행됩니다. 다음 단계에서 업로드 전 암호화와 불러오기 시 복호화를 필수로 연결합니다.': 'Cache backup including API keys will run only after the encryption module is connected. The next step will require encryption before upload and decryption during restore.',
    '현재 PC의 작업환경 캐시를 클라우드에 올리는 전용 창입니다. API 키는 별도 체크한 경우에만 포함하며, 포함 시 암호화가 필수입니다.': 'This dialog uploads this PC’s work-environment cache to the cloud. API keys are included only when separately checked, and encryption is required if included.',
    '불러오기 대상': 'Restore Target',
    '클라우드에 저장된 작업환경 캐시를 내려받아 현재 PC에 적용합니다. 실제 적용 전에는 현재 로컬 설정을 먼저 백업합니다.': 'Download the work-environment cache stored in the cloud and apply it to this PC. Before applying, the current local settings are backed up first.',
    'API 키 복호화 규칙': 'API Key Decryption Rule',
    '백업에 API 키가 포함되어 있다면 반드시 복호화 과정을 거친 뒤에만 적용합니다. 복호화에 실패하면 API 키는 적용하지 않고, 기존 로컬 API 설정을 보호합니다.': 'If a backup includes API keys, they are applied only after decryption. If decryption fails, API keys are not applied and the existing local API settings are protected.',
    '캐시 불러오기는 단축키, 프리셋, 옵션 같은 현재 작업환경을 바꿀 수 있습니다. 적용 전 확인창을 한 번 더 표시합니다.': 'Restoring cache may change the current work environment, such as shortcuts, presets, and options. A confirmation dialog appears before applying.',
    '클라우드 캐시 불러오기는 다음 단계에서 Google Drive 연동과 함께 연결됩니다. 실제 적용 전에는 로컬 설정 백업을 먼저 만들고, API 키가 포함된 백업은 복호화 후 적용합니다.': 'Cloud cache restore will be connected with Google Drive integration in the next step. Before applying, a local settings backup will be created first, and backups containing API keys will be applied only after decryption.',
    '클라우드에 저장된 작업환경 캐시를 내려받아 현재 PC에 적용하는 전용 창입니다.': 'This dialog downloads the work-environment cache stored in the cloud and applies it to this PC.',
    '저장 규칙': 'Save Rule',
    '현재 열려 있는 프로젝트의 YSBT 파일 자체를 클라우드에 백업합니다. 작업환경 캐시가 아니라 지금 작업 중인 프로젝트 파일을 보존하는 기능입니다.': 'Back up the currently open project’s YSBT file itself to the cloud. This preserves the project file you are working on, not the work-environment cache.',
    '저장하지 않은 작업이 있으면 클라우드 백업 전에 먼저 프로젝트 저장 여부를 확인합니다. 저장되지 않은 상태의 프로젝트는 업로드하지 않습니다.': 'If there are unsaved changes, the app asks whether to save before cloud backup. Unsaved project states are not uploaded.',
    '현재 열려 있는 프로젝트 파일을 클라우드에 따로 보존하는 전용 창입니다.': 'This dialog separately preserves the currently open project file in the cloud.',
    '옵션, 단축키, 매크로, 프리셋, 프롬프트, 단어장 같은 작업환경 캐시를 백업합니다. API 키는 체크박스로 별도 선택하며, 포함 시 업로드 전 암호화와 불러오기 시 복호화가 필수입니다.': 'Back up work-environment cache such as options, shortcuts, macros, presets, prompts, and glossary. API keys are selected separately with a checkbox, and if included, encryption before upload and decryption on restore are required.',
    '클라우드에 저장된 작업환경 캐시를 내려받아 현재 PC에 적용합니다. API 키가 포함된 백업은 복호화 후에만 적용합니다.': 'Download the work-environment cache stored in the cloud and apply it to this PC. Backups containing API keys are applied only after decryption.',
})
UI_EN_KO.update({v: k for k, v in UI_KO_EN.items()})

# v1.8.0 cloud menu / cloud hub strings
UI_KO_EN.update({
    '클라우드': 'Cloud',
    '클라우드 등록': 'Register Cloud',
    '클라우드 등록 해제': 'Unregister Cloud',
    '클라우드로 캐시 백업': 'Back Up Cache to Cloud',
    '클라우드에서 캐시 불러오기': 'Restore Cache from Cloud',
    '현재 프로젝트 클라우드에 백업하기': 'Back Up Current Project to Cloud',
    'Google Drive 계정 등록은 다음 단계에서 연결됩니다. 이 버튼은 클라우드 등록 진입점입니다.': 'Google Drive account registration will be connected in the next step. This button is the cloud registration entry point.',
    '클라우드 등록을 해제할까요?': 'Unregister the cloud connection?',
    '현재 버전에서는 실제 클라우드 연결 해제 로직이 아직 연결되지 않았습니다.': 'The actual cloud unregister logic is not connected in this version yet.',
    '현재 작업환경 캐시를 클라우드로 백업할까요?': 'Back up the current work-environment cache to the cloud?',
    '설정 캐시 백업 업로드는 다음 단계에서 Google Drive 연동과 함께 연결됩니다.': 'Settings cache backup upload will be connected with Google Drive integration in the next step.',
    '클라우드에 저장된 작업환경 캐시를 불러올까요? 현재 로컬 설정을 덮어쓸 수 있습니다.': 'Restore the work-environment cache saved in the cloud? This may overwrite current local settings.',
    '클라우드 캐시 불러오기는 다음 단계에서 Google Drive 연동과 함께 연결됩니다. 실제 적용 전에는 로컬 설정 백업을 먼저 만들 예정입니다.': 'Cloud cache restore will be connected with Google Drive integration in the next step. A local settings backup will be created before actual application.',
    '현재 프로젝트 클라우드 백업': 'Current Project Cloud Backup',
    '저장하지 않은 작업이 있습니다. 클라우드 백업 전에 먼저 프로젝트를 저장할까요?': 'There are unsaved changes. Save the project before cloud backup?',
    '현재 프로젝트 YSBT 파일을 클라우드에 백업하는 기능은 다음 단계에서 Google Drive 연동과 함께 연결됩니다.': 'Backing up the current project YSBT file to the cloud will be connected with Google Drive integration in the next step.',
    '클라우드 메뉴는 작업환경 캐시 백업/복원과 프로젝트 백업을 관리합니다. 홈화면에서는 프로젝트가 열려 있지 않으므로 현재 프로젝트 백업 항목은 표시하지 않습니다.': 'The Cloud menu manages work-environment cache backup/restore and project backup. On the home screen, no project is open, so the current project backup item is not shown.',
    'Google Drive 같은 외부 저장소와 연결해 작업환경 캐시를 보존하고, 필요할 때 다시 불러오는 영역입니다.': 'Connect to external storage such as Google Drive to preserve the work-environment cache and restore it when needed.',
    'Google Drive 계정을 연결합니다. 등록 후 캐시 백업, 캐시 불러오기, 프로젝트 백업 기능을 사용할 수 있게 됩니다.': 'Connect a Google Drive account. After registration, cache backup, cache restore, and project backup will be available.',
    '현재 PC에 저장된 클라우드 연결 토큰을 해제합니다. 이후 백업/불러오기 기능은 다시 등록해야 사용할 수 있습니다.': 'Remove the cloud connection token saved on this PC. Backup/restore features will require registration again afterward.',
    '옵션, API 설정, 단축키, 매크로, 프리셋, 프롬프트, 단어장 같은 작업환경 캐시를 클라우드에 백업합니다.': 'Back up work-environment cache such as options, API settings, shortcuts, macros, presets, prompts, and glossary to the cloud.',
    '클라우드에 저장된 작업환경 캐시를 내려받아 현재 PC에 적용합니다. 실제 적용 전에는 로컬 설정 백업을 먼저 만들 예정입니다.': 'Download the work-environment cache stored in the cloud and apply it to this PC. A local settings backup will be created before actual application.',
    '현재 열려 있는 프로젝트의 YSBT 파일을 클라우드에 백업합니다. 작업환경 캐시가 아니라 지금 작업 중인 프로젝트 파일 자체를 보존하는 기능입니다.': 'Back up the YSBT file of the currently open project to the cloud. This preserves the project file itself, not the work-environment cache.',
    '등록': 'Register',
    '해제': 'Unregister',
    '캐시 백업': 'Back Up Cache',
    '캐시 불러오기': 'Restore Cache',
    '프로젝트 백업': 'Back Up Project',
})

# Rebuild reverse table after cloud strings are added.
UI_EN_KO = {en: ko for ko, en in UI_KO_EN.items()}

# v1.8.0 cloud shortcut strings
SHORTCUT_TR_KO_EN.update({
    '클라우드': 'Cloud',
    '클라우드 등록': 'Register Cloud',
    '클라우드 등록 해제': 'Unregister Cloud',
    '클라우드로 캐시 백업': 'Back Up Cache to Cloud',
    '클라우드에서 캐시 불러오기': 'Restore Cache from Cloud',
    '현재 프로젝트 클라우드에 백업하기': 'Back Up Current Project to Cloud',
})

# v1.8.0 hotfix17 workspace default reset strings
UI_KO_EN.update({
    '기본값으로 변경': 'Restore Default',
    'Windows 실제 문서 폴더 아래 YSB_Translator로 되돌립니다.': 'Restore to YSB_Translator under the actual Windows Documents folder.',
    '작업 폴더 위치 기본값으로 변경': 'Restore Workspace Folder to Default',
    '작업 폴더 위치를 기본값으로 변경할까요?': 'Restore the workspace folder location to the default?',
    '현재 위치': 'Current location',
    '기본값': 'Default',
    '변경': 'Change',
    '작업 폴더 위치가 기본값으로 변경 예약되었습니다.\n프로그램을 재실행하면 아래 위치로 이동됩니다.': 'The workspace folder location has been scheduled to restore to the default.\nRestart the program to move it to the location below.',
    '작업 폴더 위치가 이미 기본값입니다.': 'The workspace folder location is already set to the default.',
    '작업 폴더 위치를 기본값으로 변경하지 못했습니다.': 'Failed to restore the workspace folder location to the default.',
    '프로젝트 작업 폴더와 캐시가 저장되는 기준 위치입니다. 위치 변경 또는 기본값으로 변경은 전용 확인 후 적용되며, 기본값은 Windows 실제 문서 폴더 아래 YSB_Translator입니다.': 'This is the base location for project workspace folders and cache. Change Location or Restore Default applies only after its own confirmation. The default is YSB_Translator under the actual Windows Documents folder.',
})
UI_EN_KO.update({v: k for k, v in UI_KO_EN.items()})
SHORTCUT_TR_KO_EN.update({
    '작업 폴더 위치 기본값으로 변경': 'Restore Workspace Folder to Default',
})


# v1.8.0 hotfix18 workspace restart strings
UI_KO_EN.update({
    '기본값으로\n변경': 'Restore\nDefault',
    '작업 폴더 위치 변경': 'Change Workspace Folder Location',
    '폴더 위치 변경으로 프로그램을 재기동합니다.\n취소할 시 이전 설정한 폴더 위치값으로 원복합니다.': 'The program will restart because the workspace folder location is changing.\nIf you cancel, the previous workspace folder location will be restored.',
    '변경 위치': 'New location',
    '재기동(Y)': 'Restart (Y)',
    'Enter 또는 Y 키로 재기동합니다.': 'Press Enter or Y to restart.',
    'N 키로 취소하고 이전 설정값으로 되돌립니다.': 'Press N to cancel and restore the previous setting.',
    '프로젝트 작업 폴더와 캐시가 저장되는 기준 위치입니다. 위치를 바꾸면 프로그램을 재기동해야 적용됩니다. 취소하면 이전 작업 폴더 위치값으로 원복됩니다. 기본값은 Windows 실제 문서 폴더 아래 YSB_Translator입니다.': 'This is the base location for project workspace folders and cache. Changing this location requires restarting the program to apply it. If you cancel, the previous workspace folder location is restored. The default is YSB_Translator under the actual Windows Documents folder.',
})
UI_EN_KO.update({v: k for k, v in UI_KO_EN.items()})


# hotfix11 additions: mask cutting tool
_HOTFIX11_UI_KO_EN = {
    '마스크 커팅': 'Mask Cutting',
    '마스크 선택 사각형': 'Rectangle Area',
    '마스크 선택 자유형': 'Freeform Area',
    '커팅 폭': 'Cut Width',
    '선택 영역 밖 경계를 지정 픽셀만큼 잘라 붙어 있는 마스크를 분리합니다.': 'Cuts the mask by the specified pixels outside the selected boundary to separate connected masks.',
    '사각형 보존 영역의 바깥 경계를 지정 픽셀만큼 잘라냅니다.': 'Cuts the mask by the specified pixels outside the rectangular keep area.',
    '자유형 보존 영역의 바깥 경계를 지정 픽셀만큼 잘라냅니다.': 'Cuts the mask by the specified pixels outside the freeform keep area.',
    '선택 영역 밖으로 잘라낼 마스크 폭입니다.': 'The mask width to cut outside the selected area.',
    '⚠️ 마스크 커팅은 텍스트 마스크/페인팅 마스크 탭에서 사용하세요.': '⚠️ Use Mask Cutting on the Text Mask or Painting Mask tab.',
    '⚠️ 마스크 커팅 영역이 비어 있습니다.': '⚠️ The mask cutting area is empty.',
    '⚠️ 현재 탭에 마스크 레이어가 없습니다.': '⚠️ There is no mask layer on the current tab.',
    '⚠️ 마스크 커팅으로 제거할 외곽 영역이 없습니다.': '⚠️ There is no outer boundary area to cut.',
    '⚠️ 지정한 커팅 영역에 제거할 마스크가 없습니다.': '⚠️ There is no mask to remove in the specified cutting area.',
    '⚠️ 마스크 커팅으로 변경된 영역이 없습니다.': '⚠️ Mask cutting did not change any area.',
    '🔪 도구: 마스크 커팅': '🔪 Tool: Mask Cutting',
    '🔪 마스크 커팅 모드: 사각형': '🔪 Mask Cutting Mode: Rectangle Area',
    '🔪 마스크 커팅 모드: 자유형': '🔪 Mask Cutting Mode: Freeform Area',
    '🔪 마스크 커팅 완료:': '🔪 Mask cutting complete:',
    '⚠️ 마스크 커팅 실패:': '⚠️ Mask cutting failed:',
}
UI_KO_EN.update(_HOTFIX11_UI_KO_EN)
UI_EN_KO.update({en: ko for ko, en in _HOTFIX11_UI_KO_EN.items()})
try:
    SHORTCUT_TR_KO_EN.update({
        '마스크 커팅': 'Mask Cutting',
        '마스크 선택 사각형': 'Rectangle Area',
        '마스크 선택 자유형': 'Freeform Area',
    })
except Exception:
    pass


# v2.0.0 page tabs / drag-and-drop image insertion
_V200_PAGE_TABS_UI_KO_EN = {
    '페이지': 'Pages',
    '페이지 없음': 'No pages',
    '이미지 불러오기': 'Import Images',
    '불러올 이미지 선택': 'Select Images to Import',
    '페이지 삭제': 'Delete Page',
    '이 페이지를 프로젝트에서 삭제할까요?': 'Delete this page from the project?',
    '삭제': 'Delete',
    '페이지 탭 표시명': 'Page Tab Display Name',
    '출력 표시명': 'Output Display Name',
    '원본 파일명': 'Original Filename',
    '1p_원본 파일명': '1p_Original Filename',
    '좌측 이미지 작업창 상단의 페이지 탭에 표시할 이름 형식을 정합니다. 기본값은 1p_원본 파일명입니다.': 'Choose the naming format shown on the page tabs above the left image workspace. The default is 1p_original filename.',
    '결과물, 클린 이미지, 포토샵 스크립트 파일명에 사용할 페이지 이름 형식을 정합니다. 기본값은 1p_원본 파일명입니다.': 'Choose the naming format used for result images, clean images, and Photoshop script filenames. The default is 1p_original filename.',
}
UI_KO_EN.update(_V200_PAGE_TABS_UI_KO_EN)
UI_EN_KO.update({en: ko for ko, en in _V200_PAGE_TABS_UI_KO_EN.items()})


# v2.0.0 hotfix6: empty project creation dialog
_V200_HOTFIX6_UI_KO_EN = {
    '새 프로젝트': 'New Project',
    '프로젝트 이름': 'Project Name',
    '생성 위치': 'Creation Location',
    '생성 경로': 'Creation Path',
    '프로젝트 생성 위치 선택': 'Select Project Creation Location',
    '이미지 없이 빈 작업 인터페이스를 먼저 만들고, 나중에 이미지 불러오기로 페이지를 추가합니다.': 'Create an empty workspace first, then add pages later with Import Images.',
    '만들기': 'Create',
    '프로젝트 생성 실패': 'Project Creation Failed',
    '프로젝트 생성 위치를 만들 수 없습니다.': 'Could not create the project location.',
    '빈 프로젝트를 만들 수 없습니다.': 'Could not create the empty project.',
}
UI_KO_EN.update(_V200_HOTFIX6_UI_KO_EN)
UI_EN_KO.update({en: ko for ko, en in _V200_HOTFIX6_UI_KO_EN.items()})
try:
    SHORTCUT_TR_KO_EN.update({
        '새 프로젝트': 'New Project',
        '이미지 불러오기': 'Import Images',
    })
except Exception:
    pass



API_TR_KO_EN.update({
    'Gemini Image Inpainting': 'Gemini Image Inpainting',
    'Gemini API Key (shared with translation)': 'Gemini API Key (shared with translation)',
    'Remove text inside the white mask and reconstruct the manga background': 'Remove text inside the white mask and reconstruct the manga background',
})


# v2.0.0 hotfix49 shortcut/dialog translation additions
SHORTCUT_TR_KO_EN.update({
    '페이지 탭 파일명 변경': 'Rename Page Tab File Name',
    '현재 이미지탭 삭제': 'Delete Current Image Tab',
    '전체 이미지탭 삭제': 'Delete All Image Tabs',
})


# v2.0.0 hotfix49 UI translation additions
UI_KO_EN.update({
    '페이지 탭 파일명 변경': 'Rename Page Tab File Name',
    '현재 이미지탭 삭제': 'Delete Current Image Tab',
    '전체 이미지탭 삭제': 'Delete All Image Tabs',
    '현재 프로젝트의 작업 폴더로 이동하기': 'Open Current Project Work Folder',
})
UI_EN_KO = {en: ko for ko, en in UI_KO_EN.items()}


# v2.0.0 hotfix52 help/about translations
UI_KO_EN.update({
    '도움말': 'Help',
    '프로그램 정보': 'About',
    'YSB Translator Tool / 역식붕이 툴': 'YSB Translator Tool / 역식붕이 툴',
    '버전': 'Version',
    '이 소프트웨어는 GNU General Public License v3.0에 따라 배포됩니다.': 'This software is distributed under the GNU General Public License v3.0.',
    '이 애플리케이션은 PyQt6를 사용하므로, 오픈소스 배포판은 GPLv3 기준으로 제공됩니다.': 'Because this application uses PyQt6, the open-source distribution is provided under GPLv3.',
    'YSB Translator Tool, 역식붕이 툴, ZeroStress8은 amule949가 사용하는 프로젝트명 및 표지입니다.': 'YSB Translator Tool, 역식붕이 툴, and ZeroStress8 are project names and marks used by amule949.',
    'GPLv3 라이선스는 소스 코드에 적용되며, 프로젝트명·로고·브랜딩 사용 권리를 부여하지 않습니다.': 'The GPLv3 license applies to the source code and does not grant project name, logo, or branding usage rights.',
    '자세한 내용은 LICENSE 및 TRADEMARKS.md를 참고하세요.': 'See LICENSE and TRADEMARKS.md for details.',
})
UI_EN_KO = {en: ko for ko, en in UI_KO_EN.items()}

try:
    SHORTCUT_TR_KO_EN.update({
        '도움말': 'Help',
        '프로그램 정보': 'About',
    })
except Exception:
    pass


# v2.0.0 OCR language combo translations
API_TR_KO_EN.update({
    'OCR 언어': 'OCR Language',
    '일본어': 'Japanese',
    '중국어': 'Chinese',
    '한국어': 'Korean',
    '영어': 'English',
})

# v2.0.0 cloud registration interlock translations
UI_KO_EN.update({
    '이미 Google Drive 계정이 등록되어 있습니다.\n\n다른 계정을 연결하려면 먼저 클라우드 등록 해제를 진행해 주세요.': 'A Google Drive account is already registered.\n\nTo connect a different account, unregister the current cloud account first.',
    '이미 등록된 클라우드 계정이 있어 새 등록을 시작할 수 없습니다. 다른 계정을 연결하려면 먼저 등록 해제를 진행하세요.': 'A cloud account is already registered, so a new registration cannot be started. To connect a different account, unregister the current account first.',
})

# v2.0.0 font refresh translations
UI_KO_EN.update({
    '폰트 갱신': 'Refresh Fonts',
    'Windows에 설치되어 있지만 목록에 보이지 않는 글꼴을 다시 찾습니다.': 'Search again for fonts installed in Windows but missing from the list.',
    '폰트 갱신 확인': 'Refresh Fonts',
    'Windows 글꼴 폴더와 사용자 글꼴 폴더를 다시 검색합니다.\n\n일부 글꼴은 Qt 기본 목록에 바로 보이지 않을 수 있어, 이 작업은 누락된 글꼴을 추가로 등록합니다.\n\n글꼴이 많으면 잠시 걸릴 수 있습니다. 계속할까요?': 'This will scan the Windows Fonts folder and your user Fonts folder again.\n\nSome fonts may not appear in Qt\'s default list, so this registers missing fonts as application fonts.\n\nIt may take a moment if you have many fonts. Continue?',
    '폰트 갱신 완료': 'Font refresh complete',
    '폰트 목록을 갱신했습니다.\n새로 추가된 글꼴 패밀리: {count}개': 'The font list has been refreshed.\nNew font families added: {count}',
    '폰트 갱신 실패': 'Font refresh failed',
    '폰트 갱신 중 오류가 발생했습니다.': 'An error occurred while refreshing fonts.',
})

# v2.0.0 path visibility option translations
UI_KO_EN.update({
    '로그창에 파일 위치 및 경로 표시': 'Show file locations and paths in logs',
    '로그에 저장 위치, 출력 위치, 작업 폴더 같은 실제 파일 경로를 함께 표시합니다. 끄면 완료/실패 같은 결과 문구만 표시합니다.': 'Shows actual file paths such as save locations, output folders, and workspace folders in the log. When disabled, only result messages such as completion/failure are shown.',
    '옵션 및 설정창에 캐시 위치 경로 표시': 'Show cache location paths in options and settings',
    'API, 단축키 같은 옵션/설정 관리창에서 실제 캐시 파일 위치를 표시합니다. 끄면 캐시 경로는 숨깁니다.': 'Shows actual cache file locations in option/settings dialogs such as API and shortcut settings. When disabled, cache paths are hidden.',
    '파일 경로 표시': 'File path display',
    '로그와 설정창에 실제 파일 경로를 표시할지 정합니다. 기본값은 꺼짐이며, 필요한 경우에만 켜는 고급 정보입니다.': 'Choose whether to show actual file paths in logs and settings windows. This is off by default and is advanced information for users who need it.',
    '파일 경로 표시 설정 저장 완료': 'File path display settings saved',
    '표시': 'Show',
    '경로 숨김': 'Path hidden',
    '로그 경로 표시: ON': 'Log path display: ON',
    '로그 경로 표시: OFF': 'Log path display: OFF',
    '설정창 캐시 경로 표시: ON': 'Settings cache path display: ON',
    '설정창 캐시 경로 표시: OFF': 'Settings cache path display: OFF',
})
UI_EN_KO = {en: ko for ko, en in UI_KO_EN.items()}
