# kicad-keyboard-grinner

A KiCad Action Plugin for arranging keyboard switch footprints in a Grin layout.

Created with vibing using Codex and Claude.

> English version is mainly translated by Claude from [./README.ja.md](./README.ja.md).

## Features

* Arrange keyboard switch footprints (`SW*`) along a convex-down curved row
* Adjust curve depth with sag amount
* Adjustable number of flat keys at each end (0, 1, or 2)
* Asymmetric curve correction for different end key widths
* Support for key sizes (1.25u, 1.5u, 1.75u, etc.)
* Modifiable curves with angle profiles

## Installation

1. Copy the plugin file to your KiCad plugin directory:
   * Linux: `~/.kicad/scripting/plugins/`
   * macOS: `~/Library/Application Support/kicad/scripting/plugins/`
   * Windows: `%APPDATA%\kicad\scripting\plugins\`

2. **Tools → External Plugins → Refresh Plugins**

## Usage

1. Select keyboard switch footprints (with reference names matching `SW\d+` pattern, e.g., `SW1`, `SW2`, etc.)
2. Run the plugin from the menu: **Tools → External Plugins → Keyboard grinner**
3. Configure parameters in the dialog:
   * **Downward sag amount** (mm): The vertical drop at the bottom of the curve
   * **Flat keys at each end**: Number of horizontal keys at the left and right edges (0-2)
   * **Angle profile**: Curve shape profile
   * **Asymmetric curve correction**: Enable to compensate for different end key widths (e.g., 1.75u + 1.0u)
4. Click **Apply** to preview or **OK** to apply and close
5. Run the plugin with no footprints selected to re-open a saved row. The plugin stores row parameters in a hidden footprint field named `grinner_params` on the leftmost switch and presents them in a picker dialog.

> Tip: set `DEBUG_FIELD_DIALOG = True` in `src/keyboard_grinner.py` if you want pop-up confirmation while working on field storage.

## KiCad Version

* 8, 9

## Example

1. [cheena-gb](https://github.com/cheena-gb)'s [60% keyboard](./example/griiiiiiiiii.kicad_pcb)
   * View it on [kicanvas](https://kicanvas.org/?github=https%3A%2F%2Fgithub.com%2Ff4ah6o%2Fkicad-keyboard-grinner%2Fblob%2Fmain%2Fexample%2Fgriiiiiiiiii.kicad_pcb)
   * Built with an alpha plugin version not stored in this repository plus manual adjustments by the contributor using Keyboard Interference Check Footprints

### About "Keyboard Interference Check Footprints"
Files contained inside [kbd_SW_IFC](./kbd_SW_IFC/) are footprints for checking interference between keys and keycaps.  
The outer rectangle has width of 19.05mm X units; the inner one is 0.5mm offset of that.  
The square inside is the switch hole, drawn on Edge.Cuts.  
Through holes on the edges are 2.2mm diameter; M2 screw through hole.  
  
It is possible to fine-tune the placements of the footprints with these footprints.
Please use it as same as regular footprints.
* Checked on KiCAD 9

## Acknowledgement

* [Salicylic acid](https://x.com/Salicylic_acid3)'s [Jiki Onsen-gai Annaijo (Self-made Keyboard Hot Spring Town Information Center)](https://discord.com/invite/xytwFtmvct) - Jiki Progress Wai-Wai Forum
* [cheena-gb](https://github.com/cheena-gb) for the post that inspired development and early feedback
  * Additionally provided the [example board](./example/griiiiiiiiii.kicad_pcb)
  * Also viewable on [kicanvas](https://kicanvas.org/?github=https%3A%2F%2Fgithub.com%2Ff4ah6o%2Fkicad-keyboard-grinner%2Fblob%2Fmain%2Fexample%2Fgriiiiiiiiii.kicad_pcb)
* [marby](https://github.com/marby3) for providing hints on the asymmetric curve correction feature

## License

[MIT](./LICENSE)