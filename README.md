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

## KiCad Version

* 8, 9

## Acknowledgement

* [Salicylic acid](https://x.com/Salicylic_acid3)'s [Jiki Onsen-gai Annaijo (Self-made Keyboard Hot Spring Town Information Center)](https://discord.com/invite/xytwFtmvct) - Jiki Progress Wai-Wai Forum
* [Chiina](https://x.com/on_8va_bassa) for the post that inspired development and early feedback
* [marby](https://github.com/marby3) for providing hints on the asymmetric curve correction feature

## License

[MIT](./LICENSE)
