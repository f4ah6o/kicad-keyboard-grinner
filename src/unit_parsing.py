# SPDX-License-Identifier: MIT
"""Unit parsing and conversion utilities."""

import math
import re


# Constants
UNIT_MM = 19.05  # key pitch (1u)

# Regex patterns
_unit_token_re = re.compile(r"(\d+(?:\.\d+)?)\s*(mm|MM|u|U)?")


def _convert_unit_token(num_str, unit_str, default_unit="u"):
    """
    Convert a numeric string with unit to millimeters.

    Args:
        num_str: Numeric string
        unit_str: Unit string ("mm", "u", or None)
        default_unit: Default unit if unit_str is None

    Returns:
        Value in millimeters, or None if conversion fails
    """
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
    """
    Parse a dimension pair like "1.5u x 1u" or "1.75u".

    Args:
        text: Text containing dimension(s)

    Returns:
        Tuple of (width_mm, height_mm) or None if parse fails
    """
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
    """
    Parse a single unit value like "1.5u" or "19.05mm".

    Args:
        text: Text containing a dimension
        default_unit: Default unit if not specified

    Returns:
        Value in millimeters, or None if parse fails
    """
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
    """
    Quantize a dimension to standard keyboard unit increments.

    Args:
        value_mm: Value in millimeters
        min_units: Minimum value in units
        step: Quantization step in units

    Returns:
        Quantized value in millimeters
    """
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
