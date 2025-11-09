# SPDX-License-Identifier: MIT
"""Dialog classes for the keyboard grinner plugin."""

import wx


class RowSelectionDialog(wx.Dialog):
    """Dialog for selecting saved rows."""

    def __init__(self, parent, saved_rows):
        super().__init__(parent, title="配置済みの行を選択")
        self._saved_rows = saved_rows

        # Description label
        label = wx.StaticText(self, label="編集する行を選択してください:")

        # Choice dropdown
        labels = [row["label"] for row in saved_rows]
        self._choice = wx.Choice(self, choices=labels)
        if labels:
            self._choice.SetSelection(0)

        # Buttons
        self._select_btn = wx.Button(self, wx.ID_OK, label="選択して編集")
        self._cancel_btn = wx.Button(self, wx.ID_CANCEL)
        self._select_btn.SetDefault()

        # Layout
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_sizer.Add(self._select_btn, 0, wx.RIGHT, 5)
        btn_sizer.Add(self._cancel_btn, 0)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(label, 0, wx.ALL, 10)
        sizer.Add(self._choice, 0, wx.ALL | wx.EXPAND, 10)
        sizer.Add(btn_sizer, 0, wx.ALL | wx.ALIGN_RIGHT, 10)

        self.SetSizerAndFit(sizer)

    def get_selected_row(self):
        """Return the selected row data."""
        idx = self._choice.GetSelection()
        if idx >= 0:
            return self._saved_rows[idx]
        return None


class OptionsDialog(wx.Dialog):
    """Dialog for configuring row layout options."""

    def __init__(
        self,
        parent,
        initial_sag,
        initial_end_flat,
        initial_profile_key,
        initial_asymmetric,
        angle_profile_options,
    ):
        super().__init__(parent, title="RowLayouter 設定")

        self._sag_ctrl = wx.SpinCtrlDouble(
            self, min=0.0, max=100.0, inc=0.5, initial=max(0.0, initial_sag)
        )
        self._sag_ctrl.SetDigits(2)

        self._end_ctrl = wx.SpinCtrl(self, min=0, max=2, initial=int(initial_end_flat))

        profile_labels = [label for (label, _key) in angle_profile_options]
        self._profile_choice = wx.Choice(self, choices=profile_labels)
        try:
            initial_index = next(
                idx
                for idx, (_label, key) in enumerate(angle_profile_options)
                if key == initial_profile_key
            )
        except StopIteration:
            initial_index = 0
        self._profile_choice.SetSelection(initial_index)

        # Asymmetric curve correction checkbox
        self._asymmetric_checkbox = wx.CheckBox(
            self, label="非対称カーブ補正(端キー幅の違いを補正)"
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
        self._angle_profile_options = angle_profile_options

    def get_sag(self):
        """Get sag value."""
        return float(self._sag_ctrl.GetValue())

    def get_end_flat(self):
        """Get end flat value."""
        return int(self._end_ctrl.GetValue())

    def get_profile_key(self):
        """Get selected profile key."""
        idx = self._profile_choice.GetSelection()
        if 0 <= idx < len(self._angle_profile_options):
            return self._angle_profile_options[idx][1]
        return self._angle_profile_options[0][1]

    def get_use_asymmetric_curve(self):
        """Get asymmetric curve setting."""
        return self._asymmetric_checkbox.GetValue()

    def set_apply_handler(self, handler):
        """Set the apply handler callback."""
        self._apply_handler = handler

    def _collect_parameters(self):
        """Collect all parameters from dialog."""
        return {
            "sag": self.get_sag(),
            "end_flat": self.get_end_flat(),
            "profile": self.get_profile_key(),
            "use_asymmetric_curve": self.get_use_asymmetric_curve(),
        }

    def _on_apply(self, event):
        """Handle apply button click."""
        if self._apply_handler:
            self._apply_handler(self._collect_parameters())

    def _on_ok(self, event):
        """Handle OK button click."""
        if self._apply_handler:
            if not self._apply_handler(self._collect_parameters()):
                return
        self.EndModal(wx.ID_OK)

    def _on_cancel(self, event):
        """Handle cancel button click."""
        self.EndModal(wx.ID_CANCEL)
