# SPDX-License-Identifier: MIT
# @fileoverview KiCad plugin for arranging keyboard switch footprints
#               in a Grin layout with customizable curve profiles
#               and asymmetric corrections.
# @version 2025.11.0
# @author f12o
# @see https://github.com/f4ah6o/kicad-keyboard-grinner

import json
import math
import re

import pcbnew
import wx

PLUGIN_NAME = "Keyboard grinner"
PLUGIN_CATEGORY = "Modify PCB"
PLUGIN_DESCRIPTION = "For Grin layout, place selected SW footprints along a convex-down row with corner contact."

# --- Parameters -----------------------------------------------------------
UNIT_MM = 19.05  # key pitch (1u)
DEFAULT_SAG_Y_MM = 20.0  # downward sag of the lowest key [mm]
DEFAULT_END_FLAT_KEYS = 1  # number of flat keys at each end (0, 1, or 2)
DEFAULT_USE_ASYMMETRIC_CURVE = (
    True  # asymmetric curve correction for different end key widths
)
ROT_OFFSET_DEG = 0.0  # footprint orientation offset
REF_REGEX = r"^SW\d+$"  # target references
DRAW_EDGECUTS = False
DRAW_SQUARE_GUIDE = False
EDGE_WIDTH_MM = 0.1

_current_sag_y_mm = DEFAULT_SAG_Y_MM
_current_end_flat_keys = DEFAULT_END_FLAT_KEYS
_current_use_asymmetric_curve = DEFAULT_USE_ASYMMETRIC_CURVE

ANGLE_PROFILE_OPTIONS = [
    ("緩やか (コサイン)", "cosine"),
    ("自然 (ベジェ接線)", "bezier"),
    ("滑らか (二次)", "quadratic"),
]

_current_angle_profile = ANGLE_PROFILE_OPTIONS[0][1]

# --- Helpers --------------------------------------------------------------

_num_re = re.compile(r"(\d+)")
_unit_token_re = re.compile(r"(\d+(?:\.\d+)?)\s*(mm|MM|u|U)?")


def _convert_unit_token(num_str, unit_str, default_unit="u"):
    try:
        value = float(num_str)
    except (TypeError, ValueError):
        return None
    unit = (
        unit_str.lower()
        if unit_str
        else (default_unit.lower() if default_unit else None)
    )
    if not unit:
        return None
    if unit == "mm":
        return value
    if unit == "u":
        return value * UNIT_MM
    return None


def _parse_unit_pair(text):
    if not text:
        return None
    normalized = str(text).replace("×", "x")
    matches = _unit_token_re.findall(normalized)
    if not matches:
        return None
    has_unit = any(unit for (_num, unit) in matches)
    width_val = _convert_unit_token(
        matches[0][0], matches[0][1], default_unit="u" if has_unit else None
    )
    if not width_val or width_val <= 0:
        return None
    if len(matches) > 1:
        height_val = _convert_unit_token(
            matches[1][0], matches[1][1], default_unit="u" if has_unit else None
        )
        if not height_val or height_val <= 0:
            height_val = UNIT_MM
    else:
        height_val = UNIT_MM
    return width_val, height_val


def _parse_unit_value(text, default_unit="u"):
    if text is None:
        return None
    normalized = str(text).strip()
    match = _unit_token_re.search(normalized)
    if not match:
        return None
    value = _convert_unit_token(
        match.group(1), match.group(2), default_unit=default_unit
    )
    if value is None or value <= 0:
        return None
    return value


def _quantize_dim_mm(value_mm, min_units=1.0, step=0.25):
    try:
        value = float(value_mm)
    except (TypeError, ValueError):
        return min_units * UNIT_MM
    if math.isnan(value) or value <= 0.0:
        return min_units * UNIT_MM
    units = value / UNIT_MM
    units = max(min_units, units)
    units = round(units / step) * step
    if units < min_units:
        units = min_units
    return units * UNIT_MM


def infer_key_dimensions(fp):
    candidates = []
    try:
        fp_id = fp.GetFPID()
        if fp_id:
            candidates.append(fp_id.GetLibItemName())
    except AttributeError:
        pass
    try:
        candidates.append(fp.GetValue())
    except AttributeError:
        pass
    try:
        candidates.append(fp.GetDescription())
    except AttributeError:
        pass

    width_mm = None
    height_mm = None

    try:
        props = fp.GetProperties()
    except AttributeError:
        props = None
    if props and hasattr(props, "get"):
        width_mm = _parse_unit_value(props.get("KEY_WIDTH")) or _parse_unit_value(
            props.get("KeyWidth")
        )
        height_mm = _parse_unit_value(props.get("KEY_HEIGHT")) or _parse_unit_value(
            props.get("KeyHeight")
        )
        if width_mm is None and height_mm is None:
            pair = _parse_unit_pair(props.get("KEY_SIZE")) or _parse_unit_pair(
                props.get("KeySize")
            )
            if not pair:
                pair = _parse_unit_pair(props.get("KEY_DIM")) or _parse_unit_pair(
                    props.get("KeyDim")
                )
            if not pair:
                pair = _parse_unit_pair(props.get("SW_SIZE"))
            if pair:
                width_mm, height_mm = pair
        extra = props.get("SW_WIDTH")
        if width_mm is None and extra:
            width_mm = _parse_unit_value(extra)

    for text in candidates:
        if width_mm is not None and height_mm is not None:
            break
        dims = _parse_unit_pair(text)
        if dims:
            if width_mm is None:
                width_mm = dims[0]
            if height_mm is None:
                height_mm = dims[1]

    if width_mm is None or height_mm is None:
        bbox = fp.GetBoundingBox()
        if width_mm is None:
            width_mm = _quantize_dim_mm(pcbnew.ToMM(bbox.GetWidth()))
        if height_mm is None:
            height_mm = _quantize_dim_mm(pcbnew.ToMM(bbox.GetHeight()))

    if width_mm <= 0 or math.isnan(width_mm):
        width_mm = UNIT_MM
    if height_mm <= 0 or math.isnan(height_mm):
        height_mm = UNIT_MM
    return width_mm, height_mm


class RowSelectionDialog(wx.Dialog):
    """保存済み行選択ダイアログ"""

    def __init__(self, parent, saved_rows):
        super().__init__(parent, title="配置済みの行を選択")
        self._saved_rows = saved_rows

        # 説明ラベル
        label = wx.StaticText(self, label="編集する行を選択してください:")

        # プルダウン
        labels = [row['label'] for row in saved_rows]
        self._choice = wx.Choice(self, choices=labels)
        if labels:
            self._choice.SetSelection(0)

        # ボタン
        self._select_btn = wx.Button(self, wx.ID_OK, label="選択して編集")
        self._cancel_btn = wx.Button(self, wx.ID_CANCEL)
        self._select_btn.SetDefault()

        # レイアウト
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_sizer.Add(self._select_btn, 0, wx.RIGHT, 5)
        btn_sizer.Add(self._cancel_btn, 0)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(label, 0, wx.ALL, 10)
        sizer.Add(self._choice, 0, wx.ALL | wx.EXPAND, 10)
        sizer.Add(btn_sizer, 0, wx.ALL | wx.ALIGN_RIGHT, 10)

        self.SetSizerAndFit(sizer)

    def get_selected_row(self):
        """選択された行データを返す"""
        idx = self._choice.GetSelection()
        if idx >= 0:
            return self._saved_rows[idx]
        return None


class OptionsDialog(wx.Dialog):
    def __init__(
        self,
        parent,
        initial_sag,
        initial_end_flat,
        initial_profile_key,
        initial_asymmetric,
    ):
        super().__init__(parent, title="RowLayouter 設定")

        self._sag_ctrl = wx.SpinCtrlDouble(
            self, min=0.0, max=100.0, inc=0.5, initial=max(0.0, initial_sag)
        )
        self._sag_ctrl.SetDigits(2)

        self._end_ctrl = wx.SpinCtrl(self, min=0, max=2, initial=int(initial_end_flat))

        profile_labels = [label for (label, _key) in ANGLE_PROFILE_OPTIONS]
        self._profile_choice = wx.Choice(self, choices=profile_labels)
        try:
            initial_index = next(
                idx
                for idx, (_label, key) in enumerate(ANGLE_PROFILE_OPTIONS)
                if key == initial_profile_key
            )
        except StopIteration:
            initial_index = 0
        self._profile_choice.SetSelection(initial_index)

        # 非対称カーブ補正チェックボックス
        self._asymmetric_checkbox = wx.CheckBox(
            self, label="非対称カーブ補正（端キー幅の違いを補正）"
        )
        self._asymmetric_checkbox.SetValue(initial_asymmetric)

        grid = wx.FlexGridSizer(0, 2, 5, 10)
        grid.AddGrowableCol(1)
        grid.Add(wx.StaticText(self, label="下端の下げ量"), 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self._sag_ctrl, 0, wx.EXPAND)
        grid.Add(
            wx.StaticText(self, label="各端の水平キー数"), 0, wx.ALIGN_CENTER_VERTICAL
        )
        grid.Add(self._end_ctrl, 0, wx.EXPAND)
        grid.Add(
            wx.StaticText(self, label="角度プロファイル"), 0, wx.ALIGN_CENTER_VERTICAL
        )
        grid.Add(self._profile_choice, 0, wx.EXPAND)
        grid.Add(wx.StaticText(self, label=""), 0)
        grid.Add(self._asymmetric_checkbox, 0, wx.EXPAND)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self._ok_btn = wx.Button(self, wx.ID_OK)
        self._apply_btn = wx.Button(self, wx.ID_APPLY)
        self._cancel_btn = wx.Button(self, wx.ID_CANCEL)
        self._ok_btn.SetDefault()
        btn_sizer.Add(self._ok_btn, 0, wx.RIGHT, 5)
        btn_sizer.Add(self._apply_btn, 0, wx.RIGHT, 5)
        btn_sizer.Add(self._cancel_btn, 0)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(grid, 0, wx.ALL | wx.EXPAND, 15)
        sizer.Add(btn_sizer, 0, wx.ALL | wx.ALIGN_RIGHT, 10)
        self.SetSizerAndFit(sizer)

        self.Bind(wx.EVT_BUTTON, self._on_ok, self._ok_btn)
        self.Bind(wx.EVT_BUTTON, self._on_apply, self._apply_btn)
        self.Bind(wx.EVT_BUTTON, self._on_cancel, self._cancel_btn)

        self._apply_handler = None

    def get_sag(self):
        return float(self._sag_ctrl.GetValue())

    def get_end_flat(self):
        return int(self._end_ctrl.GetValue())

    def get_profile_key(self):
        idx = self._profile_choice.GetSelection()
        if 0 <= idx < len(ANGLE_PROFILE_OPTIONS):
            return ANGLE_PROFILE_OPTIONS[idx][1]
        return ANGLE_PROFILE_OPTIONS[0][1]

    def get_use_asymmetric_curve(self):
        return self._asymmetric_checkbox.GetValue()

    def set_apply_handler(self, handler):
        self._apply_handler = handler

    def _collect_parameters(self):
        return {
            "sag": self.get_sag(),
            "end_flat": self.get_end_flat(),
            "profile": self.get_profile_key(),
            "use_asymmetric_curve": self.get_use_asymmetric_curve(),
        }

    def _on_apply(self, event):
        if self._apply_handler:
            self._apply_handler(self._collect_parameters())

    def _on_ok(self, event):
        if self._apply_handler:
            if not self._apply_handler(self._collect_parameters()):
                return
        self.EndModal(wx.ID_OK)

    def _on_cancel(self, event):
        self.EndModal(wx.ID_CANCEL)


def mm(value: float) -> int:
    return pcbnew.FromMM(value)


def board_to_math(pt):
    x, y = pt
    return (x, -y)


def math_to_board(pt):
    x, y = pt
    return (x, -y)


def natural_key(ref: str):
    parts = _num_re.split(ref)
    key = []
    for part in parts:
        if part.isdigit():
            key.append(int(part))
        elif part:
            key.append(part)
    return key


def angle_profile_factor(profile_key: str, norm_distance: float) -> float:
    norm = max(0.0, min(1.0, norm_distance))
    if profile_key == "cosine":
        return math.cos((math.pi / 2.0) * norm)
    if profile_key == "quadratic":
        return max(0.0, 1.0 - norm * norm)
    return 1.0


def assign_categories(count: int, end_flat: int):
    if count <= 0:
        return []
    categories = ["lower"] * count
    if count % 2 == 1:
        center = count // 2
        categories[center] = "valley_flat"
        left_indices = list(range(0, center))
        right_indices = list(range(center + 1, count))
    else:
        center_left = count // 2 - 1
        center_right = count // 2
        categories[center_left] = "valley_upper"
        categories[center_right] = "valley_upper"
        left_indices = list(range(0, center_left))
        right_indices = list(range(center_right + 1, count))

    def mark_flats(indices, from_start):
        remaining = end_flat
        if remaining <= 0:
            return
        seq = indices if from_start else list(reversed(indices))
        for idx in seq:
            if categories[idx] != "lower":
                continue
            categories[idx] = "flat"
            remaining -= 1
            if remaining <= 0:
                break

    mark_flats(left_indices, from_start=True)
    mark_flats(right_indices, from_start=False)

    left_nonflat = [idx for idx in left_indices if categories[idx] == "lower"]
    if left_nonflat:
        categories[left_nonflat[-1]] = "upper"
        for idx in left_nonflat[:-1]:
            categories[idx] = "lower"

    right_nonflat = [idx for idx in right_indices if categories[idx] == "lower"]
    if right_nonflat:
        categories[right_nonflat[0]] = "upper"
        for idx in right_nonflat[1:]:
            categories[idx] = "lower"

    return categories


def contact_mode_from_categories(cat_prev: str, cat_curr: str) -> str:
    special = {cat_prev, cat_curr}
    if "valley_flat" in special:
        return "upper"
    if "flat" in special:
        return "lower"
    if "upper" in special or "valley_upper" in special:
        return "upper"
    return "lower"


def calculate_asymmetric_bezier_controls(
    P0, P3, sag_y_mm, left_width_mm, right_width_mm
):
    """
    左右の端キー幅に基づいて非対称ベジェ制御点を計算

    Args:
        P0: 始点 (x, y)
        P3: 終点 (x, y)
        sag_y_mm: 下げ量 (mm)
        left_width_mm: 左端キーの幅 (mm)
        right_width_mm: 右端キーの幅 (mm)

    Returns:
        (P1, P2): 非対称に調整された制御点

    計算ロジック:
        1. 非対称係数 = (left_width - right_width) / (left_width + right_width)
           範囲: -1.0 (右に偏る) ~ 0.0 (対称) ~ +1.0 (左に偏る)

        2. 制御点シフト量 = asymmetry × shift_factor (デフォルト 0.15 = 最大15%シフト)

        3. 制御点位置:
           - 対称時: P1 = 1/3, P2 = 2/3
           - 左端が広い (asymmetry > 0): P1, P2 を左にシフト
           - 右端が広い (asymmetry < 0): P1, P2 を右にシフト

        4. 縦位置 (beta) は従来通り: (4/3) × (-sag_y_mm)

    例:
        - 左1.75u, 右1.0u: asymmetry = 0.273 → 約4.1%左シフト
        - 左1.5u, 右1.0u: asymmetry = 0.2 → 約3.0%左シフト
        - 左1.0u, 右1.0u: asymmetry = 0.0 → シフトなし（対称）
    """
    row_length = P3[0] - P0[0]
    beta = (4.0 / 3.0) * (-sag_y_mm)

    # 非対称係数の計算
    total_width = left_width_mm + right_width_mm
    if total_width > 1e-6:
        asymmetry = (left_width_mm - right_width_mm) / total_width
    else:
        asymmetry = 0.0

    # シフト量（最大15%）
    shift_factor = 0.15
    shift = asymmetry * shift_factor

    # 制御点の水平位置を非対称に調整
    # P1: 左端から 1/3 ± shift の位置
    # P2: 右端から 1/3 ∓ shift の位置（左端が広いと左にシフト = 右端からの距離は大きくなる）
    p1_from_left = (1.0 / 3.0) - shift
    p2_from_right = (1.0 / 3.0) + shift  # 符号反転: 左端が広い → P2も左寄り

    P1 = (P0[0] + row_length * p1_from_left, P0[1] + beta)
    P2 = (P3[0] - row_length * p2_from_right, P3[1] + beta)

    return P1, P2


def run_with_parameters(
    board, sag_y_mm, end_flat_option, angle_profile_key, use_asymmetric_curve=False
):
    fps = gather_targets(board)
    if not fps:
        wx.MessageBox(
            "SW* 参照名の選択フットプリントがありません。",
            "RowLayouter",
            wx.OK | wx.ICON_WARNING,
        )
        return False

    N = len(fps)
    if N == 1:
        wx.MessageBox(
            "1つだけでは行を構成できません。", "RowLayouter", wx.OK | wx.ICON_WARNING
        )
        return False

    # 水平キー0の場合は旧ロジック（b286c7c）を使用
    if end_flat_option == 0:
        success = run_with_parameters_zero_flat(
            board, fps, N, sag_y_mm, angle_profile_key, use_asymmetric_curve
        )
    else:
        # 水平キー1以上の場合は新ロジック（996b4d9）を使用
        success = run_with_parameters_nonzero_flat(
            board,
            fps,
            N,
            sag_y_mm,
            end_flat_option,
            angle_profile_key,
            use_asymmetric_curve,
        )

    # 成功時にパラメータを保存
    if success:
        params = {
            'sag': sag_y_mm,
            'end_flat': end_flat_option,
            'profile': angle_profile_key,
            'use_asymmetric_curve': use_asymmetric_curve
        }
        save_parameters_to_footprint(fps[0], params, fps)

    return success


def run_with_parameters_zero_flat(
    board, fps, N, sag_y_mm, angle_profile_key, use_asymmetric_curve
):
    """水平キー0の場合の処理（b286c7cのロジック）"""
    original_centers_math = []
    for fp in fps:
        pos = fp.GetPosition()
        mm_pos = (pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y))
        original_centers_math.append(board_to_math(mm_pos))

    for fp in fps:
        fp.SetOrientationDegrees(0.0)

    key_sizes = [infer_key_dimensions(fp) for fp in fps]
    key_widths_actual = [dims[0] for dims in key_sizes]
    key_heights_actual = [dims[1] for dims in key_sizes]

    left_actual_width = key_widths_actual[0]
    left_actual_height = key_heights_actual[0]
    right_actual_width = key_widths_actual[-1]
    right_actual_height = key_heights_actual[-1]

    use_virtual_endcaps = True

    layout_widths = []
    layout_to_actual = []
    if use_virtual_endcaps:
        layout_widths.append(UNIT_MM)
        layout_to_actual.append(None)
    for idx, width in enumerate(key_widths_actual):
        layout_widths.append(width)
        layout_to_actual.append(idx)
    if use_virtual_endcaps:
        layout_widths.append(UNIT_MM)
        layout_to_actual.append(None)

    layout_N = len(layout_widths)

    base_pos = fps[0].GetPosition()
    base_mm = (pcbnew.ToMM(base_pos.x), pcbnew.ToMM(base_pos.y))
    base_math_actual = board_to_math(base_mm)
    base_math = base_math_actual

    cumulative_distances = [0.0]
    for i in range(1, layout_N):
        spacing = (layout_widths[i - 1] + layout_widths[i]) / 2.0
        cumulative_distances.append(cumulative_distances[-1] + spacing)

    row_length = cumulative_distances[-1]
    P0 = base_math
    P3 = (base_math[0] + row_length, base_math[1])

    # ベジェ制御点の計算: 非対称カーブ補正の適用
    if use_asymmetric_curve:
        # 非対称カーブ: 実際の端キー幅を使用
        P1, P2 = calculate_asymmetric_bezier_controls(
            P0, P3, sag_y_mm, left_actual_width, right_actual_width
        )
    else:
        # 従来の対称カーブ
        beta = (4.0 / 3.0) * (-sag_y_mm)
        P1 = (P0[0] + row_length / 3.0, P0[1] + beta)
        P2 = (P3[0] - row_length / 3.0, P3[1] + beta)

    ts = bezier_divide_by_distances(P0, P1, P2, P3, layout_N, cumulative_distances)
    centers = [bezier_cubic_point(t, P0, P1, P2, P3) for t in ts]

    categories_layout = assign_categories(layout_N, 0)
    if use_virtual_endcaps:
        categories_layout[0] = "flat"
        categories_layout[-1] = "flat"
    categories_actual = assign_categories(N, 0)

    base_tangent = []
    angles = []
    center_pos = (layout_N - 1) / 2.0 if layout_N > 1 else 0.0
    max_dist = center_pos if center_pos > 0 else 1.0
    for idx, t in enumerate(ts):
        dx, dy = bezier_cubic_tangent(t, P0, P1, P2, P3)
        ang = math.atan2(dy, dx)
        base_tangent.append(ang)
        norm = abs(idx - center_pos) / max_dist
        factor = angle_profile_factor(angle_profile_key, norm)
        cat = categories_layout[idx]
        if cat in ("flat", "valley_flat"):
            adj_ang = 0.0
        else:
            adj_ang = ang * factor
        angles.append(adj_ang)

    angles = [ang + math.radians(ROT_OFFSET_DEG) for ang in angles]

    for idx in range(1, layout_N):
        prev_center = centers[idx - 1]
        prev_angle = angles[idx - 1]
        curr_angle = angles[idx]
        prev_width = layout_widths[idx - 1]
        curr_width = layout_widths[idx]
        mode = contact_mode_from_categories(
            categories_layout[idx - 1], categories_layout[idx]
        )
        avg = math.atan2(
            math.sin(base_tangent[idx - 1]) + math.sin(base_tangent[idx]),
            math.cos(base_tangent[idx - 1]) + math.cos(base_tangent[idx]),
        )
        fwd = (math.cos(avg), math.sin(avg))
        centers[idx] = place_with_corner_contact(
            prev_center, prev_angle, curr_angle, prev_width, curr_width, mode, fwd
        )

    actual_centers = []
    actual_angles = []
    for layout_idx, actual_idx in enumerate(layout_to_actual):
        if actual_idx is None:
            continue
        actual_centers.append(centers[layout_idx])
        actual_angles.append(angles[layout_idx])

    if actual_centers:
        base_y = actual_centers[0][1]
        for idx, cat in enumerate(categories_actual):
            if cat == "flat" and idx > 0:
                actual_centers[idx] = (actual_centers[idx][0], base_y)
        if len(actual_centers) > 1:
            actual_centers[-1] = (actual_centers[-1][0], base_y)

    if (
        actual_centers
        and not use_virtual_endcaps
        and abs(left_actual_width - UNIT_MM) > 1e-6
    ):
        angle_left = actual_angles[0]
        virtual_offset = rot2d(UNIT_MM / 2.0, -left_actual_height / 2.0, angle_left)
        actual_offset = rot2d(
            left_actual_width / 2.0, -left_actual_height / 2.0, angle_left
        )
        delta_left = (
            virtual_offset[0] - actual_offset[0],
            virtual_offset[1] - actual_offset[1],
        )
        actual_centers[0] = (
            actual_centers[0][0] + delta_left[0],
            actual_centers[0][1] + delta_left[1],
        )

    if (
        actual_centers
        and not use_virtual_endcaps
        and abs(right_actual_width - UNIT_MM) > 1e-6
    ):
        angle_right = actual_angles[-1]
        virtual_offset = rot2d(-UNIT_MM / 2.0, -right_actual_height / 2.0, angle_right)
        actual_offset = rot2d(
            -right_actual_width / 2.0, -right_actual_height / 2.0, angle_right
        )
        delta_right = (
            virtual_offset[0] - actual_offset[0],
            virtual_offset[1] - actual_offset[1],
        )
        actual_centers[-1] = (
            actual_centers[-1][0] + delta_right[0],
            actual_centers[-1][1] + delta_right[1],
        )

    if actual_centers and not use_virtual_endcaps:
        desired_center = original_centers_math[0]
        current_center = actual_centers[0]
        translation = (
            desired_center[0] - current_center[0],
            desired_center[1] - current_center[1],
        )
        if abs(translation[0]) > 1e-9 or abs(translation[1]) > 1e-9:
            actual_centers = [
                (c[0] + translation[0], c[1] + translation[1]) for c in actual_centers
            ]

    if actual_centers:
        delta_x = actual_centers[0][0] - original_centers_math[0][0]
        delta_y = actual_centers[0][1] - original_centers_math[0][1]
        if abs(delta_x) > 1e-9 or abs(delta_y) > 1e-9:
            actual_centers = [(c[0] - delta_x, c[1] - delta_y) for c in actual_centers]

    if DRAW_EDGECUTS:
        poly = [bezier_cubic_point(i / 100.0, P0, P1, P2, P3) for i in range(101)]
        draw_polyline_math(board, poly, pcbnew.Edge_Cuts, EDGE_WIDTH_MM, closed=False)
        if DRAW_SQUARE_GUIDE:
            for center_math, ang, dims in zip(actual_centers, actual_angles, key_sizes):
                draw_polyline_math(
                    board,
                    square_corners_math(center_math, dims[0], dims[1], ang),
                    pcbnew.Edge_Cuts,
                    EDGE_WIDTH_MM,
                    closed=True,
                )

    for fp, center_math, angle in zip(fps, actual_centers, actual_angles):
        center_board = math_to_board(center_math)
        fp.SetPosition(pcbnew.VECTOR2I(mm(center_board[0]), mm(center_board[1])))
        fp.SetOrientationDegrees(math.degrees(angle))
        fp.SetLocked(False)

    pcbnew.Refresh()
    return True


def run_with_parameters_nonzero_flat(
    board, fps, N, sag_y_mm, end_flat_option, angle_profile_key, use_asymmetric_curve
):
    """水平キー1以上の場合の処理（996b4d9のロジック）"""
    for fp in fps:
        fp.SetOrientationDegrees(0.0)

    key_sizes = [infer_key_dimensions(fp) for fp in fps]
    key_widths_mm = [dims[0] for dims in key_sizes]
    key_heights_mm = [dims[1] for dims in key_sizes]

    left_actual_width = key_widths_mm[0]
    left_actual_height = key_heights_mm[0]
    right_actual_width = key_widths_mm[-1]
    right_actual_height = key_heights_mm[-1]

    virtual_widths = key_widths_mm.copy()
    if abs(left_actual_width - UNIT_MM) > 1e-6:
        virtual_widths[0] = UNIT_MM
    if abs(right_actual_width - UNIT_MM) > 1e-6:
        virtual_widths[-1] = UNIT_MM

    base_pos = fps[0].GetPosition()
    base_mm = (pcbnew.ToMM(base_pos.x), pcbnew.ToMM(base_pos.y))
    base_math_actual = board_to_math(base_mm)
    if abs(virtual_widths[0] - left_actual_width) > 1e-6:
        base_math = (
            base_math_actual[0] + (left_actual_width - virtual_widths[0]) / 2.0,
            base_math_actual[1],
        )
    else:
        base_math = base_math_actual

    cumulative_distances = [0.0]
    for i in range(1, N):
        spacing = (virtual_widths[i - 1] + virtual_widths[i]) / 2.0
        cumulative_distances.append(cumulative_distances[-1] + spacing)

    row_length = cumulative_distances[-1]
    P0 = base_math
    P3 = (base_math[0] + row_length, base_math[1])

    # ベジェ制御点の計算: 非対称カーブ補正の適用
    if use_asymmetric_curve:
        # 非対称カーブ: 実際の端キー幅を使用
        P1, P2 = calculate_asymmetric_bezier_controls(
            P0, P3, sag_y_mm, left_actual_width, right_actual_width
        )
    else:
        # 従来の対称カーブ
        beta = (4.0 / 3.0) * (-sag_y_mm)
        P1 = (P0[0] + row_length / 3.0, P0[1] + beta)
        P2 = (P3[0] - row_length / 3.0, P3[1] + beta)

    ts = bezier_divide_by_distances(P0, P1, P2, P3, N, cumulative_distances)
    centers = [bezier_cubic_point(t, P0, P1, P2, P3) for t in ts]

    categories = assign_categories(N, end_flat_option)

    base_tangent = []
    angles = []
    center_pos = (N - 1) / 2.0 if N > 1 else 0.0
    max_dist = center_pos if center_pos > 0 else 1.0
    for idx, t in enumerate(ts):
        dx, dy = bezier_cubic_tangent(t, P0, P1, P2, P3)
        ang = math.atan2(dy, dx)
        base_tangent.append(ang)
        norm = abs(idx - center_pos) / max_dist
        factor = angle_profile_factor(angle_profile_key, norm)
        cat = categories[idx]
        if cat in ("flat", "valley_flat"):
            adj_ang = 0.0
        else:
            adj_ang = ang * factor
        angles.append(adj_ang)

    angles = [ang + math.radians(ROT_OFFSET_DEG) for ang in angles]

    for idx in range(1, N):
        prev_center = centers[idx - 1]
        prev_angle = angles[idx - 1]
        curr_angle = angles[idx]
        prev_width = virtual_widths[idx - 1]
        curr_width = virtual_widths[idx]
        mode = contact_mode_from_categories(categories[idx - 1], categories[idx])
        avg = math.atan2(
            math.sin(base_tangent[idx - 1]) + math.sin(base_tangent[idx]),
            math.cos(base_tangent[idx - 1]) + math.cos(base_tangent[idx]),
        )
        fwd = (math.cos(avg), math.sin(avg))
        centers[idx] = place_with_corner_contact(
            prev_center, prev_angle, curr_angle, prev_width, curr_width, mode, fwd
        )

    if N > 0:
        base_y = centers[0][1]
        for idx in range(N):
            if categories[idx] == "flat" and idx > 0:
                centers[idx] = (centers[idx][0], base_y)

    if abs(left_actual_width - UNIT_MM) > 1e-6:
        angle_left = angles[0]
        virtual_offset = rot2d(UNIT_MM / 2.0, -left_actual_height / 2.0, angle_left)
        actual_offset = rot2d(
            left_actual_width / 2.0, -left_actual_height / 2.0, angle_left
        )
        delta_left = (
            virtual_offset[0] - actual_offset[0],
            virtual_offset[1] - actual_offset[1],
        )
        centers[0] = (centers[0][0] + delta_left[0], centers[0][1] + delta_left[1])

    if abs(right_actual_width - UNIT_MM) > 1e-6:
        angle_right = angles[-1]
        virtual_offset = rot2d(-UNIT_MM / 2.0, -right_actual_height / 2.0, angle_right)
        actual_offset = rot2d(
            -right_actual_width / 2.0, -right_actual_height / 2.0, angle_right
        )
        delta_right = (
            virtual_offset[0] - actual_offset[0],
            virtual_offset[1] - actual_offset[1],
        )
        centers[-1] = (centers[-1][0] + delta_right[0], centers[-1][1] + delta_right[1])

    if DRAW_EDGECUTS:
        poly = [bezier_cubic_point(i / 100.0, P0, P1, P2, P3) for i in range(101)]
        draw_polyline_math(board, poly, pcbnew.Edge_Cuts, EDGE_WIDTH_MM, closed=False)
        if DRAW_SQUARE_GUIDE:
            for center_math, ang, dims in zip(centers, angles, key_sizes):
                draw_polyline_math(
                    board,
                    square_corners_math(center_math, dims[0], dims[1], ang),
                    pcbnew.Edge_Cuts,
                    EDGE_WIDTH_MM,
                    closed=True,
                )

    for fp, center_math, angle in zip(fps, centers, angles):
        center_board = math_to_board(center_math)
        fp.SetPosition(pcbnew.VECTOR2I(mm(center_board[0]), mm(center_board[1])))
        fp.SetOrientationDegrees(math.degrees(angle))
        fp.SetLocked(False)

    pcbnew.Refresh()
    return True


def bezier_cubic_point(t, P0, P1, P2, P3):
    u = 1.0 - t
    return (
        u * u * u * P0[0]
        + 3 * u * u * t * P1[0]
        + 3 * u * t * t * P2[0]
        + t * t * t * P3[0],
        u * u * u * P0[1]
        + 3 * u * u * t * P1[1]
        + 3 * u * t * t * P2[1]
        + t * t * t * P3[1],
    )


def bezier_cubic_tangent(t, P0, P1, P2, P3):
    u = 1.0 - t
    dx = (
        3 * u * u * (P1[0] - P0[0])
        + 6 * u * t * (P2[0] - P1[0])
        + 3 * t * t * (P3[0] - P2[0])
    )
    dy = (
        3 * u * u * (P1[1] - P0[1])
        + 6 * u * t * (P2[1] - P1[1])
        + 3 * t * t * (P3[1] - P2[1])
    )
    return dx, dy


def bezier_divide_by_arclen(P0, P1, P2, P3, count):
    """等間隔でN個に分割 (後方互換性のため残す)"""
    if count <= 1:
        return [0.0]
    return bezier_divide_by_distances(P0, P1, P2, P3, count, None)


def bezier_divide_by_distances(P0, P1, P2, P3, count, cumulative_distances=None):
    """
    ベジェ曲線を指定した累積距離配列に基づいて分割

    Args:
        P0, P1, P2, P3: ベジェ曲線の制御点
        count: 分割数
        cumulative_distances: 各点までの累積距離のリスト (Noneの場合は等間隔)

    Returns:
        各点に対応するパラメータtのリスト
    """
    if count <= 1:
        return [0.0]

    samples = 800
    pts = [
        bezier_cubic_point(i / (samples - 1), P0, P1, P2, P3) for i in range(samples)
    ]
    lengths = [0.0]
    total = 0.0
    for idx in range(1, samples):
        dx = pts[idx][0] - pts[idx - 1][0]
        dy = pts[idx][1] - pts[idx - 1][1]
        seg = math.hypot(dx, dy)
        total += seg
        lengths.append(total)

    # 累積距離が指定されていない場合は等間隔
    if cumulative_distances is None:
        cumulative_distances = [total * (k / (count - 1)) for k in range(count)]
    else:
        # 正規化: 累積距離を曲線の総弧長にスケール
        max_dist = cumulative_distances[-1] if cumulative_distances[-1] > 0 else 1.0
        cumulative_distances = [(d / max_dist) * total for d in cumulative_distances]

    ts = []
    for target in cumulative_distances:
        lo, hi = 0, samples - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if lengths[mid] < target:
                lo = mid + 1
            else:
                hi = mid
        ts.append(lo / (samples - 1))
    return ts


def rot2d(x, y, angle_rad):
    c = math.cos(angle_rad)
    s = math.sin(angle_rad)
    return (x * c - y * s, x * s + y * c)


def square_corners_math(center, width, height, angle_rad):
    cx, cy = center
    hw = width / 2.0
    hh = height / 2.0
    base = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]
    rotated = [rot2d(x, y, angle_rad) for (x, y) in base]
    return [(cx + px, cy + py) for (px, py) in rotated]


def add_segment_math(board, p1_math, p2_math, layer, width_mm):
    p1_board = math_to_board(p1_math)
    p2_board = math_to_board(p2_math)
    seg = pcbnew.PCB_SHAPE(board)
    seg.SetShape(pcbnew.S_SEGMENT)
    seg.SetLayer(layer)
    seg.SetWidth(mm(width_mm))
    seg.SetStart(pcbnew.VECTOR2I(mm(p1_board[0]), mm(p1_board[1])))
    seg.SetEnd(pcbnew.VECTOR2I(mm(p2_board[0]), mm(p2_board[1])))
    board.Add(seg)
    return seg


def draw_polyline_math(board, pts_math, layer, width_mm, closed=False):
    count = len(pts_math)
    last = count if closed else count - 1
    for idx in range(last):
        add_segment_math(
            board, pts_math[idx], pts_math[(idx + 1) % count], layer, width_mm
        )


def corner_point_math(center, width, height, angle, label):
    hw = width / 2.0
    hh = height / 2.0
    offsets = {
        "UL": (-hw, hh),
        "UR": (hw, hh),
        "LL": (-hw, -hh),
        "LR": (hw, -hh),
    }
    ox, oy = offsets[label]
    rx, ry = rot2d(ox, oy, angle)
    return (center[0] + rx, center[1] + ry)


def get_lower_upper_labels(angle, width, height):
    labels = ["UL", "UR", "LL", "LR"]
    # convert to board orientation by inspecting math Y (lower on board => smaller math Y)
    pts = {
        lab: corner_point_math((0.0, 0.0), width, height, angle, lab) for lab in labels
    }
    sorted_labels = sorted(labels, key=lambda lab: pts[lab][1])
    lower = sorted_labels[:2]
    upper = sorted_labels[2:]
    return lower, upper


def place_with_corner_contact(
    prev_center, prev_angle, curr_angle, prev_width, curr_width, mode, forward
):
    # 高さは常に1u (UNIT_MM)
    height = UNIT_MM
    lower_prev, upper_prev = get_lower_upper_labels(prev_angle, prev_width, height)
    lower_curr, upper_curr = get_lower_upper_labels(curr_angle, curr_width, height)
    prev_labels = lower_prev if mode == "lower" else upper_prev
    curr_labels = lower_curr if mode == "lower" else upper_curr

    # 理想的な中心間距離 = 前キーの半幅 + 現キーの半幅
    target = (prev_width + curr_width) / 2.0
    best = None
    for lp in prev_labels:
        p_corner = corner_point_math(prev_center, prev_width, height, prev_angle, lp)
        for lc in curr_labels:
            rel_corner = corner_point_math(
                (0.0, 0.0), curr_width, height, curr_angle, lc
            )
            candidate = (p_corner[0] - rel_corner[0], p_corner[1] - rel_corner[1])
            dx = candidate[0] - prev_center[0]
            dy = candidate[1] - prev_center[1]
            dist = math.hypot(dx, dy)
            forward_dist = dx * forward[0] + dy * forward[1]
            score = 1000.0 * forward_dist - abs(dist - target)
            if forward_dist < 0:
                score -= 1e6
            if dist < 0.6 * target:
                score -= 1e5
            if best is None or score > best[0]:
                best = (score, candidate)
    if best is None:
        return (
            prev_center[0] + forward[0] * target,
            prev_center[1] + forward[1] * target,
        )
    return best[1]


def save_parameters_to_footprint(first_fp, params, target_fps):
    """
    左端フットプリントにパラメータを保存

    Args:
        first_fp: 左端フットプリント
        params: 保存するパラメータ dict
        target_fps: 対象フットプリントのリスト
    """
    try:
        props = first_fp.GetProperties()
        data = params.copy()
        refs = [fp.GetReference() for fp in target_fps]
        data['footprints'] = refs
        data['row_name'] = f"{refs[0]}〜{refs[-1]}"
        data['version'] = '2025.11.0'
        props['grinner_params'] = json.dumps(data, ensure_ascii=False)
        first_fp.SetPropertiesNative(props)
    except Exception as e:
        print(f"Failed to save parameters: {e}")


def find_saved_rows(board):
    """
    ボードから保存済み行を検出

    Args:
        board: pcbnew.BOARD

    Returns:
        list: 保存済み行のリスト
    """
    saved_rows = []
    for fp in board.GetFootprints():
        props = fp.GetProperties()
        if 'grinner_params' in props:
            try:
                data = json.loads(props['grinner_params'])
                saved_rows.append({
                    'first_fp': fp,
                    'data': data,
                    'label': f"{data.get('row_name', 'Unknown')} ({len(data.get('footprints', []))}個)"
                })
            except json.JSONDecodeError:
                continue
    return saved_rows


def reselect_footprints_from_data(board, data):
    """
    保存されたフットプリントリストを再選択

    Args:
        board: pcbnew.BOARD
        data: 保存されたパラメータ dict

    Returns:
        int: 選択されたフットプリント数
    """
    if 'footprints' not in data:
        return 0

    target_refs = set(data['footprints'])
    count = 0

    # 既存選択をクリア
    for fp in board.GetFootprints():
        fp.SetSelected(False)

    # 対象を選択
    for fp in board.GetFootprints():
        if fp.GetReference() in target_refs:
            fp.SetSelected(True)
            count += 1

    return count


def gather_targets(board):
    selected = [fp for fp in board.GetFootprints() if fp.IsSelected()]
    regex = re.compile(REF_REGEX)
    targets = [fp for fp in selected if regex.match(fp.GetReference() or "")]
    targets.sort(key=lambda fp: natural_key(fp.GetReference()))
    return targets


# --- Plugin ---------------------------------------------------------------


class GrinArrayPlaceRow(pcbnew.ActionPlugin):
    def defaults(self):
        self.name = PLUGIN_NAME
        self.category = PLUGIN_CATEGORY
        self.description = PLUGIN_DESCRIPTION

    def Run(self):
        board = pcbnew.GetBoard()

        parent = None
        try:
            parent = pcbnew.GetFrame()
        except AttributeError:
            parent = wx.GetActiveWindow()

        # 現在の選択をチェック
        selected = [fp for fp in board.GetFootprints() if fp.IsSelected()]

        initial_params = None

        if not selected:
            # 選択なし → 行選択ダイアログを表示
            saved_rows = find_saved_rows(board)

            if not saved_rows:
                # 保存行なし
                wx.MessageBox(
                    "SW* 参照名のフットプリントを選択してから実行してください。",
                    "Keyboard grinner",
                    wx.OK | wx.ICON_INFORMATION
                )
                return

            # 行選択ダイアログ
            row_dialog = RowSelectionDialog(parent, saved_rows)
            result = row_dialog.ShowModal()

            if result != wx.ID_OK:
                row_dialog.Destroy()
                return

            # 選択された行のフットプリントを選択
            selected_row = row_dialog.get_selected_row()
            row_dialog.Destroy()

            if not selected_row:
                return

            count = reselect_footprints_from_data(board, selected_row['data'])
            pcbnew.Refresh()

            if count == 0:
                wx.MessageBox(
                    "保存されたフットプリントが見つかりませんでした。",
                    "Keyboard grinner",
                    wx.OK | wx.ICON_WARNING
                )
                return

            # 保存されたパラメータを初期値として使用
            initial_params = selected_row['data']

        # パラメータダイアログを開く
        global _current_sag_y_mm, _current_end_flat_keys, _current_angle_profile, _current_use_asymmetric_curve

        # 初期値の決定
        if initial_params:
            sag = initial_params.get('sag', _current_sag_y_mm)
            end_flat = initial_params.get('end_flat', _current_end_flat_keys)
            profile = initial_params.get('profile', _current_angle_profile)
            asymmetric = initial_params.get('use_asymmetric_curve', _current_use_asymmetric_curve)
        else:
            sag = _current_sag_y_mm
            end_flat = _current_end_flat_keys
            profile = _current_angle_profile
            asymmetric = _current_use_asymmetric_curve

        dialog = OptionsDialog(parent, sag, end_flat, profile, asymmetric)

        def handle_apply(params):
            global _current_sag_y_mm, _current_end_flat_keys, _current_angle_profile, _current_use_asymmetric_curve
            sag_val = max(0.0, params["sag"])
            end_flat_val = max(0, min(2, int(params["end_flat"])))
            profile_key = params["profile"]
            use_async = params["use_asymmetric_curve"]

            success = run_with_parameters(
                board, sag_val, end_flat_val, profile_key, use_async
            )

            if success:
                _current_sag_y_mm = sag_val
                _current_end_flat_keys = end_flat_val
                _current_angle_profile = profile_key
                _current_use_asymmetric_curve = use_async

            return success

        dialog.set_apply_handler(handle_apply)
        result = dialog.ShowModal()
        dialog.Destroy()

        if result == wx.ID_CANCEL:
            return


GrinArrayPlaceRow().register()
