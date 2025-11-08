# SPDX-License-Identifier: MIT
# @fileoverview KiCad plugin for arranging keyboard switch footprints
#               in a Grin layout with customizable curve profiles
#               and asymmetric corrections.
# @version 2025.10.2
# @author f12o
# @see https://github.com/f4ah6o/kicad-keyboard-grinner

import re

import pcbnew
import wx

from .dialogs import OptionsDialog, RowSelectionDialog
from .footprint_fields import (
    find_saved_rows,
    infer_key_dimensions,
    reselect_footprints_from_data,
    save_parameters_to_footprint,
)
from .geometry import (
    bezier_cubic_point,
    bezier_divide_by_distances,
    board_to_math,
)
from .layout_calculator import (
    apply_corner_contact_adjustments,
    apply_end_key_width_corrections,
    apply_flat_key_adjustments,
    apply_position_to_origin,
    apply_positions_to_footprints,
    assign_categories,
    calculate_angles_from_tangents,
    calculate_bezier_controls,
    draw_debug_geometry,
    get_original_centers_math,
)
from .unit_parsing import UNIT_MM

PLUGIN_NAME = "Keyboard grinner"
PLUGIN_CATEGORY = "Modify PCB"
PLUGIN_DESCRIPTION = "For Grin layout, place selected SW footprints along a convex-down row with corner contact."

# --- Parameters -----------------------------------------------------------
DEFAULT_SAG_Y_MM = 20.0  # downward sag of the lowest key [mm]
DEFAULT_END_FLAT_KEYS = 1  # number of flat keys at each end (0, 1, or 2)
DEFAULT_USE_ASYMMETRIC_CURVE = (
    False  # asymmetric curve correction for different end key widths
)
REF_REGEX = r"^SW\d+$"  # target references

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


def natural_key(ref: str):
    """Natural sorting key for reference strings."""
    parts = _num_re.split(ref)
    key = []
    for part in parts:
        if part.isdigit():
            key.append(int(part))
        elif part:
            key.append(part)
    return key


def gather_targets(board):
    """Gather target footprints from board selection."""
    selected = [fp for fp in board.GetFootprints() if fp.IsSelected()]
    regex = re.compile(REF_REGEX)
    targets = [fp for fp in selected if regex.match(fp.GetReference() or "")]
    targets.sort(key=lambda fp: natural_key(fp.GetReference()))
    return targets


def run_with_parameters(
    board, sag_y_mm, end_flat_option, angle_profile_key, use_asymmetric_curve=False
):
    """
    Run layout calculation with given parameters.

    Args:
        board: pcbnew.BOARD object
        sag_y_mm: Downward sag amount
        end_flat_option: Number of flat keys at each end
        angle_profile_key: Angle profile type
        use_asymmetric_curve: Whether to use asymmetric curve correction

    Returns:
        True if successful, False otherwise
    """
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

    # Use old logic (b286c7c) for 0 flat keys, new logic (996b4d9) for 1+ flat keys
    if end_flat_option == 0:
        success = run_with_parameters_zero_flat(
            board, fps, N, sag_y_mm, angle_profile_key, use_asymmetric_curve
        )
    else:
        success = run_with_parameters_nonzero_flat(
            board,
            fps,
            N,
            sag_y_mm,
            end_flat_option,
            angle_profile_key,
            use_asymmetric_curve,
        )

    # Save parameters on success
    if success:
        params = {
            "sag": sag_y_mm,
            "end_flat": end_flat_option,
            "profile": angle_profile_key,
            "use_asymmetric_curve": use_asymmetric_curve,
        }
        save_parameters_to_footprint(fps[0], params, fps)

    return success


def run_with_parameters_zero_flat(
    board, fps, N, sag_y_mm, angle_profile_key, use_asymmetric_curve
):
    """Layout calculation for 0 flat keys (b286c7c logic)."""
    # Reset orientations
    for fp in fps:
        fp.SetOrientationDegrees(0.0)

    # Infer key dimensions
    key_sizes = [infer_key_dimensions(fp) for fp in fps]
    key_widths_actual = [dims[0] for dims in key_sizes]
    key_heights_actual = [dims[1] for dims in key_sizes]

    left_actual_width = key_widths_actual[0]
    right_actual_width = key_widths_actual[-1]

    # Use virtual endcaps
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

    # Calculate base position
    base_pos = fps[0].GetPosition()
    base_mm = (pcbnew.ToMM(base_pos.x), pcbnew.ToMM(base_pos.y))
    base_math_actual = board_to_math(base_mm)
    base_math = base_math_actual

    # Calculate cumulative distances
    cumulative_distances = [0.0]
    for i in range(1, layout_N):
        spacing = (layout_widths[i - 1] + layout_widths[i]) / 2.0
        cumulative_distances.append(cumulative_distances[-1] + spacing)

    row_length = cumulative_distances[-1]
    P0 = base_math
    P3 = (base_math[0] + row_length, base_math[1])

    # Calculate Bezier control points
    P1, P2 = calculate_bezier_controls(
        P0, P3, sag_y_mm, left_actual_width, right_actual_width, use_asymmetric_curve
    )

    # Divide Bezier curve
    ts = bezier_divide_by_distances(P0, P1, P2, P3, layout_N, cumulative_distances)
    centers = [bezier_cubic_point(t, P0, P1, P2, P3) for t in ts]

    # Assign categories
    categories_layout = assign_categories(layout_N, 0)
    if use_virtual_endcaps:
        categories_layout[0] = "flat"
        categories_layout[-1] = "flat"

    # Calculate angles
    base_tangent, angles = calculate_angles_from_tangents(
        ts, P0, P1, P2, P3, layout_N, angle_profile_key, categories_layout
    )

    # Apply corner contact adjustments
    centers = apply_corner_contact_adjustments(
        centers, angles, layout_widths, categories_layout, base_tangent, layout_N
    )

    # Extract actual centers and angles
    actual_centers = []
    actual_angles = []
    for layout_idx, actual_idx in enumerate(layout_to_actual):
        if actual_idx is None:
            continue
        actual_centers.append(centers[layout_idx])
        actual_angles.append(angles[layout_idx])

    # Flatten flat keys
    if actual_centers:
        base_y = actual_centers[0][1]
        categories_actual = assign_categories(N, 0)
        for idx, cat in enumerate(categories_actual):
            if cat == "flat" and idx > 0:
                actual_centers[idx] = (actual_centers[idx][0], base_y)
        if len(actual_centers) > 1:
            actual_centers[-1] = (actual_centers[-1][0], base_y)

    # Apply end key width corrections (only if not using virtual endcaps)
    if actual_centers and not use_virtual_endcaps:
        actual_centers = apply_end_key_width_corrections(
            actual_centers,
            actual_angles,
            key_widths_actual,
            key_heights_actual,
            left_actual_width,
            right_actual_width,
        )

    # Translate to keep first key at original position (only if not using virtual endcaps)
    if actual_centers and not use_virtual_endcaps:
        desired_center = get_original_centers_math(fps)[0]
        current_center = actual_centers[0]
        translation = (
            desired_center[0] - current_center[0],
            desired_center[1] - current_center[1],
        )
        if abs(translation[0]) > 1e-9 or abs(translation[1]) > 1e-9:
            actual_centers = [
                (c[0] + translation[0], c[1] + translation[1]) for c in actual_centers
            ]

    # Final translation to origin
    actual_centers = apply_position_to_origin(
        actual_centers, get_original_centers_math(fps)
    )

    # Draw debug geometry
    draw_debug_geometry(board, P0, P1, P2, P3, actual_centers, actual_angles, key_sizes)

    # Apply positions to footprints
    apply_positions_to_footprints(fps, actual_centers, actual_angles)

    pcbnew.Refresh()
    return True


def run_with_parameters_nonzero_flat(
    board, fps, N, sag_y_mm, end_flat_option, angle_profile_key, use_asymmetric_curve
):
    """Layout calculation for 1+ flat keys (996b4d9 logic)."""
    # Reset orientations
    for fp in fps:
        fp.SetOrientationDegrees(0.0)

    # Infer key dimensions
    key_sizes = [infer_key_dimensions(fp) for fp in fps]
    key_widths_mm = [dims[0] for dims in key_sizes]
    key_heights_mm = [dims[1] for dims in key_sizes]

    left_actual_width = key_widths_mm[0]
    right_actual_width = key_widths_mm[-1]

    # Create virtual widths
    virtual_widths = key_widths_mm.copy()
    if abs(left_actual_width - UNIT_MM) > 1e-6:
        virtual_widths[0] = UNIT_MM
    if abs(right_actual_width - UNIT_MM) > 1e-6:
        virtual_widths[-1] = UNIT_MM

    # Calculate base position
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

    # Calculate cumulative distances
    cumulative_distances = [0.0]
    for i in range(1, N):
        spacing = (virtual_widths[i - 1] + virtual_widths[i]) / 2.0
        cumulative_distances.append(cumulative_distances[-1] + spacing)

    row_length = cumulative_distances[-1]
    P0 = base_math
    P3 = (base_math[0] + row_length, base_math[1])

    # Calculate Bezier control points
    P1, P2 = calculate_bezier_controls(
        P0, P3, sag_y_mm, left_actual_width, right_actual_width, use_asymmetric_curve
    )

    # Divide Bezier curve
    ts = bezier_divide_by_distances(P0, P1, P2, P3, N, cumulative_distances)
    centers = [bezier_cubic_point(t, P0, P1, P2, P3) for t in ts]

    # Assign categories
    categories = assign_categories(N, end_flat_option)

    # Calculate angles
    base_tangent, angles = calculate_angles_from_tangents(
        ts, P0, P1, P2, P3, N, angle_profile_key, categories
    )

    # Apply corner contact adjustments
    centers = apply_corner_contact_adjustments(
        centers, angles, virtual_widths, categories, base_tangent, N
    )

    # Apply end key width corrections before flat key adjustments
    centers = apply_end_key_width_corrections(
        centers,
        angles,
        key_widths_mm,
        key_heights_mm,
        left_actual_width,
        right_actual_width,
    )

    # Apply flat key y-coordinate adjustments
    centers = apply_flat_key_adjustments(centers, categories, N)

    # Draw debug geometry
    draw_debug_geometry(board, P0, P1, P2, P3, centers, angles, key_sizes)

    # Apply positions to footprints
    apply_positions_to_footprints(fps, centers, angles)

    pcbnew.Refresh()
    return True


# --- Plugin ---------------------------------------------------------------


class GrinArrayPlaceRow(pcbnew.ActionPlugin):
    """KiCad action plugin for Grin keyboard layout."""

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

        # Check current selection
        selected = [fp for fp in board.GetFootprints() if fp.IsSelected()]

        initial_params = None

        if not selected:
            # No selection → Show row selection dialog
            saved_rows = find_saved_rows(board)

            if not saved_rows:
                # No saved rows
                wx.MessageBox(
                    "保存済みの行が見つかりません。先に対象の SW フットプリントを選択して配置を実行してください。",
                    "Keyboard grinner",
                    wx.OK | wx.ICON_INFORMATION,
                )
                return

            # Row selection dialog
            row_dialog = RowSelectionDialog(parent, saved_rows)
            result = row_dialog.ShowModal()

            if result != wx.ID_OK:
                row_dialog.Destroy()
                return

            # Select footprints from selected row
            selected_row = row_dialog.get_selected_row()
            row_dialog.Destroy()

            if not selected_row:
                return

            count = reselect_footprints_from_data(board, selected_row["data"])
            pcbnew.Refresh()

            if count == 0:
                wx.MessageBox(
                    "保存されたフットプリントが見つかりませんでした。",
                    "Keyboard grinner",
                    wx.OK | wx.ICON_WARNING,
                )
                return

            # Use saved parameters as initial values
            initial_params = selected_row["data"]

        # Open parameter dialog
        global _current_sag_y_mm, _current_end_flat_keys, _current_angle_profile, _current_use_asymmetric_curve

        # Determine initial values
        if initial_params:
            sag = initial_params.get("sag", _current_sag_y_mm)
            end_flat = initial_params.get("end_flat", _current_end_flat_keys)
            profile = initial_params.get("profile", _current_angle_profile)
            asymmetric = initial_params.get(
                "use_asymmetric_curve", _current_use_asymmetric_curve
            )
        else:
            sag = _current_sag_y_mm
            end_flat = _current_end_flat_keys
            profile = _current_angle_profile
            asymmetric = _current_use_asymmetric_curve

        dialog = OptionsDialog(
            parent, sag, end_flat, profile, asymmetric, ANGLE_PROFILE_OPTIONS
        )

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
