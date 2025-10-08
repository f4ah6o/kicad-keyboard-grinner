# kicad-keyboard-grinner （ぐりんぐりん）

Grinレイアウトでキーボードスイッチフットプリントを配置するためのKiCad Action Pluginです。

codexやclaudeによるvibingで作成しています。

## 機能

* キーボードスイッチフットプリント（`SW*`）を下凸のカーブに沿って配置
* 下げ量（sag）でカーブの深さを調整
* 左右端の水平キー数を調整可能（0、1、または2）
* 端キーの幅が異なる場合の非対称カーブ補正
* キーサイズ（1.25u、1.5u、1.75uなど）のサポート
* 角度プロファイルでカーブを変更可能

## インストール

1. プラグインファイルをKiCadのプラグインディレクトリにコピーします:
   * Linux: `~/.kicad/scripting/plugins/`
   * macOS: `~/Library/Application Support/kicad/scripting/plugins/`
   * Windows: `%APPDATA%\kicad\scripting\plugins\`

2. **ツール → 外部プラグイン → プラグインを更新**

## 使い方

1. キーボードスイッチフットプリントを選択します（参照名が`SW\d+`パターンに一致するもの、例: `SW1`、`SW2`など）
2. メニューからプラグインを実行します: **ツール → 外部プラグイン → Keyboard grinner**
3. ダイアログでパラメータを設定します:
   * **下端の下げ量**（mm）: カーブの最下点の垂直方向の下げ量
   * **各端の水平キー数**: 左右端の水平キーの数（0〜2）
   * **角度プロファイル**: カーブ形状のプロファイル
   * **非対称カーブ補正**: 端キーの幅が異なる場合の補正を有効化（例: 1.75u + 1.0u）
4. **適用**をクリックしてプレビュー、または**OK**をクリックして適用して閉じます

## KiCAD バージョン

* 8,9

## 謝辞

* [サリチル酸](https://x.com/Salicylic_acid3)さんの[自キ温泉街案内所](https://discord.com/invite/xytwFtmvct)　自キ進捗ワイワイフォーラム
* 開発のきっかけとなった投稿といち早く反応をくれた[ちぃな](https://x.com/on_8va_bassa)さん
* 非対称カーブ補正機能のヒントを提供してくれた[marby](https://github.com/marby3)さん

## ライセンス

[MIT](./LICENSE)
