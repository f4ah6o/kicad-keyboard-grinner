# SPDX-License-Identifier: MIT
"""Footprint field handling utilities for KiCad."""

import json
import math

import pcbnew
import wx

from .unit_parsing import UNIT_MM, _parse_unit_pair, _parse_unit_value, _quantize_dim_mm


# Debug flag
DEBUG_FIELD_DIALOG = False


def _resolve_user_field_id():
    """Resolve the USER field ID for the current KiCad version."""
    for enum_name in ("PCB_FIELD_T", "FIELD_T", "FOOTPRINT_FIELD_ID"):
        enum = getattr(pcbnew, enum_name, None)
        if enum and hasattr(enum, "USER"):
            return getattr(enum, "USER")

    for const_name in (
        "PCB_FIELD_T_USER",
        "FIELD_T_USER",
        "PCB_FIELD_ID_USER",
    ):
        if hasattr(pcbnew, const_name):
            return getattr(pcbnew, const_name)

    return None


try:
    _USER_FIELD_ID = _resolve_user_field_id()
except AttributeError:
    _USER_FIELD_ID = None


def _get_footprint_field(fp, name):
    """Get a footprint field by name."""
    try:
        return fp.GetFieldByName(name)
    except AttributeError:
        return None


def _add_footprint_field(fp, name, *, visible=True):
    """
    Add a new field to a footprint.

    Args:
        fp: Footprint object
        name: Field name
        visible: Whether field should be visible

    Returns:
        The created field object

    Raises:
        RuntimeError: If field creation fails
    """
    errors = []
    field = None

    if _USER_FIELD_ID is not None:
        try:
            field = pcbnew.PCB_FIELD(fp, _USER_FIELD_ID, name)
        except Exception as exc:  # pragma: no cover - environment dependent
            errors.append(f"with USER id: {exc}")
            field = None

    if field is None:
        get_count = getattr(fp, "GetFieldCount", None)
        if callable(get_count):
            try:
                field = pcbnew.PCB_FIELD(fp, get_count(), name)
            except Exception as exc:  # pragma: no cover - environment dependent
                errors.append(f"with GetFieldCount(): {exc}")
                field = None

    for attr in ("PCB_FIELD_ID_USER", "PCB_FIELD_T", "FIELD_T"):
        if field is not None:
            break
        obj = getattr(pcbnew, attr, None)
        if obj is None:
            continue
        try:
            candidate = obj.USER if hasattr(obj, "USER") else obj
        except AttributeError:
            candidate = obj
        if hasattr(candidate, "USER"):
            candidate = getattr(candidate, "USER")
        try:
            field = pcbnew.PCB_FIELD(fp, candidate, name)
        except Exception as exc:  # pragma: no cover - environment dependent
            errors.append(f"with {attr}: {exc}")
            field = None

    if field is None:
        detail = ", ".join(errors) if errors else "no constructors succeeded"
        raise RuntimeError(f"Failed to create field '{name}': {detail}")

    name_setter = getattr(field, "SetName", None)
    if callable(name_setter):
        name_setter(name)
    setter = getattr(field, "SetVisible", None)
    if callable(setter):
        setter(visible)
    fp.AddField(field)
    return field


def _field_text(field):
    """Get text from a field object."""
    getter = getattr(field, "GetText", None)
    if callable(getter):
        return getter()
    getter = getattr(field, "GetShownText", None)
    if callable(getter):
        return getter()
    return getattr(field, "m_Text", None)


def _footprint_field_text(fp, name):
    """Get the text stored in a footprint field if available."""
    field = _get_footprint_field(fp, name)
    if field:
        text = _field_text(field)
        if text is not None:
            return str(text)

    return None


def _debug_saved_field_snapshot(fp, field, existed_before, text):
    """Show debug dialog for saved field (if DEBUG_FIELD_DIALOG is True)."""
    if not DEBUG_FIELD_DIALOG:
        return
    try:
        ref = fp.GetReference()
    except AttributeError:
        ref = "(unknown)"
    try:
        name = field.GetName()
    except AttributeError:
        name = "(no name)"
    try:
        visible = field.IsVisible()
    except AttributeError:
        visible = "?"
    title = "Keyboard grinner debug"
    status = "updated" if existed_before else "created"
    message = (
        f"Field '{name}' {status} on {ref}\n" f"Visible: {visible}\n" f"Text: {text}"
    )
    try:
        wx.MessageBox(message, title, wx.OK | wx.ICON_INFORMATION)
    except Exception:
        print(f"[grinner] {title}: {message}")


def infer_key_dimensions(fp):
    """
    Infer key dimensions from footprint metadata.

    Args:
        fp: Footprint object

    Returns:
        Tuple of (width_mm, height_mm)
    """
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

    for field_name in ("KEY_WIDTH", "KeyWidth"):
        width_mm = _parse_unit_value(_footprint_field_text(fp, field_name))
        if width_mm is not None:
            break

    for field_name in ("KEY_HEIGHT", "KeyHeight"):
        height_mm = _parse_unit_value(_footprint_field_text(fp, field_name))
        if height_mm is not None:
            break

    if width_mm is None or height_mm is None:
        for field_name in ("KEY_SIZE", "KeySize", "KEY_DIM", "KeyDim", "SW_SIZE"):
            pair = _parse_unit_pair(_footprint_field_text(fp, field_name))
            if pair:
                if width_mm is None:
                    width_mm = pair[0]
                if height_mm is None:
                    height_mm = pair[1]
                if width_mm is not None and height_mm is not None:
                    break

    if width_mm is None:
        extra = _footprint_field_text(fp, "SW_WIDTH")
        if extra:
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


def save_parameters_to_footprint(first_fp, params, target_fps):
    """
    Save layout parameters to the leftmost footprint.

    Args:
        first_fp: Leftmost footprint
        params: Parameters dict to save
        target_fps: List of target footprints
    """
    try:
        data = params.copy()
        refs = [fp.GetReference() for fp in target_fps]
        data["footprints"] = refs
        data["row_name"] = f"{refs[0]}〜{refs[-1]}"
        data["version"] = "2025.10.2"

        json_str = json.dumps(data, ensure_ascii=False)

        if DEBUG_FIELD_DIALOG:
            wx.MessageBox(
                f"Saving parameters to {refs[0]} (count {len(refs)})\nJSON length: {len(json_str)}",
                "Keyboard grinner debug",
                wx.OK | wx.ICON_INFORMATION,
            )

        field = _get_footprint_field(first_fp, "grinner_params")
        existed_before = field is not None
        if not field:
            field = _add_footprint_field(
                first_fp, "grinner_params", visible=DEBUG_FIELD_DIALOG
            )

        visible_setter = getattr(field, "SetVisible", None)
        if callable(visible_setter):
            visible_setter(DEBUG_FIELD_DIALOG)

        field.SetText(json_str)
        _debug_saved_field_snapshot(first_fp, field, existed_before, json_str)
    except Exception as e:
        message = f"Failed to save parameters: {e}"
        if DEBUG_FIELD_DIALOG:
            wx.MessageBox(
                message,
                "Keyboard grinner debug",
                wx.OK | wx.ICON_ERROR,
            )
        else:
            print(message)


def find_saved_rows(board):
    """
    Find saved rows from the board.

    Args:
        board: pcbnew.BOARD object

    Returns:
        List of saved row dictionaries
    """
    saved_rows = []
    for fp in board.GetFootprints():
        field_text = _footprint_field_text(fp, "grinner_params")
        if not field_text:
            continue
        try:
            data = json.loads(field_text)
        except json.JSONDecodeError:
            continue
        saved_rows.append(
            {
                "first_fp": fp,
                "data": data,
                "label": f"{data.get('row_name', 'Unknown')} ({len(data.get('footprints', []))}個)",
            }
        )
    return saved_rows


def reselect_footprints_from_data(board, data):
    """
    Reselect footprints from saved data.

    Args:
        board: pcbnew.BOARD object
        data: Saved parameters dict

    Returns:
        Number of footprints selected
    """
    if "footprints" not in data:
        return 0

    target_refs = set(data["footprints"])
    count = 0

    # Clear existing selection
    for fp in board.GetFootprints():
        clear_sel = getattr(fp, "ClearSelected", None)
        if callable(clear_sel):
            clear_sel()
            continue

        setter = getattr(fp, "SetSelected", None)
        if callable(setter):
            try:
                setter(False)
            except TypeError:
                setter()

    # Select target footprints
    for fp in board.GetFootprints():
        if fp.GetReference() in target_refs:
            setter = getattr(fp, "SetSelected", None)
            if callable(setter):
                try:
                    setter(True)
                except TypeError:
                    setter()
            count += 1

    return count
