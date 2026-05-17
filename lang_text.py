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


UI_KO_EN = {'.ysbt 확장자 연결': '.ysbt File Association',
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
 '.ysbt/.ysb 확장자 연결 해제': 'Unregister .ysbt/.ysb Association',
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


SHORTCUT_TR_KO_EN = {'.ysbt 확장자 연결 등록': 'Register .ysbt Association',
 '.ysbt/.ysb 확장자 연결 해제': 'Unregister .ysbt/.ysb Association',
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
