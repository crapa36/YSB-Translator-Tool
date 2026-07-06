from .text_input_state import TextInputState, clamp_index, selected_range, state_from_owner, apply_text_state
from .text_input_selection import has_selection, inline_selection_dirty_rect
from .text_input_navigation import (
    inline_caret_point, update_desired_caret_axis_from_current,
    line_index_for_caret, horizontal_visual_rows, nearest_visual_row_index_for_caret,
    nearest_caret_in_line_by_axis, move_horizontal_line, move_vertical_column,
)
from .text_input_commands import (
    set_caret, replace_selection, delete_backward, delete_forward,
    delete_selection_for_ime_preedit, insert_symbol, insert_inline_symbol, wrap_or_pair_quote, select_all_inline, event_is_select_all, handle_inline_text_input_shortcut, handle_key_press,
)
from .text_input_hit_test import caret_index_from_pos, cursor_rect
from .text_input_ime import (
    process_input_method_event, input_method_query, visible_preedit_text,
    plain_text_with_preedit, display_text_with_preedit,
    display_index_for_logical_caret, logical_index_for_display_char,
)
from .text_input_clipboard import (
    clipboard_plain_text_from_qt_selection, publish_plain_text_clipboard,
    copy_direct_selection_to_plain_clipboard, copy_widget_selection_to_plain_clipboard,
)
from .text_input_mouse import handle_mouse_press, handle_mouse_move, handle_mouse_release, set_initial_caret_from_scene_pos

from .text_input_lifecycle import (
    prepare_text_for_commit, push_undo_snapshot, restore_snapshot,
    perform_inline_local_undo, perform_inline_local_redo,
)
