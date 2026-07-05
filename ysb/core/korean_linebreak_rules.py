"""Korean auto line-break rule table for YSB text auto adjustment.

이 파일은 한국어 전용 줄내림 조건을 한곳에서 수정하기 위한 모듈이다.

핵심 원칙:
- soft 1글자 조사는 떨어지면 감점, hard 짧은 어미/꼬리는 원문 공백이 아닌 어절 내부 절단으로 떨어질 때만 금지급 감점으로 본다.
- "부터", "에서", "수록", "듯이" 같은 2글자 이상 기능 단위는 단독 줄 허용, 내부 절단 금지로 본다.
- "어요", "아요", "니까", "니다", "지요" 같은 말끝 덩어리는 앞말에서 떨어질 수 있지만 내부 절단은 금지로 본다.
- 가벼운 문장부호/괄호/낫표는 폭 계산에서 3개까지 1묶음으로 본다.
- 무거운 특문(…, ―, │, ♡, ♥, ♪ 등)은 일반 글자 1개로 본다.
- 기존 띄어쓰기는 삭제하지 않는다. 줄바꿈만 추가한다.

수정할 때 주로 보는 곳:
- SOFT_ATTACH_LEFT_PARTICLES: 혼자 떨어지면 아쉽지만 불합격까지는 아닌 1글자 조사
- HARD_ATTACH_LEFT_ENDINGS: 혼자 떨어지면 말맛이 깨지는 짧은 어미/꼬리
- NO_SPLIT_FUNCTION_UNITS: 독립 줄은 가능하지만 내부 절단은 금지하는 2글자 이상 기능 단위
- NO_SPLIT_ENDING_UNITS: 독립 줄은 가능하지만 내부 절단은 금지하는 말끝 덩어리
- LIGHT_*_PUNCTUATION: 폭을 가볍게 치고 앞뒤 글자에 붙일 문장부호
- HEAVY_SYMBOLS: 일반 글자 1개만큼 자리를 먹는 특문
- LINE_COUNT_RULES / REQUIRED_FILL_RULES: OCR 박스 비율별 줄 수/합격선

주의:
- 이 모듈은 PyQt에 의존하지 않는다.
- 사용자 노출 문구가 아니므로 i18n 대상은 아니다.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, replace
from typing import Callable, Iterable, List, Sequence, Tuple


# 혼자 줄 앞에 떨어지면 아쉽지만, 극단 상황에서는 후보로 남길 수 있는 1글자 조사.
# "단독으로도 조사 의미를 갖지만 앞말과 붙는 편이 자연스러운" soft 부착 단위다.
SOFT_ATTACH_LEFT_PARTICLES: Tuple[str, ...] = (
    "은", "이", "가",
    "을", "를", "의",
    "에", "께",
    "도", "만", "뿐",
    "와", "과", "랑",
)

# 한 어절 내부에서 혼자 줄 앞에 떨어지면 말맛/의미 단위가 깨지는 짧은 어미/꼬리.
# 원문 공백으로 독립한 짧은 호흡은 허용하고, 어절 내부 절단으로 떨어진 경우만 불합격급 hard 부착 단위로 본다.
# 예: 시작한 / 다, 했 / 어, 그러 / 면, 해 / 서, 하 / 게, 하 / 며, 그러 / 니, 하 / 든, 하 / 던, 그거 / 야, 그건 / 냐 는 금지급 감점.
#
# "는"은 이 목록에 넣지 않는다. 단, "응원하는/좋아하는"처럼 긴 어절 안의
# "하는" 계열은 3글자 보호보다 먼저 NO_SPLIT_ENDING_UNITS에서 보호한다.
# 짧은 "먹는/가는"류는 _neun_should_be_hard()로 hard 보호하고,
# "콘서트는/사람들은"처럼 체언+조사로 보이는 긴 결합은 soft로 남긴다.
# 핵심은 "는" 자체를 전부 금지하는 게 아니라, 어미 보호 단위를 먼저 자른 뒤
# 남은 "는"만 길이/문맥으로 가르는 것이다.
HARD_ATTACH_LEFT_ENDINGS: Tuple[str, ...] = (
    "다", "어", "아",
    "네", "나", "까", "자",
    "지", "죠", "요",
    "군",
    "면", "라", "로", "고", "데", "야",
    "서", "게", "며", "니", "든", "던",
    "음", "세", "냐", "써",
)

# "는" 전용 길이 경계. 어간+는 결합 어절이 이 길이 이하면 hard(보수적으로 보호),
# 이를 초과하면 soft(체언+조사로 보고 분리를 허용)로 본다.
# 3글자 이하: 하는/먹는/가는/이러는 등 동사·형용사 활용형으로 보고 보호한다.
# 4글자 이상: 콘서트는/사람들은처럼 체언+조사로 보고, 분리를 허용하되 약감점만 준다.
NEUN_HARD_COMBINED_LEN_MAX: int = 3


def _neun_should_be_hard(prev_text: object) -> bool:
    """앞 조각과 합친 "...는" 어절이 hard(보호 대상)인지 판단한다.

    prev_text: "는" 바로 앞에 붙는 조각(어간 또는 체언)의 텍스트.
    합친 길이가 NEUN_HARD_COMBINED_LEN_MAX(기본 3) 이하이면 hard로,
    그보다 길면 soft로 본다. 이 함수는 "는"에 대해서만 호출한다.
    """
    try:
        combined_len = visual_len(str(prev_text or '')) + 1  # +1 = "는" 자신
    except Exception:
        combined_len = NEUN_HARD_COMBINED_LEN_MAX + 1
    return combined_len <= NEUN_HARD_COMBINED_LEN_MAX

# 이전 버전 호환 이름. 의미상으로는 soft/hard가 갈라졌지만 외부 호출부 호환을 위해 유지한다.
SINGLE_CHAR_BOUND_PARTICLES: Tuple[str, ...] = SOFT_ATTACH_LEFT_PARTICLES
SHORT_SENTENCE_ENDINGS: Tuple[str, ...] = HARD_ATTACH_LEFT_ENDINGS

# 앞말 부착 단위 전체. soft는 감점, hard는 원문 경계 여부를 본 뒤 불합격급 감점으로 다르게 처리한다.
# "는"은 길이에 따라 hard/soft가 갈리므로(_neun_should_be_hard 참조) 항상 soft 쪽에도 포함해
# line_is_soft_attach_only류 판정에서 "는" 단독 줄을 최소한 soft로는 잡을 수 있게 한다.
ATTACH_LEFT_TOKENS: Tuple[str, ...] = tuple(dict.fromkeys(SOFT_ATTACH_LEFT_PARTICLES + HARD_ATTACH_LEFT_ENDINGS + ("는",)))

# 독립된 줄로 내려도 괜찮지만, 내부를 찢으면 안 되는 2글자 이상 기능 단위.
# 예: 너 / 이랑 / 나 는 가능, 너이 / 랑나 는 금지.
# 예: 집 / 에서 / 부터 는 가능, 집에 / 서부터 또는 집에서부 / 터 는 금지.
# 예: 죽은 / 듯이 는 가능, 죽은 듯 / 이 는 금지.
NO_SPLIT_FUNCTION_UNITS: Tuple[str, ...] = (
    # 격조사/부사격 조사 계열
    "으로", "에서", "에게", "한테", "께서",
    "에다", "에다가",

    # 보조사/기능 덩어리 계열
    "부터", "처럼", "만큼", "수록",
    "조차", "마저", "밖에", "같이", "듯이",

    # 접속/인용 계열 중 내부 절단을 막을 단위
    "라는", "이란",
    "라도", "이랑",

    # 자주 붙는 2글자 이상 기능 표현. 독립 줄은 허용, 내부 절단은 금지한다.
    "때문에", "덕분에", "대신에", "사이에", "중에",
)

# 이전 버전 호환 이름. 실제 의미는 이제 NO_SPLIT_FUNCTION_UNITS가 맞다.
BREAKABLE_FUNCTION_UNITS: Tuple[str, ...] = NO_SPLIT_FUNCTION_UNITS

# 말끝 덩어리. 앞말에서 떨어지는 것은 허용하지만 내부 절단은 금지한다.
# 예: 먹었 / 어요, 그럴수 / 가요, 그렇 / 지요, 아닙 / 니까, 합 / 니다 는 가능.
# 예: 먹었어 / 요, 그럴수가 / 요, 그렇지 / 요, 아닙니 / 까, 합니 / 다 는 금지급 감점.
# 주의: "습니다", "습니까"는 통째 보호하지 않는다. 한국어 감각상 습 / 니다, 습 / 니까로 분리 가능하다.
NO_SPLIT_ENDING_UNITS: Tuple[str, ...] = (
    "어요", "아요", "에요", "예요",
    "니까", "니다",
    "네요", "나요", "가요", "까요", "지요",
    "잖아",
    "거야", "거지", "거죠",
    "겠어", "겠다", "겠네", "겠지", "겠죠",
    "더라",
    "구나", "구만", "군요",
    "던가",

    # 관형/서술형 어미 보호. 3글자 이하 단어 보호보다 먼저 잡아야
    # 응원하는 -> 응원 / 하는 이 되고 응원하 / 는 후보가 사라진다.
    # 너무 넓게 모든 "X는"을 보호하면 콘서트는/후보는 같은 체언+조사를 망가뜨리므로
    # 우선 한국어 번역에서 가장 자주 터지는 안전한 활용 덩어리만 둔다.
    "하는", "되는", "있는", "없는", "않는",
)

# 내부 절단 금지 단위 전체. 독립 줄은 가능하지만 단위 내부가 찢기면 안 된다.
ABSOLUTE_NO_SPLIT_UNITS: Tuple[str, ...] = tuple(dict.fromkeys(NO_SPLIT_FUNCTION_UNITS + NO_SPLIT_ENDING_UNITS))

# 이전 버전 호환 이름. 외부 호출부가 있으면 보호 단위 전체를 반환한다.
# 의미상으로는 이제 "부착 대상"이 아니라 "한국어 줄내림 보호 단위 전체"에 가깝다.
BOUND_MORPHEMES: Tuple[str, ...] = tuple(dict.fromkeys(ABSOLUTE_NO_SPLIT_UNITS + ATTACH_LEFT_TOKENS))

# 이전 버전 호환 이름. 실제 내부 절단 금지 대상은 ABSOLUTE_NO_SPLIT_UNITS다.
PROTECTED_SUFFIX_TOKENS: Tuple[str, ...] = ABSOLUTE_NO_SPLIT_UNITS

# 이전 버전 호환 이름. 실제 되붙이기 대상은 ATTACH_LEFT_TOKENS다.
BOUND_ATTACH_TOKENS: Tuple[str, ...] = ATTACH_LEFT_TOKENS

# 긴 단어를 쪼갤 때 조사/짧은 종결어미를 뒤 조각으로 떨어뜨리지 않을 항목.
SHORT_BOUND_PARTICLES = set(ATTACH_LEFT_TOKENS)

# 가벼운 특문: 3개까지 한 묶음당 시각 자릿수 1로 계산하고, 줄내림은 앞뒤 글자와 붙인다.
LIGHT_OPEN_PUNCTUATION = "「『‘“([{<《〈〔【"
LIGHT_CLOSE_PUNCTUATION = "」』’”)]}>》〉〕】"
LIGHT_INLINE_PUNCTUATION = ".,、。·・･!！?？~〜"
LIGHT_PUNCTUATION = ''.join(dict.fromkeys(LIGHT_OPEN_PUNCTUATION + LIGHT_CLOSE_PUNCTUATION + LIGHT_INLINE_PUNCTUATION))
LIGHT_PUNCT_GROUP_SIZE = 3

# 말줄임표/감탄부호가 길게 붙은 감정 꼬리는 본문과 분리할 수 있다.
# 예: 안에서...!?!? -> 안에서 / ...!?!?
EMOTION_TAIL_PUNCT_VISUAL_LEN_MIN = 2

# 무거운 특문: 실제 글자 하나처럼 취급한다.
HEAVY_SYMBOLS = "…―—–│┃｜♡♥♪♫♬★☆※→←↑↓↔↕"

# 부착 어미 판정에서는 렌더/폭 계산과 별개로 뒤에 붙은 감정 특문을 제거하고
# 핵심 어미를 본다. 예: 까…?, 다♥, 요~ 는 까/다/요 단독 분리로 판정해야 한다.
# 단, visual_len에서는 HEAVY_SYMBOLS를 계속 일반 글자 1개로 본다.
ATTACH_TRAILING_DECORATION = ''.join(dict.fromkeys(LIGHT_CLOSE_PUNCTUATION + LIGHT_INLINE_PUNCTUATION + HEAVY_SYMBOLS))

# 줄 앞에 오면 어색한 닫는 부호/문장부호 계열. HEAVY_SYMBOLS의 …는 제외된다.
LEADING_PUNCTUATION = ''.join(ch for ch in (LIGHT_CLOSE_PUNCTUATION + LIGHT_INLINE_PUNCTUATION) if ch not in HEAVY_SYMBOLS)

# OCR 박스 가로/세로 비율별 우선 줄 수.
# box_ratio = width / height
# min_ratio <= box_ratio < max_ratio 범위로 판정한다.
LINE_COUNT_RULES = [
    {"name": "very_vertical", "min_ratio": 0.00, "max_ratio": 0.55, "preferred": [4, 5, 3, 6, 2, 7, 8], "min_lines_if_long": 3},
    {"name": "vertical", "min_ratio": 0.55, "max_ratio": 0.82, "preferred": [3, 4, 2, 5, 6], "min_lines_if_long": 3},
    {"name": "wide", "min_ratio": 2.10, "max_ratio": 99.0, "preferred": [1, 2, 3], "min_lines_if_long": 1},
    {"name": "semi_wide", "min_ratio": 1.35, "max_ratio": 2.10, "preferred": [2, 1, 3, 4], "min_lines_if_long": 1},
    {"name": "square", "min_ratio": 0.82, "max_ratio": 1.35, "preferred": [2, 3, 1, 4, 5], "min_lines_if_long": 1},
]

# 몇 글자 이하일 때는 1줄만 우선 시도할지.
NO_SPLIT_COMPACT_LEN_MAX = 3

# 공백으로 분리된 완성 어절이 이 길이 이하이면 내부 줄바꿈을 강하게 막는다.
# 예: 좋을까, 해야, 뭐야 같은 짧은 어절은 글자가 조금 작아져도 통째 보존한다.
# 단, 뒤에 붙은 무거운 장식 특문(♥/♪ 등)은 별도 줄로 내려갈 수 있다.
SHORT_WORD_PRESERVE_LEN_MAX = 3

# 3글자 본체 + 1글자 조사 형태의 짧은 어절은 통째 보존한다.
# 예: 에이스가, 수영부에 같은 4칸 이하 어절은 에이/스가처럼 쪼개면
# 이후 줄 압축 단계에서 에이 스가처럼 단어가 벌어질 수 있으므로 먼저 보호한다.
SHORT_STEM_PARTICLE_WORD_PRESERVE_BODY_LEN_MAX = 3
SHORT_STEM_PARTICLE_WORD_PRESERVE_TOTAL_LEN_MAX = 4

# 4글자 이상 공백 없는 긴 어절은 세로형 박스에서 내부 분할할 수 있다.
# 단, 끝 조각은 2글자 이상으로 남겨서 찍어두자~ -> 찍어 / 두자~처럼 보정한다.
# 하자/좋다처럼 3글자 이하 어절은 기존 SHORT_WORD_PRESERVE_LEN_MAX 보호 규칙이 우선한다.
LONG_WORD_SPLIT_CORE_LEN_MIN = 4
LONG_WORD_MIN_TAIL_LEN = 2

# OCR 박스 비율별 최소 채움 합격선. 값은 (required_width_ratio, required_height_ratio).
REQUIRED_FILL_RULES = [
    {"name": "very_vertical", "min_ratio": 0.00, "max_ratio": 0.55, "req_w": 0.30, "req_h": 0.96},
    {"name": "vertical", "min_ratio": 0.55, "max_ratio": 0.82, "req_w": 0.38, "req_h": 0.94},
    {"name": "wide", "min_ratio": 2.10, "max_ratio": 99.0, "req_w": 0.96, "req_h": 0.30},
    {"name": "semi_wide", "min_ratio": 1.35, "max_ratio": 2.10, "req_w": 0.94, "req_h": 0.40},
    {"name": "square", "min_ratio": 0.82, "max_ratio": 1.35, "req_w": 0.86, "req_h": 0.86},
]

# 1줄 후보가 너무 납작한 상태로 합격하지 않게 하는 조건.
# compact_len >= min_len이고 box_ratio < max_box_ratio이면 req_h를 min_height까지 끌어올린다.
ONE_LINE_MIN_HEIGHT_RULES = [
    # 좁거나 정사각형에 가까운 말풍선에서 "예? 뭐야?" 같은 짧은 두 호흡이
    # 한 줄로 과통과하지 않게 한다. 1줄 후보는 실제 높이를 충분히 채우지 못하면 탈락시킨다.
    {"min_len": 4, "max_box_ratio": 1.35, "min_height": 0.70},
    {"min_len": 6, "max_box_ratio": 2.10, "min_height": 0.62},
]

# 근접 합격선. 큰 글자 후보가 req_w/req_h에 아주 조금 못 미칠 때 살린다.
NEAR_TOUCH_W_TOLERANCE = 0.06
NEAR_TOUCH_H_TOLERANCE = 0.04
NEAR_TOUCH_TOTAL_DEFICIT_MAX = 0.07

# 긴 단어 분할 기본값.
SPLIT_MIN_PART_LEN = 3
SPLIT_GUARD_LIMIT = 24
SPLIT_REPAIR_GUARD_LIMIT = 12

# 줄 수/비상 재분할 한계.
MAX_LINE_COUNT = 10
EMERGENCY_BADNESS_PENALTY = 0.75

# split_to_line_count() 후보 탐색 한계.
# 0.86 같은 조기 줄내림 매직넘버를 쓰지 않고, 가능한 줄 경계 후보를 만든 뒤
# OCR 박스 비율/줄 균형/보호 단위 감점으로 고른다.
MAX_LINEBREAK_COMBINATION_CANDIDATES = 240
LINEBREAK_SHAPE_RATIO_WEIGHT = 7.5
LINEBREAK_BALANCE_WEIGHT = 1.25
LINEBREAK_LAST_LINE_SHORT_WEIGHT = 0.65
LINEBREAK_BADNESS_WEIGHT = 140.0
LINEBREAK_LIGHT_PUNCT_EDGE_WEIGHT = 1.5
LINEBREAK_HEIGHT_FACTOR = 1.05

# 폭/겹침 판정 기본값.
BOUND_REPAIR_WIDTH_ALLOW_RATIO = 1.10
HARD_WIDTH_LIMIT_RATIO = 1.10
TEXT_OVERLAP_SMALL_EDGE_PX = 0.0
TEXT_OVERLAP_TINY_AREA_RATIO = 0.0
TEXT_OVERLAP_REQUIRED_GAP_PX = 1.0

# 후보 점수식. 낮을수록 좋은 후보로 보고, 최종 선택에서는 별도 선택키로 큰 글자를 우선한다.
SCORE_UNTOUCHED_PENALTY = 100000.0
SCORE_BADNESS_WEIGHT = 15000.0
SCORE_DEFICIT_WEIGHT = 5000.0
SCORE_RATIO_COST_WEIGHT = 120.0
SCORE_FONT_SIZE_REWARD = 2.0
SCORE_FILL_W_REWARD = 60.0
SCORE_FILL_H_REWARD = 80.0

# 최종 선택키. 1줄 과통과 후보를 살짝 뒤로 미는 조건.
ONE_LINE_SELECTION_PENALTY_MIN_LEN = 4
ONE_LINE_SELECTION_PENALTY_MAX_BOX_RATIO = 1.35

# 줄내림 감점. linebreak_badness()에서 사용한다.
# 조사/짧은 종결어미/보호 단위 파손은 "보기 싫음"이 아니라 금지급 감점으로 본다.
ABSOLUTE_BADNESS = 100.0
BADNESS_SOFT_ATTACH_ONLY_LINE = 2.0
BADNESS_HARD_ATTACH_ONLY_LINE = ABSOLUTE_BADNESS
BADNESS_LEADING_SOFT_ATTACH_TOKEN = 1.5
BADNESS_LEADING_HARD_ATTACH_TOKEN = ABSOLUTE_BADNESS
# 이전 이름 호환. linebreak_badness 내부에서는 soft/hard를 분리해서 사용한다.
BADNESS_PARTICLE_ONLY_LINE = BADNESS_SOFT_ATTACH_ONLY_LINE
BADNESS_LEADING_ATTACH_TOKEN = BADNESS_LEADING_HARD_ATTACH_TOKEN
BADNESS_LEADING_LIGHT_PUNCTUATION = 1.20
BADNESS_SPLIT_FUNCTION_UNIT = ABSOLUTE_BADNESS
BADNESS_SPLIT_ENDING_UNIT = ABSOLUTE_BADNESS
# 한 글자 일반 한글 줄은 보호 단위가 아니면 약한 품질 감점으로만 둔다.
BADNESS_SINGLE_HANGUL_LINE = 0.35
# 3글자 이하 완성 어절 본체가 줄 경계에서 찢기는 경우.
# hard 어미와 같은 금지급 감점으로 보되, 긴 공백 없는 단어의 3글자 분할은 이 규칙 대상이 아니다.
BADNESS_SPLIT_SHORT_WORD = ABSOLUTE_BADNESS
# 긴 어절을 줄 경계에서 쪼갤 수는 있지만, 쪼개진 머리/꼬리를 다른 어절과
# 같은 줄에 섞으면 단어가 끊겨 보인다. 예: 수영부 에이 / 스가 되어.
BADNESS_SPLIT_WORD_MIXED_LINE = 8.0
# 이전 이름 호환.
BADNESS_SPLIT_PROTECTED_SUFFIX = BADNESS_SPLIT_FUNCTION_UNIT


@dataclass(frozen=True)
class _BreakUnit:
    text: str
    space_before: bool = False
    # 원문에서 이 단위 앞에 공백/줄경계가 있었는지 보존한다.
    # _lines_from_breaks()는 표시용 앞공백을 지우지만, 하드 어미 감점은
    # 줄 위치가 아니라 원문 경계에서 나온 독립 호흡인지 여부로 판단해야 한다.
    original_space_before: bool = False
    # 원문 공백 기준 어절 번호. 3글자 이하 완성 어절 보존 규칙에서 사용한다.
    word_index: int = -1
    # 같은 protect_group을 가진 단위들은 가능한 한 같은 줄에 남겨야 한다.
    # 주로 3글자 이하 완성 어절 본체를 보호하기 위한 값이다.
    protect_group: int = -1


def _sorted_tokens(tokens: Sequence[str]) -> Tuple[str, ...]:
    return tuple(sorted((str(x) for x in tokens if x), key=len, reverse=True))


def is_heavy_symbol(ch: str) -> bool:
    return bool(ch) and ch in HEAVY_SYMBOLS


def is_light_punctuation(ch: str) -> bool:
    return bool(ch) and (ch in LIGHT_PUNCTUATION) and (ch not in HEAVY_SYMBOLS)


def strip_light_punctuation(text: object) -> str:
    s = re.sub(r"\s+", "", str(text or ""))
    return ''.join(ch for ch in s if not is_light_punctuation(ch))


def strip_attach_trailing_decoration(text: object) -> str:
    """부착 조사/어미 판정용 핵심 문자열을 만든다.

    렌더링과 폭 계산에서는 …/♥/♪ 같은 무거운 특문을 글자 1칸으로 본다.
    하지만 줄내림 보호 판정에서는 까…?, 다♥, 요~처럼 뒤에 감정 특문이
    붙어도 핵심은 까/다/요 단독 분리이므로 trailing decoration을 제거한다.
    앞/중간 특문은 함부로 제거하지 않고, 끝에 붙은 장식만 걷어낸다.
    """
    s = strip_light_punctuation(text)
    while s and s[-1] in ATTACH_TRAILING_DECORATION:
        s = s[:-1]
    return s


def _is_attach_trailing_decoration_only(text: object) -> bool:
    """부착 단위 뒤쪽 rest가 장식/문장부호뿐인지 판단한다."""
    s = re.sub(r"\s+", "", str(text or ""))
    if not s:
        return True
    return all((is_light_punctuation(ch) or ch in HEAVY_SYMBOLS) for ch in s)


def visual_len(text: object) -> int:
    """줄내림 판단용 시각 자릿수.

    - 공백은 제외한다.
    - 가벼운 특문은 연속 3개까지 1칸으로 본다.
    - 무거운 특문과 일반 글자는 1칸으로 본다.
    """
    s = ''.join(ch for ch in str(text or '') if not ch.isspace())
    total = 0
    light_run = 0
    for ch in s:
        if is_light_punctuation(ch):
            light_run += 1
            continue
        if light_run:
            total += int(math.ceil(light_run / float(max(1, LIGHT_PUNCT_GROUP_SIZE))))
            light_run = 0
        total += 1
    if light_run:
        total += int(math.ceil(light_run / float(max(1, LIGHT_PUNCT_GROUP_SIZE))))
    return total


def compact_len(text: object) -> int:
    """공백을 뺀 줄내림 판단용 글자 수.

    실제 렌더 폭이 아니라 줄내림 조건용 길이다. 가벼운 특문은 visual_len 규칙을 따른다.
    """
    return visual_len(text)


def bound_morphemes() -> Tuple[str, ...]:
    """이전 호출부 호환용. 보호 단위와 부착 우선 단위를 모두 반환한다."""
    return BOUND_MORPHEMES


def single_char_bound_particles() -> Tuple[str, ...]:
    return SINGLE_CHAR_BOUND_PARTICLES


def no_split_function_units() -> Tuple[str, ...]:
    return NO_SPLIT_FUNCTION_UNITS


def breakable_function_units() -> Tuple[str, ...]:
    """이전 이름 호환용. 실제 이름은 no_split_function_units()다."""
    return NO_SPLIT_FUNCTION_UNITS


def short_sentence_endings() -> Tuple[str, ...]:
    return SHORT_SENTENCE_ENDINGS


def soft_attach_left_particles() -> Tuple[str, ...]:
    return SOFT_ATTACH_LEFT_PARTICLES


def hard_attach_left_endings() -> Tuple[str, ...]:
    return HARD_ATTACH_LEFT_ENDINGS


def attach_left_tokens() -> Tuple[str, ...]:
    return ATTACH_LEFT_TOKENS


def no_split_ending_units() -> Tuple[str, ...]:
    return NO_SPLIT_ENDING_UNITS


def absolute_no_split_units() -> Tuple[str, ...]:
    return ABSOLUTE_NO_SPLIT_UNITS


def bound_attach_tokens() -> Tuple[str, ...]:
    """이전 호출부 호환용. 실제로는 조사+짧은 말끝 부착 단위를 반환한다."""
    return ATTACH_LEFT_TOKENS


def protected_suffix_tokens() -> Tuple[str, ...]:
    """이전 호출부 호환용. 실제로는 내부 절단 금지 단위 전체를 반환한다."""
    return ABSOLUTE_NO_SPLIT_UNITS


def line_is_soft_attach_only(line: object) -> bool:
    """한 줄이 soft 조사만으로 구성됐는지 판단한다.

    soft 조사(은/는/이/가 등)는 떨어지면 아쉽지만 불합격은 아니다.
    닫는 따옴표/마침표 같은 가벼운 문장부호가 붙어 있어도 외톨이로 본다.
    """
    s = strip_attach_trailing_decoration(line)
    if not s:
        return False
    return s in SOFT_ATTACH_LEFT_PARTICLES


def line_is_hard_attach_only(line: object) -> bool:
    """한 줄이 hard 짧은 어미/꼬리만으로 구성됐는지 판단한다.

    hard 단위(다/어/아/면/고/데/요 등)는 혼자 떨어지면 의미/말맛이 깨지므로
    금지급 감점 대상으로 본다.
    """
    s = strip_attach_trailing_decoration(line)
    if not s:
        return False
    return s in HARD_ATTACH_LEFT_ENDINGS


def line_is_bad_particle_only(line: object) -> bool:
    """이전 이름 호환용. soft 조사 또는 hard 짧은 어미가 외톨이인지 판단한다."""
    return line_is_soft_attach_only(line) or line_is_hard_attach_only(line)


def line_is_bad_single_hangul_line(line: object) -> bool:
    """일반 한글 한 글자만 한 줄에 남는 후보를 낮은 우선순위로 보낸다.

    soft/hard 부착 단위는 별도 규칙으로 처리하므로 제외한다.
    숫자/영문/기호는 오판이 커서 제외한다.
    """
    s = strip_attach_trailing_decoration(line)
    return len(s) == 1 and ('가' <= s <= '힣') and s not in ATTACH_LEFT_TOKENS


def _leading_attach_token_from(line: object, tokens: Sequence[str]) -> str:
    s = str(line or "").lstrip()
    if not s:
        return ""

    # 닫는 문장부호가 먼저 나오면 부착 복구보다 문장부호 감점 영역이다.
    if s[0] in LEADING_PUNCTUATION:
        return ""

    # 여는 따옴표 뒤에 부착 단위가 바로 나오면 그 단위만 복구 대상으로 본다.
    prefix = ""
    while s and s[0] in LIGHT_OPEN_PUNCTUATION:
        prefix += s[0]
        s = s[1:].lstrip()
    if not s:
        return ""

    for m in _sorted_tokens(tokens):
        if not s.startswith(m):
            continue
        rest = s[len(m):]
        if (
            not rest
            or rest[0].isspace()
            or rest[0] in LEADING_PUNCTUATION
            or rest[0] in LIGHT_CLOSE_PUNCTUATION
            or _is_attach_trailing_decoration_only(rest)
        ):
            return prefix + m
    return ""


def leading_soft_attach_token(line: object) -> str:
    """줄 맨 앞에 떨어진 soft 조사 단위를 찾는다."""
    return _leading_attach_token_from(line, SOFT_ATTACH_LEFT_PARTICLES)


def leading_hard_attach_token(line: object) -> str:
    """줄 맨 앞에 떨어진 hard 짧은 어미/꼬리를 찾는다."""
    return _leading_attach_token_from(line, HARD_ATTACH_LEFT_ENDINGS)


def leading_bound_morpheme(line: object) -> str:
    """이전 이름 호환용. 줄 맨 앞에 떨어진 부착 단위를 찾는다.

    hard를 먼저 보고, 없으면 soft를 본다.
    """
    return leading_hard_attach_token(line) or leading_soft_attach_token(line)


def split_function_unit_across_boundary(left: object, right: object) -> str:
    """줄 경계에서 보호 단위가 내부 절단됐는지 찾는다.

    기능 단위와 말끝 덩어리 모두 금지급으로 본다.
    또한 "그럴수가 / 요"처럼 등록된 고정 단위가 아니더라도
    한글+요 말끝에서 요만 따로 떨어진 경계는 동적 보호 단위로 잡는다.
    """
    a = strip_attach_trailing_decoration(left)
    b = strip_attach_trailing_decoration(right)
    if not a or not b:
        return ""

    # 요 단독 분리: 먹었어 / 요, 그럴수가 / 요 등은 절대 불편 규칙.
    if b.startswith("요") and a and ('가' <= a[-1] <= '힣'):
        return a[-1] + "요"

    for token in _sorted_tokens(ABSOLUTE_NO_SPLIT_UNITS):
        if len(token) < 2:
            continue
        for cut in range(1, len(token)):
            left_part = token[:cut]
            right_part = token[cut:]
            if not (a.endswith(left_part) and b.startswith(right_part)):
                continue

            # 긴 말끝을 사용자가 의도한 더 작은 존댓말 단위로 쪼개는 경우는 허용한다.
            # 예: 그렇잖아요 -> 그렇잖 / 아요.
            # 이때 기존 "잖아" 보호가 "잖 / 아요"를 잘못 금지하지 않도록,
            # 오른쪽이 이미 보호된 말끝 덩어리(아요/어요/에요/지요 등)로 시작하면 통과시킨다.
            if token in NO_SPLIT_ENDING_UNITS:
                for ending in _sorted_tokens(NO_SPLIT_ENDING_UNITS):
                    if ending == token:
                        continue
                    if len(ending) > len(right_part) and ending.startswith(right_part) and b.startswith(ending):
                        break
                else:
                    return token
                continue

            return token
    return ""


def split_protected_suffix_across_boundary(left: object, right: object) -> str:
    """이전 이름 호환용."""
    return split_function_unit_across_boundary(left, right)


def linebreak_badness(lines: Sequence[object]) -> float:
    """한국어 조사/말끝/기능 단위/특문 줄내림 불량도. 0이면 양호, 높을수록 불량.

    문자열 목록만 받는 공개 함수는 "이 줄이 원문 공백에서 시작됐는지 /
    한 어절 내부 절단에서 시작됐는지"를 알 수 없다. 그래서 다/나/까/자/야 같은
    hard 짧은 종결 조각을 줄 위치만 보고 금지급 감점하지 않는다.

    실제 split_to_line_count() 후보 평가는 _BreakUnit의 original_space_before 정보를 가진
    _linebreak_badness_for_units()가 담당한다. 여기서는 출처 정보 없이도 안전한 규칙
    (soft 조사 약감점, 문장부호 선행 감점, 보호 단위 내부 절단 감점)만 적용한다.
    일반 1글자 한글 줄도 원문 경계 여부 없이는 독립 호흡인지 알 수 있으므로 여기서는 감점하지 않는다.
    """
    bad = 0.0
    clean = [str(x or '').strip() for x in (lines or []) if str(x or '').strip()]
    for idx, line in enumerate(clean):
        if line_is_soft_attach_only(line):
            bad += BADNESS_SOFT_ATTACH_ONLY_LINE

        if leading_soft_attach_token(line):
            bad += BADNESS_LEADING_SOFT_ATTACH_TOKEN

        if line[:1] in LEADING_PUNCTUATION:
            bad += BADNESS_LEADING_LIGHT_PUNCTUATION
        if idx > 0 and split_function_unit_across_boundary(clean[idx - 1], line):
            bad += BADNESS_SPLIT_FUNCTION_UNIT
    return bad


def _line_starts_from_source_boundary(line_units: Sequence['_BreakUnit'], line_index: int) -> bool:
    """해당 줄이 원문 공백/원래 시작점에서 생긴 줄인지 판단한다.

    하드 어미 감점은 첫 줄/둘째 줄 같은 위치 기준이 아니라 분리 출처 기준이다.
    원문 공백이나 원래 텍스트 시작점에서 시작한 짧은 호흡은 어디에 있어도 허용하고,
    띄어쓰기 없는 한 어절 내부를 자르면서 생긴 hard 조각만 금지급 감점한다.
    """
    if not line_units:
        return True
    if int(line_index or 0) <= 0:
        return True
    first = line_units[0]
    return bool(getattr(first, 'original_space_before', False) or getattr(first, 'space_before', False))


def _linebreak_badness_for_units(lines: Sequence[Sequence['_BreakUnit']]) -> float:
    """_BreakUnit 출처 정보를 이용한 내부 후보 전용 badness.

    - 원문 공백/줄경계로 독립한 다/나/까/자/야 등은 줄 위치와 무관하게 허용한다.
    - 한 어절 내부 절단으로 hard 짧은 어미/꼬리만 떨어진 경우만 금지급 감점한다.
    - "는" 단독 줄은 길이로 따로 판단한다: 어절 내부 절단이면서 앞 조각과 합친
      길이가 3글자 이하면(하는/먹는류) hard, 4글자 이상이면(콘서트는류) soft.
    """
    bad = 0.0
    clean_lines = [list(line or []) for line in (lines or []) if _units_text(line)]
    texts = [_units_text(line) for line in clean_lines]
    for idx, line_units in enumerate(clean_lines):
        line = texts[idx]
        source_boundary = _line_starts_from_source_boundary(line_units, idx)

        if strip_attach_trailing_decoration(line) == "는" and (not source_boundary) and idx > 0:
            if _neun_should_be_hard(texts[idx - 1]):
                bad += BADNESS_HARD_ATTACH_ONLY_LINE
            else:
                bad += BADNESS_SOFT_ATTACH_ONLY_LINE
        elif (not source_boundary) and line_is_hard_attach_only(line):
            bad += BADNESS_HARD_ATTACH_ONLY_LINE
        elif line_is_soft_attach_only(line):
            bad += BADNESS_SOFT_ATTACH_ONLY_LINE
        elif (not source_boundary) and line_is_bad_single_hangul_line(line):
            bad += BADNESS_SINGLE_HANGUL_LINE

        leading_word = line.lstrip()[:1]
        if leading_word == "는" and (not source_boundary) and idx > 0 and not leading_hard_attach_token(line) and not leading_soft_attach_token(line):
            # "는"으로 시작하되 기존 leading_*_attach_token이 못 잡는 경우(예: "는 정말") -
            # 앞 줄과 합친 길이로 hard/soft를 가른다.
            if _neun_should_be_hard(texts[idx - 1]):
                bad += BADNESS_LEADING_HARD_ATTACH_TOKEN
            else:
                bad += BADNESS_LEADING_SOFT_ATTACH_TOKEN
        elif (not source_boundary) and leading_hard_attach_token(line):
            bad += BADNESS_LEADING_HARD_ATTACH_TOKEN
        elif leading_soft_attach_token(line):
            bad += BADNESS_LEADING_SOFT_ATTACH_TOKEN

        if line[:1] in LEADING_PUNCTUATION:
            bad += BADNESS_LEADING_LIGHT_PUNCTUATION
        if idx > 0 and split_function_unit_across_boundary(texts[idx - 1], line):
            bad += BADNESS_SPLIT_FUNCTION_UNIT
    return bad


def _first_matching_rule(rules: Sequence[dict], box_ratio: float) -> dict:
    ratio = float(box_ratio or 1.0)
    for rule in rules:
        if float(rule.get("min_ratio", 0.0)) <= ratio < float(rule.get("max_ratio", 99.0)):
            return rule
    return dict(rules[-1]) if rules else {}


def line_count_candidates(compact_length: int, box_ratio: float) -> List[int]:
    """OCR 박스 비율과 글자 수로 우선 시도할 줄 수 목록을 만든다."""
    compact_length = max(1, int(compact_length or 1))
    max_lines = max(1, min(MAX_LINE_COUNT, compact_length))
    if compact_length <= NO_SPLIT_COMPACT_LEN_MAX:
        preferred = [1]
        min_lines_if_long = 1
    else:
        rule = _first_matching_rule(LINE_COUNT_RULES, box_ratio)
        preferred = list(rule.get("preferred") or [1])
        min_lines_if_long = int(rule.get("min_lines_if_long") or 1)

    out: List[int] = []
    for n in preferred + list(range(1, max_lines + 1)):
        try:
            n = int(n)
        except Exception:
            continue
        if not (1 <= n <= max_lines) or n in out:
            continue
        if compact_length >= 6 and n < min_lines_if_long:
            continue
        out.append(n)
    return out or [1]


def required_fill_for_box(box_ratio: float) -> Tuple[float, float]:
    """OCR 박스를 어느 정도 채워야 합격으로 볼지 반환한다."""
    rule = _first_matching_rule(REQUIRED_FILL_RULES, box_ratio)
    return float(rule.get("req_w", 0.86)), float(rule.get("req_h", 0.86))


def one_line_required_height(line_count: int, compact_length: int, box_ratio: float, req_h: float) -> float:
    """1줄 후보 전용 높이 합격선을 반환한다."""
    need = float(req_h)
    if int(line_count or 1) > 1:
        return need
    compact_length = int(compact_length or 0)
    ratio = float(box_ratio or 1.0)
    for rule in ONE_LINE_MIN_HEIGHT_RULES:
        if compact_length >= int(rule.get("min_len", 0)) and ratio < float(rule.get("max_box_ratio", 99.0)):
            need = max(need, float(rule.get("min_height", need)))
    return need


def touch_ok_for_lines(lines: Sequence[str], fill_w: float, fill_h: float, *, compact_length: int, box_ratio: float, req_w: float, req_h: float) -> bool:
    """채움 비율이 합격선에 닿았는지 판단한다."""
    line_count = max(1, len([x for x in (lines or []) if str(x or "").strip()]))
    height_req = one_line_required_height(line_count, compact_length, box_ratio, req_h)
    return float(fill_w) >= float(req_w) and float(fill_h) >= float(height_req)


def near_touch_ok(fill_w: float, fill_h: float, req_w: float, req_h: float) -> bool:
    """아주 조금 부족한 큰 글자 후보를 살릴지 판단한다."""
    w_def = max(0.0, float(req_w) - float(fill_w))
    h_def = max(0.0, float(req_h) - float(fill_h))
    return (
        float(fill_w) >= max(0.0, float(req_w) - NEAR_TOUCH_W_TOLERANCE)
        and float(fill_h) >= max(0.0, float(req_h) - NEAR_TOUCH_H_TOLERANCE)
        and (w_def + h_def) <= NEAR_TOUCH_TOTAL_DEFICIT_MAX
    )


def _split_plain_by_visual_count(text: str, max_part_len: int) -> List[str]:
    text = str(text or '')
    if not text:
        return []
    max_part_len = max(SPLIT_MIN_PART_LEN, int(max_part_len or SPLIT_MIN_PART_LEN))
    if visual_len(text) <= max_part_len:
        return [text]

    parts: List[str] = []
    current = ''
    current_len = 0
    for ch in text:
        ch_len = max(1, visual_len(ch))
        if current and current_len + ch_len > max_part_len:
            parts.append(current)
            current = ch
            current_len = ch_len
        else:
            current += ch
            current_len += ch_len
    if current:
        parts.append(current)

    fixed: List[str] = []
    for part in parts:
        if fixed and visual_len(part) == 1 and strip_light_punctuation(part) in SHORT_BOUND_PARTICLES:
            fixed[-1] += part
        else:
            fixed.append(part)
    return fixed or [text]


def _dynamic_no_split_units_for_chunk(chunk: object) -> Tuple[str, ...]:
    """특정 토큰 끝에서만 생기는 동적 말끝 보호 단위를 반환한다.

    대표 케이스: 그럴수가요 -> 그럴수 / 가요.
    모든 한글+요 조합을 정적 목록으로 만들 수 없으므로 토큰 끝의 마지막 두 글자를 보호한다.
    """
    s = str(chunk or '')
    if len(s) >= 2 and s[-1] == "요" and ('가' <= s[-2] <= '힣'):
        return (s[-2:],)
    return tuple()


def _split_korean_suffix_units(chunk: str, max_plain_part_len: int | None = None) -> List[str]:
    """공백 없는 일반 문자열을 보호 단위로 나눈다.

    ABSOLUTE_NO_SPLIT_UNITS는 단어 끝이 아니어도 먼저 독립 단위로 잡는다.
    예: 지금부터야 -> 지금 / 부터 / 야
        죽은듯이 -> 죽은 / 듯이
        먹었어요 -> 먹었 / 어요
        그럴수가요 -> 그럴수 / 가요
        그렇지요 -> 그렇 / 지요
        아니에요 -> 아니 / 에요
        그렇잖아요 -> 그렇잖 / 아요
        아닙니까 -> 아닙 / 니까
    남은 꼬리에는 ATTACH_LEFT_TOKENS(soft 조사 + hard 짧은 어미)를 뒤에서부터 분리한다.
    """
    s = str(chunk or '')
    if not s:
        return []

    protected = _sorted_tokens(tuple(dict.fromkeys(ABSOLUTE_NO_SPLIT_UNITS + _dynamic_no_split_units_for_chunk(s))))

    core, punct = _split_core_and_trailing_light_punctuation(s)
    if _should_split_trailing_emotion_punctuation(core, punct):
        return _split_korean_suffix_units(core, max_plain_part_len=max_plain_part_len) + [punct]
    if _is_short_stem_particle_word(s):
        return [s]
    has_protected_unit = any(tok and tok in core for tok in protected)
    # 보호 어미/기능 단위가 없는 긴 무공백 어절은 조사/어미를 한 글자씩 뜯기 전에
    # 먼저 전체 어절 기준의 "끝 2글자 tail" 규칙을 적용한다.
    # 예: 기다려지네 -> 기다려/지네, 먹었을까 -> 먹었/을까.
    # 이 분기를 거치지 않으면 지/네, 을/까 같은 1글자 hard 조각이 먼저 생기고
    # repair 단계에서 기다/려지네 같은 3글자 tail 오분할이 생긴다.
    if (not has_protected_unit) and visual_len(core) >= LONG_WORD_SPLIT_CORE_LEN_MIN:
        return _split_long_core_with_tail(s)

    def append_plain(out: List[str], plain: str) -> None:
        if not plain:
            return
        # plain 꼬리에 soft 조사/hard 짧은 어미가 붙어 있으면 분리한다.
        suffixes: List[str] = []
        remain = plain
        guard = 0
        for _ in range(16):
            matched = ''
            for tok in _sorted_tokens(ATTACH_LEFT_TOKENS):
                if remain == tok:
                    continue
                if len(remain) > len(tok) and remain.endswith(tok):
                    matched = tok
                    break
            if not matched:
                break
            suffixes.insert(0, matched)
            remain = remain[:-len(matched)]
            guard += 1
            if guard >= 16:
                break
        if remain:
            if max_plain_part_len and visual_len(remain) > max_plain_part_len:
                out.extend(_split_plain_by_visual_count(remain, max_plain_part_len))
            else:
                out.append(remain)
        out.extend(suffixes)

    out: List[str] = []
    i = 0
    while i < len(s):
        match_pos = None
        match_tok = ''
        for pos in range(i, len(s)):
            for tok in protected:
                if s.startswith(tok, pos):
                    match_pos = pos
                    match_tok = tok
                    break
            if match_tok:
                break
        if match_tok and match_pos is not None:
            append_plain(out, s[i:match_pos])
            out.append(match_tok)
            i = match_pos + len(match_tok)
            continue
        append_plain(out, s[i:])
        break

    return out or [s]

def _attach_light_punctuation(units: List[str]) -> List[str]:
    """가벼운 특문을 앞/뒤 단위에 붙여 줄바꿈 중간 절단을 막는다."""
    out: List[str] = []
    pending_open = ''
    for raw in units:
        unit = str(raw or '')
        if not unit:
            continue
        if all(is_light_punctuation(ch) for ch in unit):
            if all(ch in LIGHT_OPEN_PUNCTUATION for ch in unit):
                pending_open += unit
                continue
            if out:
                if _should_split_trailing_emotion_punctuation(out[-1], unit):
                    out.append(unit)
                else:
                    out[-1] += unit
                continue
            pending_open += unit
            continue
        if pending_open:
            unit = pending_open + unit
            pending_open = ''
        out.append(unit)
    if pending_open:
        if out:
            out[-1] += pending_open
        else:
            out.append(pending_open)
    return out


def _split_core_and_trailing_light_punctuation(text: object) -> Tuple[str, str]:
    """본문과 뒤에 붙은 가벼운 문장부호를 분리한다.

    예: 두자~ -> (두자, ~). 문장부호는 분할 뒤 tail에 다시 붙인다.
    """
    s = str(text or '')
    cut = len(s)
    while cut > 0 and is_light_punctuation(s[cut - 1]):
        cut -= 1
    return s[:cut], s[cut:]




def _should_split_trailing_emotion_punctuation(core: object, punct: object) -> bool:
    """길게 붙은 감정 문장부호를 본문과 분리할지 판단한다.

    나...처럼 짧은 독백 꼬리는 앞 글자에 붙이고,
    안에서...!?!?처럼 본문+긴 감정 꼬리는 안에서 / ...!?!?로 분리할 수 있게 한다.
    """
    c = str(core or '')
    p = str(punct or '')
    if not c or not p:
        return False
    if visual_len(c) < 2:
        return False
    return visual_len(p) >= EMOTION_TAIL_PUNCT_VISUAL_LEN_MIN

def _is_short_stem_particle_word(text: object) -> bool:
    """3글자 본체 + 1글자 조사형 짧은 어절인지 판단한다.

    에이스가/수영부에처럼 본체는 3칸 이하이고 마지막이 soft 조사인 경우는
    아이스크림 같은 긴 명사와 달리 통째 보존하는 편이 더 안전하다.
    """
    core, _punct = _split_core_and_trailing_light_punctuation(text)
    core = str(core or '')
    if not core:
        return False
    total_len = visual_len(core)
    if total_len <= SHORT_WORD_PRESERVE_LEN_MAX:
        return True
    if total_len > SHORT_STEM_PARTICLE_WORD_PRESERVE_TOTAL_LEN_MAX:
        return False
    for tok in _sorted_tokens(SOFT_ATTACH_LEFT_PARTICLES + ("는",)):
        if not tok or len(tok) != 1:
            continue
        if core.endswith(tok) and len(core) > len(tok):
            stem = core[:-len(tok)]
            if 0 < visual_len(stem) <= SHORT_STEM_PARTICLE_WORD_PRESERVE_BODY_LEN_MAX:
                return True
    return False

def _split_long_core_with_tail(text: object, *, min_tail_len: int = LONG_WORD_MIN_TAIL_LEN) -> List[str]:
    """4글자 이상 긴 무공백 어절을 끝 2글자 꼬리 중심으로 2조각으로 나눈다.

    기본 원칙은 "3글자 이하는 통째 보호, 4글자 이상은 마지막 2글자를 tail로 분리"다.
    그래서 6글자라도 절반(3/3)으로 자르지 않고 4/2로 자른다.

    기다려지네 -> 기다려 / 지네
    먹었을까 -> 먹었 / 을까
    찍어두자~ -> 찍어 / 두자~
    아이스크림 -> 아이스 / 크림
    시작한다 -> 시작 / 한다
    """
    core, punct = _split_core_and_trailing_light_punctuation(text)
    core_len = visual_len(core)
    if core_len < LONG_WORD_SPLIT_CORE_LEN_MIN:
        return [str(text or '')]
    min_tail_len = max(1, int(min_tail_len or 1))
    # 사용자가 보는 기본 규칙은 "끝 2글자 꼬리"다.
    # 이전처럼 core_len // 2를 섞으면 기다려지네 -> 기다/려지네 같은 3글자 tail이 생긴다.
    tail_len = min(max(1, min_tail_len), max(1, core_len - 1))
    head_len = max(1, core_len - tail_len)
    head = core[:head_len]
    tail = core[head_len:] + punct
    if not head or not tail:
        return [str(text or '')]
    return [head, tail]


def _repair_long_word_lonely_hard_suffix_units(units: Sequence[str]) -> List[str]:
    """긴 무공백 어절 끝의 1글자 hard suffix 외톨이를 2글자 이상 tail로 보정한다.

    기존 hard 어미 규칙은 하/자, 했/다 같은 잘못된 내부 절단을 막기 위한 것이다.
    하지만 4글자 이상 어절에서 자/라/다 같은 1글자 suffix를 별도 단위로 떼면
    찍어두자~가 찍어두 / 자~가 되고, 이 후보가 hard 감점으로 밀린다.
    이 경우는 suffix를 앞 조각과 다시 합쳐 찍어 / 두자~처럼 2글자 이상 tail로 재분할한다.

    "는"은 HARD_ATTACH_LEFT_ENDINGS에 없으므로 아래 일반 분기를 안 타고,
    _neun_should_be_hard()로 별도 판단한다: 앞 조각과 합친 길이가 3글자 이하면
    (하는/먹는/가는처럼 동사 어간+활용형) 합쳐서 보호하고, 4글자 이상이면
    (콘서트는/사람들은처럼 체언+조사) 합치지 않고 그대로 분리 상태를 유지한다.
    """
    out: List[str] = []
    for raw in units or []:
        unit = str(raw or '')
        if not unit:
            continue
        clean = strip_attach_trailing_decoration(unit)
        if out and visual_len(clean) == 1 and clean == "는":
            prev = out[-1]
            if _neun_should_be_hard(prev):
                # 하/는, 먹/는, 이러/는 같은 hard 활용형은 여기서 실제 한 단위로 합친다.
                # 예전에는 뒤의 3글자 보호 단계에 기대면서 조각 자체를 남겼는데,
                # 긴 어절 안에서는 그 순서 때문에 응원하/는 같은 오분할 후보가 살아남을 수 있었다.
                out.pop()
                out.append(prev + unit)
            else:
                # 체언+조사로 보고 합치지 않는다 - 이미 올바르게 분리된 상태(예: 콘서트/는)를 보존.
                out.append(unit)
        elif (
            out
            and visual_len(clean) == 1
            and clean in HARD_ATTACH_LEFT_ENDINGS
        ):
            prev = out.pop()
            combined = prev + unit
            combined_core = strip_attach_trailing_decoration(combined)
            if visual_len(combined_core) >= LONG_WORD_SPLIT_CORE_LEN_MIN:
                out.extend(_split_long_core_with_tail(combined))
            else:
                out.append(prev)
                out.append(unit)
        else:
            out.append(unit)
    return out


def linebreak_units_for_token(token: object, max_plain_part_len: int | None = None) -> List[str]:
    """한 공백 토큰을 줄내림 가능한 최소 단위로 나눈다."""
    s = str(token or '').strip()
    if not s:
        return []
    primitive: List[str] = []
    buf = ''
    mode = ''

    def flush() -> None:
        nonlocal buf, mode
        if buf:
            if mode == 'normal':
                primitive.extend(_split_korean_suffix_units(buf, max_plain_part_len=max_plain_part_len))
            else:
                primitive.append(buf)
        buf = ''
        mode = ''

    for ch in s:
        if is_heavy_symbol(ch):
            flush()
            primitive.append(ch)
        elif is_light_punctuation(ch):
            if mode != 'light':
                flush()
                mode = 'light'
            buf += ch
        else:
            if mode != 'normal':
                flush()
                mode = 'normal'
            buf += ch
    flush()
    attached = _attach_light_punctuation(primitive)
    return _repair_long_word_lonely_hard_suffix_units(attached)



def _piece_is_heavy_symbol_only(piece: object) -> bool:
    s = str(piece or '').strip()
    return bool(s) and all(is_heavy_symbol(ch) for ch in s)


def _piece_is_decoration_only(piece: object) -> bool:
    s = str(piece or '').strip()
    return bool(s) and all((is_light_punctuation(ch) or is_heavy_symbol(ch)) for ch in s)


def _short_word_body_end(pieces: Sequence[str]) -> int:
    """3글자 이하 어절 보존에서 본체로 볼 끝 위치를 반환한다.

    뒤에 붙은 ♥/♡/♪ 같은 무거운 장식 특문은 본체를 깨느니 따로 내릴 수 있으므로
    보호 그룹에서 제외한다. ?/! 같은 가벼운 문장부호는 앞 단위에 붙어 있으므로 본체에 포함된다.
    """
    end = len(list(pieces or []))
    items = list(pieces or [])
    while end > 0 and _piece_is_decoration_only(items[end - 1]):
        end -= 1
    return end


def _short_word_protect_group_for_pieces(pieces: Sequence[str], word_index: int) -> int:
    """공백 기준 3글자 이하 완성 어절이면 보호 그룹 번호를 반환한다.

    예: 좋을까 -> 좋/을/까 단위가 생겨도 같은 줄에 남기는 쪽을 우선한다.
        좋을까♥ -> 좋/을/까는 같은 줄에, ♥는 별도 줄 허용.
        아이스크림 -> 4글자 이상이므로 아이스/크림 같은 3글자 분할 허용.
    """
    items = [str(x or '') for x in (pieces or []) if str(x or '')]
    if not items or int(word_index) < 0:
        return -1
    body_end = _short_word_body_end(items)
    if body_end <= 0:
        return -1
    body_text = ''.join(items[:body_end])
    # 가벼운 문장부호뿐 아니라 뒤에 붙은 감정 특문도 보호 판단에서는 제외한다.
    # 좋을까?, 있을까…?, 할까♥ 는 본체 좋을까/있을까/할까 기준으로 보호한다.
    body_core = strip_attach_trailing_decoration(body_text)
    body_len = visual_len(body_core)
    if 0 < body_len <= SHORT_WORD_PRESERVE_LEN_MAX:
        return int(word_index)
    return -1


def _short_word_split_badness(lines: Sequence[Sequence[_BreakUnit]]) -> float:
    """3글자 이하 완성 어절 본체가 여러 줄에 찢겼는지 평가한다."""
    group_lines = {}
    for line_idx, line in enumerate(lines or []):
        for unit in line or []:
            try:
                group = int(getattr(unit, 'protect_group', -1))
            except Exception:
                group = -1
            if group < 0:
                continue
            group_lines.setdefault(group, set()).add(int(line_idx))
    bad = 0.0
    for line_set in group_lines.values():
        if len(line_set) > 1:
            bad += BADNESS_SPLIT_SHORT_WORD
    return bad

def _make_break_units(text: object, target_lines: int | None = None) -> List[_BreakUnit]:
    raw = re.sub(r"\s+", " ", str(text or '').strip())
    if not raw:
        return [_BreakUnit('')]
    max_plain_part_len = None
    if target_lines and target_lines > 1:
        max_plain_part_len = max(SPLIT_MIN_PART_LEN, int(math.ceil(max(1, visual_len(raw)) / float(target_lines))))
    units: List[_BreakUnit] = []
    pending_space = False
    word_index = -1
    for part in re.findall(r"\S+|\s+", raw):
        if part.isspace():
            pending_space = bool(units)
            continue
        word_index += 1
        pieces = linebreak_units_for_token(part, max_plain_part_len=max_plain_part_len)
        protect_group = _short_word_protect_group_for_pieces(pieces, word_index)
        body_end = _short_word_body_end(pieces)
        # 3글자 이하 완성 어절 본체는 후보 단위 단계에서 먼저 하나로 묶는다.
        # 이렇게 해야 좋을까?/먹어야 같은 짧은 어절이 target_lines 때문에 억지로 찢기지 않는다.
        if protect_group >= 0 and body_end > 1:
            pieces = [''.join(pieces[:body_end])] + list(pieces[body_end:])
            body_end = 1
        for idx, piece in enumerate(pieces):
            group = protect_group if (protect_group >= 0 and idx < body_end) else -1
            had_space_before = bool(pending_space and idx == 0)
            units.append(_BreakUnit(
                piece,
                space_before=had_space_before,
                original_space_before=had_space_before,
                word_index=word_index,
                protect_group=group,
            ))
            pending_space = False
    return units or [_BreakUnit(raw)]

def _units_text(units: Sequence[_BreakUnit]) -> str:
    out = ''
    for unit in units:
        if unit.space_before and out:
            out += ' '
        out += unit.text
    return out.strip()


def split_token_by_count(token: object, max_part_len: int) -> List[str]:
    """공백 없는 긴 한국어 덩어리를 보호 단위 기준으로 쪼갠다."""
    token = str(token or '').strip()
    if not token:
        return []
    max_part_len = max(SPLIT_MIN_PART_LEN, int(max_part_len or SPLIT_MIN_PART_LEN))
    units = linebreak_units_for_token(token, max_plain_part_len=max_part_len)
    if len(units) <= 1 and visual_len(token) <= max_part_len:
        return [token]

    parts: List[str] = []
    current = ''
    current_len = 0
    for unit in units:
        u_len = max(1, visual_len(unit))
        if current and current_len + u_len > max_part_len:
            parts.append(current)
            current = unit
            current_len = u_len
        else:
            current += unit
            current_len += u_len
    if current:
        parts.append(current)

    fixed: List[str] = []
    for part in parts:
        clean = strip_light_punctuation(part)
        if fixed and visual_len(part) == 1 and clean in SHORT_BOUND_PARTICLES:
            fixed[-1] += part
        else:
            fixed.append(part)
    return fixed or [token]


def split_token_by_width(token: object, target_w: float, width_fn: Callable[[str], float], *, max_visual_part_len: int = 8) -> List[str]:
    """렌더 폭 기준으로 긴 토큰을 나누되 보호 단위 내부는 자르지 않는다."""
    token = str(token or '').strip()
    if not token:
        return []
    target_w = max(1.0, float(target_w or 1.0))
    units = linebreak_units_for_token(token, max_plain_part_len=max(SPLIT_MIN_PART_LEN, int(max_visual_part_len or 8)))
    if len(units) <= 1 and float(width_fn(token)) <= target_w:
        return [token]

    parts: List[str] = []
    current = ''
    for unit in units:
        trial = current + unit
        if current and float(width_fn(trial)) > target_w:
            parts.append(current)
            current = unit
        else:
            current = trial
    if current:
        parts.append(current)

    fixed: List[str] = []
    for part in parts:
        clean = strip_light_punctuation(part)
        if fixed and visual_len(part) == 1 and clean in SHORT_BOUND_PARTICLES:
            trial = fixed[-1] + part
            if float(width_fn(trial)) <= target_w * 1.10:
                fixed[-1] = trial
            else:
                fixed.append(part)
        else:
            fixed.append(part)
    return fixed or [token]


def make_units_for_target(text: object, target_lines: int) -> List[str]:
    """목표 줄 수를 맞추기 위한 표시용 단위 목록을 반환한다.

    이전 버전 호환용으로 문자열 목록을 반환한다. 내부 split_to_line_count()는
    공백 보존을 위해 _BreakUnit을 직접 사용한다.
    """
    return [u.text for u in _make_break_units(text, target_lines=target_lines) if u.text]




def _split_word_mixed_line_badness(lines: Sequence[Sequence[_BreakUnit]]) -> float:
    """긴 어절이 줄 경계에서 쪼개질 때 다른 어절과 섞이는 후보를 감점한다.

    아이스/크림처럼 한 단어만 깔끔하게 두 줄로 나뉘는 것은 허용할 수 있다.
    하지만 수영부 에이 / 스가 되어처럼 쪼개진 단어 조각이 앞뒤 다른 어절과
    섞이면, 줄내림을 다시 압축할 때 에이 스가 같은 인공 공백이 생기기 쉽다.
    """
    clean_lines = [list(line or []) for line in (lines or []) if _units_text(line)]
    if len(clean_lines) <= 1:
        return 0.0
    bad = 0.0

    def _word_ids(line: Sequence[_BreakUnit]) -> set[int]:
        out = set()
        for unit in line or []:
            try:
                wid = int(getattr(unit, 'word_index', -1))
            except Exception:
                wid = -1
            if wid >= 0:
                out.add(wid)
        return out

    for idx in range(len(clean_lines) - 1):
        left = clean_lines[idx]
        right = clean_lines[idx + 1]
        if not left or not right:
            continue
        try:
            l_wid = int(getattr(left[-1], 'word_index', -1))
            r_wid = int(getattr(right[0], 'word_index', -1))
        except Exception:
            continue
        if l_wid < 0 or l_wid != r_wid:
            continue
        left_ids = _word_ids(left)
        right_ids = _word_ids(right)
        # 한쪽 줄에 다른 어절이 섞이면 분할 조각이 단어처럼 보이지 않는다.
        if len(left_ids) > 1 or len(right_ids) > 1:
            bad += BADNESS_SPLIT_WORD_MIXED_LINE
    return bad

def _linebreak_candidate_score(lines: Sequence[Sequence[_BreakUnit]], *, box_ratio: float | None, target_lines: int, total_len: int) -> float:
    """줄 형상 후보 점수. 낮을수록 좋다.

    - OCR 박스 비율(box_ratio)이 있으면 max_line_len / line_count 형상이 박스 비율과 가까운지 본다.
    - 줄 길이 균형을 본다.
    - 1글자 조사 외톨이/기능 단위 내부 절단/특문 단독 줄 감점은 linebreak_badness()를 따른다.
    - 공백 기준 3글자 이하 완성 어절 본체가 여러 줄에 찢기면 금지급 감점으로 본다.
    """
    texts = [_units_text(line) for line in lines if _units_text(line)]
    if not texts:
        return 999999.0
    lengths = [max(1, visual_len(x)) for x in texts]
    line_count = max(1, len(lengths))
    target_len = max(1.0, float(total_len or sum(lengths)) / float(max(1, target_lines)))
    mean_len = max(1.0, float(sum(lengths)) / float(line_count))
    max_len = max(lengths)
    min_len = min(lengths)

    balance_cost = sum(((float(v) - mean_len) / mean_len) ** 2 for v in lengths) / float(line_count)
    short_last_cost = max(0.0, (target_len * 0.62 - float(lengths[-1])) / target_len)
    edge_punct_cost = 0.0
    for line in texts:
        st = str(line or '').strip()
        if not st:
            continue
        if st[:1] in LEADING_PUNCTUATION:
            edge_punct_cost += 1.0
        # 여는 낫표/괄호만 줄 끝에 남는 것도 좋지 않다.
        if st[-1:] in LIGHT_OPEN_PUNCTUATION:
            edge_punct_cost += 1.0

    badness_cost = _linebreak_badness_for_units(lines) + _short_word_split_badness(lines) + _split_word_mixed_line_badness(lines)

    shape_cost = 0.0
    if box_ratio is not None:
        try:
            ratio = max(0.08, min(12.0, float(box_ratio or 1.0)))
            # 실제 렌더에서는 줄 높이/행간이 있으므로 줄 수에 약간의 높이 계수를 곱한다.
            approx_shape = max(0.08, float(max_len) / max(1.0, float(line_count) * float(LINEBREAK_HEIGHT_FACTOR)))
            shape_cost = abs(math.log(approx_shape / ratio))
        except Exception:
            shape_cost = 0.0

    # 마지막 줄이 너무 긴 후보는 줄 균형에서 이미 잡히지만, 첫 줄만 지나치게 긴 경우를 조금 더 밀어낸다.
    head_heavy_cost = max(0.0, (float(lengths[0]) - float(max_len if line_count == 1 else (sum(lengths[1:]) / max(1, line_count - 1)) * 1.75)) / target_len)

    return (
        badness_cost * LINEBREAK_BADNESS_WEIGHT
        + shape_cost * LINEBREAK_SHAPE_RATIO_WEIGHT
        + balance_cost * LINEBREAK_BALANCE_WEIGHT
        + short_last_cost * LINEBREAK_LAST_LINE_SHORT_WEIGHT
        + edge_punct_cost * LINEBREAK_LIGHT_PUNCT_EDGE_WEIGHT
        + head_heavy_cost
        + (max_len - min_len) / max(1.0, target_len) * 0.12
    )


def _fallback_even_linebreak(units: Sequence[_BreakUnit], target_lines: int) -> List[List[_BreakUnit]]:
    """후보 조합이 너무 많을 때 쓰는 결정론적 균등 분할.

    0.86 조기 줄내림을 쓰지 않고, 전체 누적 길이가 각 줄 목표 누적 길이에 가장 가까운
    경계에서 끊는다.
    """
    target_lines = max(1, int(target_lines or 1))
    items = list(units or [])
    if target_lines <= 1 or len(items) <= 1:
        return [items]
    total_len = max(1, sum(max(1, visual_len(u.text)) for u in items))
    break_after: List[int] = []
    cursor_len = 0
    next_target_index = 1
    for idx, unit in enumerate(items[:-1], start=1):
        cursor_len += max(1, visual_len(unit.text))
        remaining_items = len(items) - idx
        remaining_breaks = target_lines - next_target_index
        if remaining_breaks <= 0:
            break
        if remaining_items < remaining_breaks:
            break_after.append(idx)
            next_target_index += 1
            continue
        target_cum = total_len * (next_target_index / float(target_lines))
        prev_len = cursor_len - max(1, visual_len(unit.text))
        if abs(cursor_len - target_cum) <= abs(prev_len - target_cum):
            break_after.append(idx)
            next_target_index += 1
    # 부족하면 뒤에서부터 안전하게 보충한다.
    idx = len(items) - 1
    while len(break_after) < target_lines - 1 and idx > 0:
        if idx not in break_after:
            break_after.append(idx)
        idx -= 1
    break_after = sorted(set(break_after))[:max(0, target_lines - 1)]
    lines: List[List[_BreakUnit]] = []
    start = 0
    for br in break_after:
        lines.append(list(items[start:br]))
        start = br
    lines.append(list(items[start:]))
    return [line for line in lines if line]


def _iter_linebreak_combinations(unit_count: int, target_lines: int) -> Iterable[Tuple[int, ...]]:
    """줄 경계 조합을 생성한다.

    itertools.combinations를 직접 쓰면 후보가 너무 많아질 수 있어서, 총 조합 수가 한계를
    넘으면 균등 경계 주변만 샘플링한다.
    """
    from itertools import combinations, product

    unit_count = int(unit_count or 0)
    target_lines = max(1, int(target_lines or 1))
    break_count = target_lines - 1
    if break_count <= 0 or unit_count <= 1:
        yield tuple()
        return
    max_breaks = unit_count - 1
    if break_count >= max_breaks:
        yield tuple(range(1, unit_count))
        return

    try:
        total_combo = math.comb(max_breaks, break_count)
    except Exception:
        total_combo = MAX_LINEBREAK_COMBINATION_CANDIDATES + 1
    if total_combo <= MAX_LINEBREAK_COMBINATION_CANDIDATES:
        yield from combinations(range(1, unit_count), break_count)
        return

    # 후보가 너무 많으면 각 이상적 균등 경계 주변만 본다.
    centers = [round(unit_count * i / float(target_lines)) for i in range(1, target_lines)]
    pools: List[List[int]] = []
    for c in centers:
        pool = []
        for d in (0, -1, 1, -2, 2, -3, 3):
            v = int(c + d)
            if 1 <= v <= max_breaks and v not in pool:
                pool.append(v)
        pools.append(pool or [min(max(1, int(c)), max_breaks)])
    seen = set()
    count = 0
    for combo in product(*pools):
        combo = tuple(sorted(set(int(x) for x in combo)))
        if len(combo) != break_count or combo in seen:
            continue
        seen.add(combo)
        yield combo
        count += 1
        if count >= MAX_LINEBREAK_COMBINATION_CANDIDATES:
            return


def _lines_from_breaks(units: Sequence[_BreakUnit], breaks: Sequence[int]) -> List[List[_BreakUnit]]:
    items = list(units or [])
    out: List[List[_BreakUnit]] = []
    start = 0
    for br in list(breaks or []):
        line = list(items[start:int(br)])
        if line:
            # 줄 맨 앞의 앞공백은 제거한다.
            if line[0].space_before:
                line[0] = replace(line[0], space_before=False)
            out.append(line)
        start = int(br)
    tail = list(items[start:])
    if tail:
        if tail[0].space_before:
            tail[0] = replace(tail[0], space_before=False)
        out.append(tail)
    return out


def split_to_line_count(text: object, target_lines: int, box_ratio: float | None = None) -> List[str]:
    """공백 보존 + 보호 단위 기준으로 목표 줄 수에 가깝게 나눈다.

    기존 0.86 조기 줄내림 휴리스틱은 사용하지 않는다. 가능한 줄 경계 후보를 만들고,
    OCR 박스 비율(box_ratio), 줄 길이 균형, 1글자 조사/특문/기능 단위 감점을 기준으로
    가장 나은 후보를 고른다. box_ratio를 넘기지 않은 기존 호출도 호환된다.
    """
    target_lines = max(1, int(target_lines or 1))
    units = [u for u in _make_break_units(text, target_lines=target_lines) if str(u.text or '').strip()]
    if not units:
        return ['']
    if target_lines <= 1 or len(units) <= 1:
        return [_units_text(units)]

    # 단위 수보다 많은 줄을 강제로 만들 수는 없다.
    target_lines = min(target_lines, len(units))
    total_len = max(1, sum(max(1, visual_len(u.text)) for u in units))

    best_lines: List[List[_BreakUnit]] | None = None
    best_score = float('inf')
    generated = 0
    for breaks in _iter_linebreak_combinations(len(units), target_lines):
        generated += 1
        cand_lines = _lines_from_breaks(units, breaks)
        if len(cand_lines) != target_lines:
            continue
        texts = [_units_text(line) for line in cand_lines if _units_text(line)]
        if not texts:
            continue
        score = _linebreak_candidate_score(cand_lines, box_ratio=box_ratio, target_lines=target_lines, total_len=total_len)
        if score < best_score:
            best_score = score
            best_lines = cand_lines

    if best_lines is None:
        best_lines = _fallback_even_linebreak(units, target_lines)

    result = [_units_text(line) for line in best_lines if _units_text(line)]
    return result or [str(text or '').strip()]

def would_remove_inner_spaces(raw_text: object, lines: Iterable[object]) -> bool:
    """후보 줄내림이 원문 내부 띄어쓰기를 전부 잃는지 검사한다."""
    raw = re.sub(r"\s+", " ", str(raw_text or "").strip())
    raw_space_count = len(re.findall(r"(?<=\S)\s+(?=\S)", raw))
    joined = " ".join([str(x or "").strip() for x in lines if str(x or "").strip()])
    joined_space_count = len(re.findall(r"(?<=\S)\s+(?=\S)", joined))
    return raw_space_count > 0 and joined_space_count <= 0


def candidate_score(*, touch: bool, badness: float, deficit: float, ratio_cost: float, size: int, fill_w: float, fill_h: float) -> float:
    """한국어 줄내림 후보 기본 점수. 낮을수록 좋다."""
    return (
        (0.0 if touch else SCORE_UNTOUCHED_PENALTY)
        + float(badness) * SCORE_BADNESS_WEIGHT
        + float(deficit) * SCORE_DEFICIT_WEIGHT
        + float(ratio_cost) * SCORE_RATIO_COST_WEIGHT
        - float(size) * SCORE_FONT_SIZE_REWARD
        - min(float(fill_w), HARD_WIDTH_LIMIT_RATIO) * SCORE_FILL_W_REWARD
        - min(float(fill_h), 1.00) * SCORE_FILL_H_REWARD
    )


def one_line_selection_penalty(line_count: int, compact_length: int, box_ratio: float) -> int:
    """최종 후보 선택에서 1줄 과통과를 살짝 뒤로 미는지 판단한다."""
    return 1 if (
        int(line_count or 1) <= 1
        and int(compact_length or 0) >= ONE_LINE_SELECTION_PENALTY_MIN_LEN
        and float(box_ratio or 1.0) < ONE_LINE_SELECTION_PENALTY_MAX_BOX_RATIO
    ) else 0


def candidate_select_key(candidate: dict, *, compact_length: int, box_ratio: float) -> tuple:
    """최종 후보 선택키. 큰 글자와 근접 합격 후보를 우선한다."""
    try:
        size_v = int(candidate.get("size") or 0)
    except Exception:
        size_v = 0
    try:
        fill_w_v = min(HARD_WIDTH_LIMIT_RATIO, float(candidate.get("fill_w") or 0.0))
        fill_h_v = min(1.00, float(candidate.get("fill_h") or 0.0))
    except Exception:
        fill_w_v = fill_h_v = 0.0
    try:
        deficit_v = float(candidate.get("deficit") or 0.0)
    except Exception:
        deficit_v = 9.0
    try:
        badness_v = float(candidate.get("badness") or 0.0)
    except Exception:
        badness_v = 0.0
    try:
        line_count_v = max(1, len(candidate.get("lines") or []))
    except Exception:
        line_count_v = 1
    one_line_penalty = one_line_selection_penalty(line_count_v, compact_length, box_ratio)
    # 조사/말끝/보호 단위 파손은 절대 감점 규칙이다.
    # 따라서 "박스를 잘 채운 후보"보다 "보호 단위를 깨지 않은 후보"를 먼저 고른다.
    absolute_clean = 1 if badness_v < (ABSOLUTE_BADNESS * 0.5) else 0
    return (
        absolute_clean,
        -badness_v,
        1 if (candidate.get("touch") or candidate.get("near_touch")) else 0,
        -one_line_penalty,
        -deficit_v,
        size_v,
        fill_h_v + fill_w_v * 0.35,
    )
