# SPDX-License-Identifier: MIT
"""Layout calculation logic for keyboard rows."""

import math

import pcbnew

from .geometry import (
    bezier_cubic_point,
    bezier_cubic_tangent,
    board_to_math,
    calculate_asymmetric_bezier_controls,
    corner_point_math,
    get_lower_upper_labels,
    math_to_board,
    rot2d,
    square_corners_math,
)
from .unit_parsing import UNIT_MM


# Constants
ROT_OFFSET_DEG = 0.0
DRAW_EDGECUTS = False
DRAW_SQUARE_GUIDE = False
EDGE_WIDTH_MM = 0.1


def mm(value: float) -> int:
    """Convert mm to KiCad internal units."""
    return pcbnew.FromMM(value)


def angle_profile_factor(profile_key: str, norm_distance: float) -> float:
    """
    Calculate angle adjustment factor based on profile.

    Args:
        profile_key: Profile type ("cosine", "quadratic", or "bezier")
        norm_distance: Normalized distance from center (0.0 to 1.0)

    Returns:
        Adjustment factor (0.0 to 1.0)
    """
    norm = max(0.0, min(1.0, norm_distance))
    if profile_key == "cosine":
        return math.cos((math.pi / 2.0) * norm)
    if profile_key == "quadratic":
        return max(0.0, 1.0 - norm * norm)
    return 1.0


def assign_categories(count: int, end_flat: int):
    """
    Assign category labels to each key in the row.

    Args:
        count: Number of keys
        end_flat: Number of flat keys at each end

    Returns:
        List of category strings for each key
    """
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
    """
    Determine contact mode from adjacent key categories.

    Args:
        cat_prev: Previous key category
        cat_curr: Current key category

    Returns:
        Contact mode ("upper" or "lower")
    """
    special = {cat_prev, cat_curr}
    if "valley_flat" in special:
        return "upper"
    if "flat" in special:
        return "lower"
    if "upper" in special or "valley_upper" in special:
        return "upper"
    return "lower"


def place_with_corner_contact(
    prev_center, prev_angle, curr_angle, prev_width, curr_width, mode, forward
):
    """
    Calculate position for key with corner contact to previous key.

    Args:
        prev_center: Previous key center (x, y)
        prev_angle: Previous key angle (radians)
        curr_angle: Current key angle (radians)
        prev_width: Previous key width
        curr_width: Current key width
        mode: Contact mode ("upper" or "lower")
        forward: Forward direction vector (x, y)

    Returns:
        Current key center position (x, y)
    """
    # Height is always 1u (UNIT_MM)
    height = UNIT_MM
    lower_prev, upper_prev = get_lower_upper_labels(prev_angle, prev_width, height)
    lower_curr, upper_curr = get_lower_upper_labels(curr_angle, curr_width, height)
    prev_labels = lower_prev if mode == "lower" else upper_prev
    curr_labels = lower_curr if mode == "lower" else upper_curr

    # Ideal center-to-center distance = half of prev width + half of curr width
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


def add_segment_math(board, p1_math, p2_math, layer, width_mm):
    """Add a line segment to the board."""
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
    """Draw a polyline on the board."""
    count = len(pts_math)
    last = count if closed else count - 1
    for idx in range(last):
        add_segment_math(
            board, pts_math[idx], pts_math[(idx + 1) % count], layer, width_mm
        )


def calculate_bezier_controls(
    P0, P3, sag_y_mm, left_width_mm, right_width_mm, use_asymmetric
):
    """
    Calculate Bezier control points.

    Args:
        P0: Start point
        P3: End point
        sag_y_mm: Downward sag
        left_width_mm: Left end key width
        right_width_mm: Right end key width
        use_asymmetric: Whether to use asymmetric correction

    Returns:
        Tuple of (P1, P2) control points
    """
    row_length = P3[0] - P0[0]
    if use_asymmetric:
        return calculate_asymmetric_bezier_controls(
            P0, P3, sag_y_mm, left_width_mm, right_width_mm
        )
    else:
        beta = (4.0 / 3.0) * (-sag_y_mm)
        P1 = (P0[0] + row_length / 3.0, P0[1] + beta)
        P2 = (P3[0] - row_length / 3.0, P3[1] + beta)
        return P1, P2


def calculate_angles_from_tangents(
    ts, P0, P1, P2, P3, N, angle_profile_key, categories
):
    """
    Calculate key angles from Bezier tangents.

    Args:
        ts: Parameter values
        P0, P1, P2, P3: Bezier control points
        N: Number of keys
        angle_profile_key: Angle profile type
        categories: Key categories

    Returns:
        Tuple of (base_tangent, angles)
    """
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
    return base_tangent, angles


def apply_corner_contact_adjustments(
    centers, angles, widths, categories, base_tangent, N
):
    """
    Apply corner contact adjustments to key positions.

    Args:
        centers: List of center positions
        angles: List of angles
        widths: List of widths
        categories: List of categories
        base_tangent: List of base tangent angles
        N: Number of keys

    Returns:
        Updated centers list
    """
    for idx in range(1, N):
        prev_center = centers[idx - 1]
        prev_angle = angles[idx - 1]
        curr_angle = angles[idx]
        prev_width = widths[idx - 1]
        curr_width = widths[idx]
        mode = contact_mode_from_categories(categories[idx - 1], categories[idx])
        avg = math.atan2(
            math.sin(base_tangent[idx - 1]) + math.sin(base_tangent[idx]),
            math.cos(base_tangent[idx - 1]) + math.cos(base_tangent[idx]),
        )
        fwd = (math.cos(avg), math.sin(avg))
        centers[idx] = place_with_corner_contact(
            prev_center, prev_angle, curr_angle, prev_width, curr_width, mode, fwd
        )
    return centers


def apply_end_key_width_corrections(
    centers, angles, key_widths, key_heights, left_actual_width, right_actual_width
):
    """
    Apply corrections for non-standard end key widths.

    Args:
        centers: List of center positions
        angles: List of angles
        key_widths: List of key widths
        key_heights: List of key heights
        left_actual_width: Actual left end key width
        right_actual_width: Actual right end key width

    Returns:
        Updated centers list
    """
    # Left end correction
    if abs(left_actual_width - UNIT_MM) > 1e-6:
        angle_left = angles[0]
        virtual_offset = rot2d(UNIT_MM / 2.0, -key_heights[0] / 2.0, angle_left)
        actual_offset = rot2d(
            left_actual_width / 2.0, -key_heights[0] / 2.0, angle_left
        )
        delta_left = (
            virtual_offset[0] - actual_offset[0],
            virtual_offset[1] - actual_offset[1],
        )
        centers[0] = (centers[0][0] + delta_left[0], centers[0][1] + delta_left[1])

    # Right end correction
    if abs(right_actual_width - UNIT_MM) > 1e-6:
        angle_right = angles[-1]
        virtual_offset = rot2d(-UNIT_MM / 2.0, -key_heights[-1] / 2.0, angle_right)
        actual_offset = rot2d(
            -right_actual_width / 2.0, -key_heights[-1] / 2.0, angle_right
        )
        delta_right = (
            virtual_offset[0] - actual_offset[0],
            virtual_offset[1] - actual_offset[1],
        )
        centers[-1] = (
            centers[-1][0] + delta_right[0],
            centers[-1][1] + delta_right[1],
        )

    return centers


def apply_flat_key_adjustments(centers, categories, N):
    """
    Apply y-coordinate adjustments for flat keys.

    Args:
        centers: List of center positions
        categories: List of key categories
        N: Number of keys

    Returns:
        Updated centers list
    """
    if N > 0:
        base_y = centers[0][1]
        for idx in range(N):
            if categories[idx] == "flat" and idx > 0:
                centers[idx] = (centers[idx][0], base_y)
        # Align right end key to base_y
        if N > 1:
            centers[-1] = (centers[-1][0], base_y)
    return centers


def apply_position_to_origin(centers, original_centers_math):
    """
    Translate centers to keep first key at original position.

    Args:
        centers: List of center positions
        original_centers_math: Original center positions

    Returns:
        Updated centers list
    """
    if centers:
        delta_x = centers[0][0] - original_centers_math[0][0]
        delta_y = centers[0][1] - original_centers_math[0][1]
        if abs(delta_x) > 1e-9 or abs(delta_y) > 1e-9:
            centers = [(c[0] - delta_x, c[1] - delta_y) for c in centers]
    return centers


def draw_debug_geometry(board, P0, P1, P2, P3, centers, angles, key_sizes):
    """Draw debug geometry on Edge.Cuts layer."""
    if not DRAW_EDGECUTS:
        return

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


def apply_positions_to_footprints(fps, centers, angles):
    """
    Apply calculated positions and angles to footprints.

    Args:
        fps: List of footprint objects
        centers: List of center positions in math coordinates
        angles: List of angles in radians
    """
    for fp, center_math, angle in zip(fps, centers, angles):
        center_board = math_to_board(center_math)
        fp.SetPosition(pcbnew.VECTOR2I(mm(center_board[0]), mm(center_board[1])))
        fp.SetOrientationDegrees(math.degrees(angle))
        fp.SetLocked(False)


def get_original_centers_math(fps):
    """Get original center positions in math coordinates."""
    original_centers_math = []
    for fp in fps:
        pos = fp.GetPosition()
        mm_pos = (pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y))
        original_centers_math.append(board_to_math(mm_pos))
    return original_centers_math
