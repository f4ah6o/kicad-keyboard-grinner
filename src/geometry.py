# SPDX-License-Identifier: MIT
"""Geometry and mathematical functions for keyboard layout calculations."""

import math


def rot2d(x, y, angle_rad):
    """
    Rotate a 2D point around the origin.

    Args:
        x: X coordinate
        y: Y coordinate
        angle_rad: Rotation angle in radians

    Returns:
        Tuple of (x, y) after rotation
    """
    c = math.cos(angle_rad)
    s = math.sin(angle_rad)
    return (x * c - y * s, x * s + y * c)


def board_to_math(pt):
    """
    Convert from KiCad board coordinates to mathematical coordinates.

    Args:
        pt: Tuple of (x, y) in board coordinates

    Returns:
        Tuple of (x, y) in math coordinates (Y-axis flipped)
    """
    x, y = pt
    return (x, -y)


def math_to_board(pt):
    """
    Convert from mathematical coordinates to KiCad board coordinates.

    Args:
        pt: Tuple of (x, y) in math coordinates

    Returns:
        Tuple of (x, y) in board coordinates (Y-axis flipped)
    """
    x, y = pt
    return (x, -y)


def bezier_cubic_point(t, P0, P1, P2, P3):
    """
    Calculate a point on a cubic Bezier curve.

    Args:
        t: Parameter value (0.0 to 1.0)
        P0, P1, P2, P3: Control points as (x, y) tuples

    Returns:
        Point (x, y) on the curve at parameter t
    """
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
    """
    Calculate the tangent vector of a cubic Bezier curve.

    Args:
        t: Parameter value (0.0 to 1.0)
        P0, P1, P2, P3: Control points as (x, y) tuples

    Returns:
        Tangent vector (dx, dy) at parameter t
    """
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
    """
    Divide Bezier curve into N equal-length segments.

    Args:
        P0, P1, P2, P3: Control points
        count: Number of points

    Returns:
        List of parameter values t
    """
    if count <= 1:
        return [0.0]
    return bezier_divide_by_distances(P0, P1, P2, P3, count, None)


def bezier_divide_by_distances(P0, P1, P2, P3, count, cumulative_distances=None):
    """
    Divide Bezier curve based on cumulative distance array.

    Args:
        P0, P1, P2, P3: Control points
        count: Number of points
        cumulative_distances: List of cumulative distances (None for equal spacing)

    Returns:
        List of parameter values t corresponding to each point
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

    # Use equal spacing if cumulative_distances not provided
    if cumulative_distances is None:
        cumulative_distances = [total * (k / (count - 1)) for k in range(count)]
    else:
        # Normalize: scale cumulative distances to total arc length
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


def calculate_asymmetric_bezier_controls(
    P0, P3, sag_y_mm, left_width_mm, right_width_mm
):
    """
    Calculate asymmetric Bezier control points based on end key widths.

    Args:
        P0: Start point (x, y)
        P3: End point (x, y)
        sag_y_mm: Downward sag amount (mm)
        left_width_mm: Left end key width (mm)
        right_width_mm: Right end key width (mm)

    Returns:
        (P1, P2): Asymmetrically adjusted control points

    Algorithm:
        1. Asymmetry coefficient = (left_width - right_width) / (left_width + right_width)
           Range: -1.0 (biased right) ~ 0.0 (symmetric) ~ +1.0 (biased left)

        2. Control point shift = asymmetry × shift_factor (default 0.15 = max 15% shift)

        3. Control point positions:
           - Symmetric: P1 = 1/3, P2 = 2/3
           - Left wider (asymmetry > 0): Shift P1, P2 left
           - Right wider (asymmetry < 0): Shift P1, P2 right

        4. Vertical position (beta) remains: (4/3) × (-sag_y_mm)

    Examples:
        - Left 1.75u, Right 1.0u: asymmetry = 0.273 → ~4.1% left shift
        - Left 1.5u, Right 1.0u: asymmetry = 0.2 → ~3.0% left shift
        - Left 1.0u, Right 1.0u: asymmetry = 0.0 → no shift (symmetric)
    """
    row_length = P3[0] - P0[0]
    beta = (4.0 / 3.0) * (-sag_y_mm)

    # Calculate asymmetry coefficient
    total_width = left_width_mm + right_width_mm
    if total_width > 1e-6:
        asymmetry = (left_width_mm - right_width_mm) / total_width
    else:
        asymmetry = 0.0

    # Shift amount (max 15%)
    shift_factor = 0.15
    shift = asymmetry * shift_factor

    # Adjust horizontal positions of control points asymmetrically
    # P1: At 1/3 ± shift from left
    # P2: At 2/3 ∓ shift from left (wider left → both shift left)
    p1_from_left = (1.0 / 3.0) - shift
    p2_from_right = (1.0 / 3.0) + shift  # Sign flipped: wider left → P2 also left

    P1 = (P0[0] + row_length * p1_from_left, P0[1] + beta)
    P2 = (P3[0] - row_length * p2_from_right, P3[1] + beta)

    return P1, P2


def square_corners_math(center, width, height, angle_rad):
    """
    Calculate corner points of a rotated rectangle.

    Args:
        center: Center point (x, y)
        width: Rectangle width
        height: Rectangle height
        angle_rad: Rotation angle in radians

    Returns:
        List of 4 corner points [(x, y), ...]
    """
    cx, cy = center
    hw = width / 2.0
    hh = height / 2.0
    base = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]
    rotated = [rot2d(x, y, angle_rad) for (x, y) in base]
    return [(cx + px, cy + py) for (px, py) in rotated]


def corner_point_math(center, width, height, angle, label):
    """
    Get a specific corner point of a rotated rectangle.

    Args:
        center: Center point (x, y)
        width: Rectangle width
        height: Rectangle height
        angle: Rotation angle in radians
        label: Corner label ("UL", "UR", "LL", "LR")

    Returns:
        Corner point (x, y)
    """
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
    """
    Determine which corner labels are lower/upper in board coordinates.

    Args:
        angle: Rotation angle in radians
        width: Rectangle width
        height: Rectangle height

    Returns:
        Tuple of (lower_labels, upper_labels)
    """
    labels = ["UL", "UR", "LL", "LR"]
    # Convert to board orientation by inspecting math Y (lower on board => smaller math Y)
    pts = {
        lab: corner_point_math((0.0, 0.0), width, height, angle, lab) for lab in labels
    }
    sorted_labels = sorted(labels, key=lambda lab: pts[lab][1])
    lower = sorted_labels[:2]
    upper = sorted_labels[2:]
    return lower, upper
