#!/usr/bin/env python3
"""
archive.json.gz を埋め込んだ単一HTMLを書き出す。

使い方:
    python build_archive_html.py out2/archive.json.gz out2/pad_skill_archive.html
"""

import base64
import io
import json
import re
import sys
import urllib.request
from pathlib import Path

AWOKEN_URL = ("https://raw.githubusercontent.com/Mapaler/PADDashFormation"
              "/master/images/awoken.png")

TEMPLATE = r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>パズドラ スキルアーカイブ</title>
<style>
  :root {
    --ground: #0E1120;
    --panel:  #171C2E;
    --raised: #1F2540;
    --line:   #2C3355;
    --ink:    #E6E9F5;
    --muted:  #8790B2;
    --focus:  #6FA8FF;

    --fire:  #E2503F;
    --water: #2E86D8;
    --wood:  #3FA35C;
    --light: #E0B32B;
    --dark:  #9A62D0;
    --heal:  #E2699C;

    --awoken-sheet: url("__AWOKEN__");
    --jp: "Hiragino Kaku Gothic ProN", "Hiragino Sans", "Yu Gothic",
          "Noto Sans JP", "Meiryo", system-ui, sans-serif;
    --mono: ui-monospace, "SF Mono", "Cascadia Mono", "Roboto Mono",
            Consolas, monospace;
  }

  * { box-sizing: border-box; }

  html, body {
    margin: 0;
    background: var(--ground); color: var(--ink);
    font-family: var(--jp); -webkit-font-smoothing: antialiased;
  }
  /* 結果を縦いっぱい使いたいので、内側スクロールをやめてページごと流す。
     常に要るタブと検索欄だけを上に貼り付け、絞り込みは一緒に流す。 */
  body { display: block; }
  :focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }

  /* ---------- ヘッダー ---------- */
  .masthead {
    position: sticky; top: 0; z-index: 30;
    padding: 10px 20px 0;
    border-bottom: 1px solid var(--line);
    background: var(--ground);
    box-shadow: 0 6px 18px -12px #000;
  }
  .filters { padding: 0 20px; }

  /* 固定するのはタブと検索欄だけ。ここの高さが変わるとスクロール位置が
     ずれて畳み判定と噛み合わなくなるので、高さは常に一定に保つ。 */
  .pagehead {
    display: flex; align-items: baseline; gap: 12px;
    flex-wrap: wrap; padding: 14px 20px 10px;
  }
  .wordmark {
    font-size: 14px; font-weight: 800;
    letter-spacing: .22em; margin: 0;
  }
  .vintage { font-family: var(--mono); font-size: 11px; color: var(--muted); margin-left: auto; }

  /* タブ: アクティブとリーダーは別物として扱う */
  .tabs { display: flex; gap: 2px; margin-bottom: 12px; }
  .tabs button {
    flex: 0 1 auto; padding: 10px 22px;
    font-family: var(--jp); font-size: 14px; font-weight: 600;
    color: var(--muted); background: transparent;
    border: 0; border-bottom: 2px solid transparent;
    cursor: pointer;
  }
  .tabs button .n { font-family: var(--mono); font-size: 11px; margin-left: 8px; opacity: .75; }
  .tabs button:hover { color: var(--ink); }
  .tabs button[aria-selected="true"] {
    color: var(--ink); border-bottom-color: var(--focus);
  }

  .search-wrap { position: relative; margin-bottom: 12px; }
  .search {
    width: 100%; padding: 13px 16px 13px 42px;
    font-family: var(--jp); font-size: 17px; font-weight: 500;
    color: var(--ink); background: var(--panel);
    border: 1px solid var(--line); border-radius: 10px;
  }
  .search::placeholder { color: var(--muted); font-weight: 400; }
  .search:focus { border-color: var(--focus); outline: none; }
  .search-icon {
    position: absolute; left: 15px; top: 50%; transform: translateY(-50%);
    color: var(--muted); pointer-events: none; font-size: 15px;
  }

  .controls {
    display: flex; flex-wrap: wrap; gap: 16px;
    align-items: center; padding-bottom: 12px;
  }
  .group { display: flex; align-items: center; gap: 8px; }
  /* .group の display が [hidden] より強いので明示的に打ち消す */
  .group[hidden] { display: none; }
  .group-label {
    font-family: var(--mono); font-size: 10px;
    letter-spacing: .16em; color: var(--muted);
  }

  .orbs { display: flex; gap: 7px; }
  .orb {
    width: 26px; height: 26px; border-radius: 50%;
    border: 2px solid transparent; cursor: pointer; padding: 0;
    opacity: .5; position: relative;
    box-shadow: inset 0 0 0 1px rgba(255,255,255,.18);
    transition: opacity .15s, transform .15s, border-color .15s;
  }
  .orb::after {
    content: ""; position: absolute; inset: 3px 3px 55% 3px;
    border-radius: 50% 50% 40% 40%;
    background: linear-gradient(180deg, rgba(255,255,255,.5), transparent);
  }
  .orb:hover { opacity: .82; transform: translateY(-1px); }
  .orb[aria-pressed="true"] { opacity: 1; border-color: #fff; }
  .orb-fire { background: var(--fire); }  .orb-water { background: var(--water); }
  .orb-wood { background: var(--wood); }  .orb-light { background: var(--light); }
  .orb-dark { background: var(--dark); }  .orb-heal { background: var(--heal); }
  /* 回復はドロップの種類であってモンスターの属性ではない。
     キャラタブは図鑑の属性で絞るので、押しても必ず0件になるため隠す。 */
  .orb[hidden] { display: none; }

  .sel {
    font-family: var(--jp); font-size: 12.5px; color: var(--ink);
    background: var(--panel); border: 1px solid var(--line);
    border-radius: 7px; padding: 6px 10px; cursor: pointer;
  }
  .sel:focus { border-color: var(--focus); outline: none; }

  .seg { display: flex; border: 1px solid var(--line); border-radius: 7px; overflow: hidden; }
  .seg[hidden] { display: none; }
  .seg button {
    font-family: var(--jp); font-size: 11.5px; color: var(--muted);
    background: transparent; border: 0; padding: 6px 11px; cursor: pointer;
  }
  .seg button:hover { color: var(--ink); }
  .seg button[aria-pressed="true"] {
    background: var(--raised); color: var(--ink); font-weight: 700;
  }

  /* 所持キャラがアシスト運用されるキャラかどうかの印 */
  .mon.is-assist { border-color: rgba(111,168,255,.5); }
  .mon .assist-mark {
    font-size: 9px; font-family: var(--mono); color: var(--focus);
    border: 1px solid rgba(111,168,255,.45); border-radius: 3px;
    padding: 0 3px; margin-left: 4px;
    /* 名前が折り返す幅でも印だけは潰れないようにする */
    white-space: nowrap; flex: 0 0 auto; align-self: center;
  }
  .mon { max-width: 100%; }

  .slider { display: flex; align-items: center; gap: 8px; }
  .slider input { width: 118px; accent-color: var(--focus); }
  .slider output { font-family: var(--mono); font-size: 12px; min-width: 62px; }

  .btn {
    font-family: var(--jp); font-size: 12px; color: var(--muted);
    background: transparent; border: 1px solid var(--line);
    border-radius: 7px; padding: 6px 12px; cursor: pointer;
  }
  .btn:hover { color: var(--ink); border-color: var(--muted); }

  .sortsel {
    font-family: var(--jp); font-size: 12px; color: var(--ink);
    background: var(--panel); border: 1px solid var(--line);
    border-radius: 7px; padding: 6px 9px; cursor: pointer;
  }
  .sortsel:hover { border-color: var(--muted); }

  .cats {
    display: flex; flex-wrap: wrap; gap: 5px;
    max-height: 30px; overflow: hidden;
    padding: 0 20px 12px; border-bottom: 1px solid var(--line);
  }
  .cats.is-open { max-height: 220px; overflow-y: auto; }
  .cats[hidden] { display: none; }
  .cat {
    font-size: 11.5px; color: var(--muted); background: var(--panel);
    border: 1px solid var(--line); border-radius: 999px;
    padding: 4px 11px; cursor: pointer; white-space: nowrap;
  }
  .cat:hover { color: var(--ink); }
  .cat[aria-pressed="true"] {
    background: var(--focus); border-color: var(--focus);
    color: #08122A; font-weight: 700;
  }
  .cat em { font-style: normal; opacity: .6; margin-left: 6px; font-family: var(--mono); font-size: 10px; }

  /* マイカテゴリ: 自動分類とは別枠。色も分けて出所が一目で分かるようにする */
  .mycats {
    display: flex; flex-wrap: wrap; gap: 6px; align-items: center;
    padding: 9px 20px; border-bottom: 1px solid var(--line);
    background: rgba(224,179,43,.045);
  }
  .mycats[hidden] { display: none; }
  .mycats-label {
    font-family: var(--mono); font-size: 10px;
    letter-spacing: .16em; color: var(--light); margin-right: 2px;
  }
  .mycat {
    display: inline-flex; align-items: stretch;
    border: 1px solid rgba(224,179,43,.42); border-radius: 999px;
    overflow: hidden; background: rgba(224,179,43,.1);
  }
  .mycat button {
    font-family: var(--jp); font-size: 11.5px; color: var(--ink);
    background: none; border: 0; cursor: pointer; padding: 4px 11px;
  }
  .mycat .mc-del {
    padding: 4px 9px; color: var(--muted);
    border-left: 1px solid rgba(224,179,43,.3); font-family: var(--mono);
  }
  .mycat .mc-del:hover { color: var(--fire); background: rgba(226,80,63,.14); }
  .mycat em { font-style: normal; opacity: .6; margin-left: 6px; font-family: var(--mono); font-size: 10px; }
  .mycat[aria-pressed="true"] { background: var(--light); border-color: var(--light); }
  .mycat[aria-pressed="true"] button { color: #1A1405; font-weight: 700; }
  .mycat[aria-pressed="true"] .mc-del { color: #1A1405; border-left-color: rgba(0,0,0,.25); }

  .mc-add {
    font-family: var(--jp); font-size: 11.5px; color: var(--light);
    background: none; border: 1px dashed rgba(224,179,43,.5);
    border-radius: 999px; padding: 4px 12px; cursor: pointer;
  }
  .mc-add:hover { background: rgba(224,179,43,.12); }
  .mc-hint { font-size: 11px; color: var(--muted); }

  .mc-form {
    display: flex; flex-wrap: wrap; gap: 7px; align-items: center;
    width: 100%; padding-top: 8px;
  }
  .mc-form[hidden] { display: none; }
  .mc-form input, .mc-form select {
    font-family: var(--jp); font-size: 12.5px; color: var(--ink);
    background: var(--panel); border: 1px solid var(--line);
    border-radius: 7px; padding: 7px 10px;
  }
  .mc-form input:focus, .mc-form select:focus { border-color: var(--light); outline: none; }
  #mcName { width: 150px; }
  #mcPattern { flex: 1 1 240px; font-family: var(--mono); font-size: 12px; }
  .mc-preview { font-family: var(--mono); font-size: 11.5px; color: var(--muted); min-width: 90px; }
  .mc-preview.bad { color: var(--fire); }
  .mc-io { width: 100%; }
  .mc-io textarea {
    width: 100%; height: 96px; margin-top: 8px;
    font-family: var(--mono); font-size: 11px; color: var(--ink);
    background: var(--panel); border: 1px solid var(--line);
    border-radius: 8px; padding: 9px;
  }
  .mc-io[hidden] { display: none; }

  /* 行からマイカテゴリへ入れる */
  .pin {
    font-family: var(--jp); font-size: 10.5px; color: var(--muted);
    background: none; border: 1px solid var(--line);
    border-radius: 4px; padding: 2px 8px; cursor: pointer; margin-left: 4px;
  }
  .pin:hover { color: var(--light); border-color: rgba(224,179,43,.5); }
  .pin.on { color: var(--light); border-color: rgba(224,179,43,.5); }
  .pin-panel {
    display: flex; flex-wrap: wrap; gap: 5px; margin-top: 7px;
    padding: 8px; border: 1px solid rgba(224,179,43,.28);
    border-radius: 8px; background: rgba(224,179,43,.05);
  }
  .pin-panel button {
    font-family: var(--jp); font-size: 11px; color: var(--muted);
    background: var(--panel); border: 1px solid var(--line);
    border-radius: 999px; padding: 3px 10px; cursor: pointer;
  }
  .pin-panel button[aria-pressed="true"] {
    background: var(--light); border-color: var(--light); color: #1A1405; font-weight: 700;
  }
  .pin-panel .empty { font-size: 11px; color: var(--muted); padding: 2px; }

  /* ---------- 結果 ---------- */
  .scroller { min-height: 60vh; }
  .row {
    display: grid; grid-template-columns: 14px 1fr; gap: 14px;
    padding: 14px 20px; border-bottom: 1px solid rgba(44,51,85,.55);
  }
  .row:hover { background: rgba(31,37,64,.42); }
  .row-body { max-width: 82ch; }

  .rail { display: flex; flex-direction: column; gap: 3px; padding-top: 5px; }
  .rail span { width: 9px; height: 9px; border-radius: 50%; display: block; }

  .row-head { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; margin-bottom: 6px; }
  .row-id { font-family: var(--mono); font-size: 11px; color: var(--muted); }
  .row-name { font-size: 15px; font-weight: 700; }
  .row-cd {
    font-family: var(--mono); font-size: 10.5px; color: var(--muted);
    border: 1px solid var(--line); border-radius: 4px; padding: 2px 7px;
  }
  .row-desc { font-size: 14.5px; line-height: 1.68; color: #D2D7EA; }
  .row-desc mark { background: rgba(111,168,255,.26); color: var(--ink); border-radius: 3px; padding: 0 2px; }

  /* 所持キャラ: 図鑑番号つき */
  .holders { margin-top: 9px; display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
  .holders-label { font-family: var(--mono); font-size: 10px; color: var(--muted); letter-spacing: .1em; }
  .mon {
    display: inline-flex; align-items: center; gap: 6px;
    font-size: 12px; color: var(--ink);
    background: var(--panel); border: 1px solid var(--line);
    border-radius: 6px; padding: 3px 9px 3px 6px;
  }
  .mon i { display: flex; gap: 2px; font-style: normal; }
  .mon i b { width: 7px; height: 7px; border-radius: 50%; display: block; }
  .mon u { text-decoration: none; font-family: var(--mono); font-size: 10.5px; color: var(--muted); }
  .mon-more {
    font-size: 11.5px; color: var(--focus); background: none;
    border: 0; cursor: pointer; padding: 3px 4px; font-family: var(--jp);
  }

  /* 覚醒アイコン。ID N は縦1列スプライトの N 行目にある */
  .aw {
    display: inline-block; width: 30px; height: 30px;
    background-image: var(--awoken-sheet);
    background-size: 30px auto;
    background-repeat: no-repeat;
    vertical-align: middle;
  }
  .aw-sm { width: 22px; height: 22px; background-size: 22px auto; }

  .awbar {
    display: flex; flex-wrap: wrap; gap: 4px; align-items: center;
    padding: 9px 20px; border-bottom: 1px solid var(--line);
    max-height: 46px; overflow: hidden;
    align-content: flex-start;
  }
  .awbar.is-open { max-height: 300px; overflow-y: auto; }
  .awbar[hidden] { display: none; }
  .awchip {
    display: inline-flex; align-items: center; gap: 5px;
    background: var(--panel); border: 1px solid var(--line);
    border-radius: 7px; padding: 2px 8px 2px 3px; cursor: pointer;
    font-size: 11.5px; color: var(--muted);
  }
  .awchip:hover { color: var(--ink); }
  .awchip[aria-pressed="true"] {
    background: var(--focus); border-color: var(--focus); color: #08122A; font-weight: 700;
  }
  .awchip em { font-style: normal; opacity: .65; font-family: var(--mono); font-size: 10px; }

  /* スキルタブから覚醒で絞るための引き出し */
  .awpick {
    padding: 10px 20px 12px; border-bottom: 1px solid var(--line);
    background: rgba(111,168,255,.05);
  }
  .awpick[hidden] { display: none; }
  .awpick-head {
    display: flex; flex-wrap: wrap; gap: 9px; align-items: center; margin-bottom: 9px;
  }
  .awpick-head input {
    font-family: var(--jp); font-size: 12.5px; color: var(--ink);
    background: var(--panel); border: 1px solid var(--line);
    border-radius: 7px; padding: 6px 10px; width: 190px;
  }
  .awpick-head input:focus { border-color: var(--focus); outline: none; }
  .awpick-note { font-size: 11px; color: var(--muted); }
  .awpick-list {
    display: flex; flex-wrap: wrap; gap: 4px;
    max-height: 46vh; overflow-y: auto;
    flex-direction: column; align-items: flex-start;
  }
  .awpick-list .none { font-size: 11.5px; color: var(--muted); padding: 4px; }
  .awgrp { display: flex; align-items: flex-start; gap: 10px; width: 100%; padding: 3px 0; }
  .awgrp-label {
    flex: 0 0 90px; text-align: right;
    font-size: 10.5px; color: var(--muted); line-height: 26px;
  }
  .awgrp-items { display: flex; flex-wrap: wrap; gap: 3px; }
  .awchip.is-icon { padding: 2px; gap: 0; border-radius: 6px; }
  .awchip.is-icon[aria-pressed="true"] { box-shadow: 0 0 0 2px var(--focus); }

  /* 統合タブの行: 1行 = キャラ */
  .crow { padding: 15px 20px; border-bottom: 1px solid rgba(44,51,85,.55); }
  .crow:hover { background: rgba(31,37,64,.32); }
  .crow-head { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
  .crow-aw { margin: 9px 0 10px; }
  .uni { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .uni-block {
    background: var(--panel); border: 1px solid var(--line);
    border-radius: 9px; padding: 10px 12px;
  }
  .uni-block.is-empty { opacity: .5; }
  .uni-top { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
  .uni-label {
    font-family: var(--mono); font-size: 9.5px; letter-spacing: .1em;
    color: var(--muted); border: 1px solid var(--line);
    border-radius: 4px; padding: 1px 5px;
  }
  .uni-label.is-leader { color: var(--light); border-color: rgba(224,179,43,.4); }
  .uni-id { font-family: var(--mono); font-size: 10.5px; color: var(--muted); }
  .uni-name { font-size: 13.5px; font-weight: 700; margin-bottom: 5px; }
  .uni-desc { font-size: 13px; line-height: 1.62; color: #D2D7EA; }
  .uni-desc mark, .uni-name mark, .mrow-name mark {
    background: rgba(111,168,255,.26); color: var(--ink); border-radius: 3px; padding: 0 2px;
  }
  .uni-empty { font-size: 12px; color: var(--muted); }

  /* 覚醒タブの行 */
  .mrow {
    padding: 13px 20px; border-bottom: 1px solid rgba(44,51,85,.55);
  }
  .mrow:hover { background: rgba(31,37,64,.42); }
  .mrow-head { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; margin-bottom: 7px; }
  .mrow-id { font-family: var(--mono); font-size: 11px; color: var(--muted); }
  .mrow-name { font-size: 15px; font-weight: 700; }
  .mrow-attrs { display: inline-flex; gap: 3px; }
  .mrow-attrs b { width: 9px; height: 9px; border-radius: 50%; display: block; }
  .aw-row { display: flex; flex-wrap: wrap; gap: 2px; align-items: center; }
  .aw-super {
    margin-left: 10px; padding-left: 10px;
    border-left: 1px solid var(--line);
    display: flex; gap: 2px; align-items: center;
  }
  .aw-super::before {
    content: "超"; font-size: 10px; color: var(--light); margin-right: 3px;
  }

  .cat-marks { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 8px; }
  .cat-mark {
    font-size: 10px; color: var(--muted);
    border: 1px solid var(--line); border-radius: 4px; padding: 2px 6px;
  }

  .state { padding: 56px 20px; text-align: center; color: var(--muted); font-size: 14px; line-height: 1.8; }
  .state strong { color: var(--ink); display: block; margin-bottom: 6px; font-size: 16px; }

  .notepanel {
    padding: 14px 20px; border-bottom: 1px solid var(--line);
    background: var(--panel);
    font-size: 12px; color: var(--muted); line-height: 1.85;
  }
  .notepanel[hidden] { display: none; }
  .notepanel dt { color: var(--ink); font-weight: 700; font-size: 12px; margin-top: 10px; }
  .notepanel dt:first-child { margin-top: 0; }
  .notepanel dd { margin: 2px 0 0; }
  .notepanel code {
    font-family: var(--mono); font-size: 11px;
    background: var(--raised); border-radius: 4px; padding: 1px 5px;
  }
  .note-toggle {
    font-family: var(--jp); font-size: 11px; color: var(--muted);
    background: none; border: 1px solid var(--line);
    border-radius: 999px; padding: 3px 11px; cursor: pointer;
  }
  .note-toggle:hover { color: var(--ink); border-color: var(--muted); }

  @media (max-width: 640px) {
    .masthead { padding: 8px 14px 0; }
    .pagehead { padding: 12px 14px 8px; }
    .filters { padding: 0 14px; }
    .notepanel { padding: 12px 14px; }
    .cats { padding: 0 14px 12px; }
    .row { padding: 12px 14px; grid-template-columns: 12px 1fr; gap: 11px; }
    .crow { padding: 13px 14px; }
    .vintage { width: 100%; margin-left: 0; }
    .search { font-size: 16px; }
    .tabs button { flex: 1; padding: 10px 6px; font-size: 13px; }
    .mycats { padding: 9px 14px; }
    .awgrp { flex-direction: column; gap: 2px; }
    .awgrp-label { flex: none; text-align: left; line-height: 1.4; }
    #mcName, #mcPattern { flex: 1 1 100%; width: auto; }
    .mc-form { gap: 6px; }
  }
  @media (max-width: 880px) {
    .uni { grid-template-columns: 1fr; }
  }
  @media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
</style>
</head>
<body>

<div class="pagehead">
  <h1 class="wordmark">パズドラ スキルアーカイブ</h1>
  <span class="vintage" id="stamp">読み込み中…</span>
  <button class="note-toggle" id="noteToggle" type="button">この表の見かた</button>
</div>

<header class="masthead">
  <div class="tabs" role="tablist" id="tabs">
    <button role="tab" data-tab="chars" aria-selected="true">キャラ<span class="n" id="nChars">–</span></button>
    <button role="tab" data-tab="active" aria-selected="false">アクティブスキル<span class="n" id="nActive">–</span></button>
    <button role="tab" data-tab="leader" aria-selected="false">リーダースキル<span class="n" id="nLeader">–</span></button>
  </div>

  <div class="search-wrap">
    <span class="search-icon">◍</span>
    <input id="q" class="search" type="search" autocomplete="off" spellcheck="false"
           placeholder="スキル文・スキル名・キャラ名で検索（数字だけなら図鑑番号／スキルID）">
  </div>

</header>

<div class="filters">
  <div class="controls">
    <div class="group">
      <span class="group-label">属性</span>
      <div class="orbs" id="orbs">
        <button class="orb orb-fire"  data-attr="fire"  aria-pressed="false" aria-label="火"></button>
        <button class="orb orb-water" data-attr="water" aria-pressed="false" aria-label="水"></button>
        <button class="orb orb-wood"  data-attr="wood"  aria-pressed="false" aria-label="木"></button>
        <button class="orb orb-light" data-attr="light" aria-pressed="false" aria-label="光"></button>
        <button class="orb orb-dark"  data-attr="dark"  aria-pressed="false" aria-label="闇"></button>
        <button class="orb orb-heal"  data-attr="heal"  aria-pressed="false" aria-label="回復"></button>
      </div>
    </div>

    <div class="group" id="awPickGroup">
      <button class="btn" id="awPickToggle" type="button">覚醒で絞る</button>
    </div>

    <div class="group" id="assistGroup">
      <span class="group-label">アシスト</span>
      <div class="seg" id="assistSeg">
        <button data-assist="any" aria-pressed="true">指定なし</button>
        <button data-assist="only" aria-pressed="false">アシストのみ</button>
        <button data-assist="not" aria-pressed="false">アシスト以外</button>
      </div>
    </div>

    <div class="group slider" id="cdGroup">
      <span class="group-label">初期CD</span>
      <input id="cdMax" type="range" min="0" max="30" value="30" step="1" aria-label="初期溜まりターンの上限">
      <output id="cdOut">指定なし</output>
    </div>

    <div class="group slider" id="multGroup" hidden>
      <span class="group-label">攻撃倍率</span>
      <input id="multMin" type="range" min="0" max="100" value="0" step="1" aria-label="最低攻撃倍率">
      <output id="multOut">指定なし</output>
    </div>

    <div class="group">
      <span class="group-label">並び順</span>
      <select class="sortsel" id="sort" aria-label="並び順">
        <option value="newest">新しいキャラ順</option>
        <option value="oldest">古いキャラ順</option>
        <option value="holders">所持キャラ数</option>
        <option value="skill">スキルID順</option>
      </select>
    </div>

    <span class="group-label" id="hits">–</span>
    <button class="btn" id="reset">条件をクリア</button>
    <button class="btn" id="toggleCats">カテゴリを広げる</button>
  </div>
</div>

<div class="notepanel" id="notePanel" hidden>
  <dl>
    <dt>データの出どころ</dt>
    <dd>Mapaler/PADDashFormation の <code>monsters-info</code>（日次更新）。</dd>

    <dt>そのまま信じてよいもの</dt>
    <dd>所持キャラと図鑑番号、スキル名、説明文、初期CD。図鑑データそのものです。</dd>

    <dt>目安として使うもの</dt>
    <dd>属性の色分けはスキル文中の属性語からの推定。カテゴリも説明文からの自動分類です。
        リーダーの「最大 ×N」は説明文から拾った倍率なので、実際に出せる値とは一致しません。</dd>

    <dt>マイカテゴリ</dt>
    <dd>このブラウザに保存されます。別の端末でも使うときは「JSON」から控えて、
        <code>mycategories.json</code> に貼ってください。</dd>

    <dt>検索のこつ</dt>
    <dd>角括弧は無視されるので <code>ロックを解除</code> でも当たります。
        数字だけ入れると図鑑番号かスキルIDの完全一致。<code>/</code> キーで検索欄へ移動します。</dd>
  </dl>
</div>

<div class="awpick" id="awpick" hidden>
  <div class="awpick-head">
    <input id="awFilter" type="search" autocomplete="off" placeholder="覚醒名で絞り込む">
    <span class="awpick-note">選んだ覚醒を<b>すべて持つキャラ</b>が所持しているスキルに絞ります</span>
    <button class="btn" id="awPickClear" type="button">覚醒の選択を解除</button>
  </div>
  <div class="awpick-list" id="awpickList"></div>
</div>

<div class="cats" id="cats"></div>

<div class="mycats" id="mycats">
  <span class="mycats-label">マイカテゴリ</span>
  <span id="mycatChips"></span>
  <button class="mc-add" id="mcAdd" type="button">＋ 追加</button>
  <button class="mc-add" id="mcIoToggle" type="button">JSON</button>
  <span class="mc-hint" id="mcHint"></span>

  <div class="mc-form" id="mcForm" hidden>
    <input id="mcName" type="text" placeholder="カテゴリ名" maxlength="24">
    <input id="mcPattern" type="text" placeholder="キーワード（正規表現可）例: 変身|転生">
    <select id="mcScope" aria-label="対象">
      <option value="both">両方のタブ</option>
      <option value="active">アクティブのみ</option>
      <option value="leader">リーダーのみ</option>
    </select>
    <span class="mc-preview" id="mcPreview">–</span>
    <button class="btn" id="mcSave" type="button">保存</button>
    <button class="btn" id="mcCancel" type="button">やめる</button>
  </div>

  <div class="mc-io" id="mcIo" hidden>
    <textarea id="mcJson" spellcheck="false" aria-label="マイカテゴリのJSON"></textarea>
    <div style="display:flex;gap:7px;margin-top:7px;align-items:center">
      <button class="btn" id="mcLoad" type="button">このJSONを読み込む</button>
      <span class="mc-hint">リポジトリの <span style="font-family:var(--mono)">mycategories.json</span> に貼れば、次のビルドから既定で入る</span>
    </div>
  </div>
</div>

<div class="scroller" id="scroller">
  <div id="viewport"></div>
  <div class="state" id="state" hidden></div>
</div>



<script>window.DEFAULT_MYCATS = __MYCATS__;</script>
<script id="payload" type="application/octet-stream">__DATA__</script>
<script>
(function () {
  "use strict";

  var ATTR_ORDER = ["fire","water","wood","light","dark","heal"];
  var ATTR_COLOR = { fire:"var(--fire)", water:"var(--water)", wood:"var(--wood)",
                     light:"var(--light)", dark:"var(--dark)", heal:"var(--heal)" };
  var CHUNK = 60, MON_LIMIT = 8;

  var DATA = null, MONS = null;
  var tab = "chars";
  var view = [], shown = 0;
  var expanded = {};   // 所持キャラを全部展開にした行

  // タブごとに条件を持つ。アクティブとリーダーは別物として扱う。
  var S = {
    active: { q:"", attrs:[], cats:[], my:[], aw:[], cdMax:30, assist:"any", sort:"newest" },
    leader: { q:"", attrs:[], cats:[], my:[], aw:[], multMin:0, assist:"any", sort:"newest" },
    chars:  { q:"", attrs:[], cats:[], my:[], aw:[], cdMax:30, multMin:0,
              assist:"any", sort:"newest" }
  };

  var el = {};
  ["q","cats","scroller","viewport","state","stamp","hits","sort",
   "cdMax","cdOut","multMin","multOut","cdGroup","multGroup",
   "nActive","nLeader","toggleCats",
   "notePanel","noteToggle","assistGroup","nChars",
   "awpick","awpickList","awFilter","awPickToggle","awPickClear","awPickGroup",
   "mycatChips","mcAdd","mcForm","mcName","mcPattern","mcScope","mcPreview",
   "mcSave","mcCancel","mcHint","mcIo","mcIoToggle","mcJson","mcLoad"].forEach(function (id) {
    el[id] = document.getElementById(id);
  });

  // ================= マイカテゴリ =================
  // 自動分類（DATA.cats）とは別に、利用者が名前と条件を決めて足せるもの。
  // 条件は説明文・スキル名への正規表現マッチ、または手動で入れたスキルIDの集合。
  var MYCATS = [];
  var STORE_KEY = "pad-skill-archive:mycats";
  var storageOK = true;
  var pinOpen = {};

  function compileMy() {
    MYCATS.forEach(function (mc) {
      try {
        mc._re = mc.pattern ? new RegExp(mc.pattern, "i") : null;
        mc._bad = false;
      } catch (e) { mc._re = null; mc._bad = true; }
      if (!mc.ids) mc.ids = [];
      if (!mc.scope) mc.scope = "both";
    });
  }

  function matchMy(mc, r) {
    if (mc.ids.indexOf(r[0]) !== -1) return true;
    if (!mc._re) return false;
    return mc._re.test(r[2]) || mc._re.test(r[1]);
  }

  function myInScope(mc) {
    // 統合タブは両方のスキルを持つ行なので、どのスコープも対象になる
    return tab === "chars" || mc.scope === "both" || mc.scope === tab;
  }

  function visibleMy() { return MYCATS.filter(myInScope); }

  function countMy(mc) {
    var n = 0, rows;
    ["active","leader"].forEach(function (k) {
      if (mc.scope !== "both" && mc.scope !== k) return;
      rows = DATA[k];
      for (var i = 0; i < rows.length; i++) if (matchMy(mc, rows[i])) n++;
    });
    return n;
  }

  function saveMy() {
    var plain = MYCATS.map(function (mc) {
      return { name: mc.name, pattern: mc.pattern, scope: mc.scope, ids: mc.ids };
    });
    try {
      localStorage.setItem(STORE_KEY, JSON.stringify(plain));
      storageOK = true;
    } catch (e) {
      storageOK = false;
    }
    el.mcHint.textContent = storageOK ? ""
      : "この環境では保存できないので、JSONを控えておいてください";
    if (!el.mcIo.hidden) el.mcJson.value = JSON.stringify(plain, null, 2);
  }

  function loadMy() {
    var raw = null;
    try { raw = localStorage.getItem(STORE_KEY); }
    catch (e) { storageOK = false; }
    if (raw) {
      try { MYCATS = JSON.parse(raw); } catch (e) { MYCATS = []; }
    }
    if (!MYCATS.length && window.DEFAULT_MYCATS) {
      MYCATS = JSON.parse(JSON.stringify(window.DEFAULT_MYCATS));
    }
    compileMy();
  }

  function renderMyCats() {
    var html = "";
    MYCATS.forEach(function (mc, i) {
      if (!myInScope(mc)) return;
      var on = S[tab].my.indexOf(i) !== -1;
      html += '<span class="mycat" aria-pressed="' + on + '">' +
                '<button class="mc-on" data-i="' + i + '">' +
                  escapeHtml(mc.name) + (mc._bad ? " ⚠" : "") +
                  "<em>" + countMy(mc).toLocaleString() + "</em></button>" +
                '<button class="mc-del" data-del="' + i + '" title="削除">×</button>' +
              "</span>";
    });
    el.mycatChips.innerHTML = html;
  }

  // 図鑑番号 -> その子が持つ覚醒の集合。スキル側から覚醒で絞るのに使う。
  var MON_AW = null;

  function buildMonAw() {
    MON_AW = new Map();
    DATA.awoken.forEach(function (m) {
      var set = new Set(m[3]);
      for (var i = 0; i < m[4].length; i++) set.add(m[4][i]);
      MON_AW.set(m[0], set);
    });
  }

  // 「選んだ覚醒をすべて持つキャラ」が1体でも所持していればそのスキルを残す
  function skillHasAwakenings(r, want) {
    for (var i = 0; i < r[7].length; i++) {
      var set = MON_AW.get(r[7][i]);
      if (!set) continue;
      var all = true;
      for (var j = 0; j < want.length; j++) {
        if (!set.has(want[j])) { all = false; break; }
      }
      if (all) return true;
    }
    return false;
  }

  // 引き出しに出す件数は「そのタブで何件のスキルが該当するか」。
  // 8,774件×所持キャラ×覚醒 を毎回なぞると1秒近くかかるのでタブ単位で覚えておく。
  var awCountCache = {};

  function awSkillCounts() {
    if (awCountCache[tab]) return awCountCache[tab];
    var counts = {};
    var rows = DATA[tab];

    if (tab === "chars") {
      // 統合タブは行がキャラなので、そのキャラ自身の覚醒をそのまま数える
      for (var c = 0; c < rows.length; c++) {
        var seenC = {};
        rows[c][3].concat(rows[c][4]).forEach(function (a) {
          if (seenC[a]) return;
          seenC[a] = 1;
          counts[a] = (counts[a] || 0) + 1;
        });
      }
      awCountCache[tab] = counts;
      return counts;
    }

    for (var i = 0; i < rows.length; i++) {
      var seen = {};
      var mons = rows[i][7];
      for (var h = 0; h < mons.length; h++) {
        var set = MON_AW.get(mons[h]);
        if (!set) continue;
        set.forEach(function (a) {
          if (seen[a]) return;
          seen[a] = 1;
          counts[a] = (counts[a] || 0) + 1;
        });
      }
    }
    awCountCache[tab] = counts;
    return counts;
  }

  // 136個を頻度順に並べると関連するものが散らばるので、
  // ETL側で名前ごとに束ねた順（DATA.awgroups）で出す。名前はアイコンの
  // ツールチップに寄せて、一覧はアイコンだけにしてある。
  function renderAwPick() {
    var counts = awSkillCounts();
    var needle = el.awFilter.value.trim();
    var sel = S[tab].aw;
    var unit = tab === "chars" ? "体" : "件";
    var html = "";

    (DATA.awgroups || []).forEach(function (grp) {
      var ids = grp[1].filter(function (id) {
        if (!counts[id]) return false;
        return !needle || awName(id).indexOf(needle) !== -1;
      });
      if (!ids.length) return;
      html += '<div class="awgrp"><span class="awgrp-label">' + escapeHtml(grp[0]) +
              '</span><div class="awgrp-items">';
      ids.forEach(function (id) {
        html += '<button class="awchip is-icon" type="button" aria-pressed="' +
                (sel.indexOf(id) !== -1) + '" data-awp="' + id + '" title="' +
                escapeHtml(awName(id)) + " · " + counts[id].toLocaleString() + unit +
                '">' + awIcon(id, true) + "</button>";
      });
      html += "</div></div>";
    });

    el.awpickList.innerHTML = html ||
      '<span class="none">該当する覚醒がありません。</span>';
  }

  function syncAwPickLabel() {
    var n = S[tab].aw.length;
    el.awPickToggle.textContent = n ? "覚醒 " + n + " 件で絞り込み中" : "覚醒で絞る";
  }

  // 覚醒アシストを持つキャラはアシスト運用されるので、素早く引けるよう集合にしておく
  var ASSIST = null;
  function isAssist(mid) { return ASSIST !== null && ASSIST.has(mid); }
  function skillHasAssist(r) {
    for (var i = 0; i < r[7].length; i++) if (isAssist(r[7][i])) return true;
    return false;
  }

  // ================= 覚醒 =================
  var AW_H = 30;   // アイコン1コマの高さ

  function awIcon(id, small) {
    var h = small ? 22 : AW_H;
    return '<span class="aw' + (small ? " aw-sm" : "") + '" title="' +
           escapeHtml(awName(id)) + '" style="background-position:0 -' +
           (id * h) + 'px"></span>';
  }

  function awName(id) {
    var n = DATA.awnames[String(id)];
    return n ? n : "覚醒 #" + id;
  }



  // ================= 統合（1行 = キャラ） =================
  // アクティブ・リーダー・覚醒はデータ上どれもモンスターにぶら下がっているので、
  // 行をキャラに揃えれば3つを同時に絞り込める。
  var UNI_CATS = [];

  function buildChars() {
    var byActive = new Map(), byLeader = new Map();
    DATA.active.forEach(function (r, i) { r[7].forEach(function (m) { byActive.set(m, i); }); });
    DATA.leader.forEach(function (r, i) { r[7].forEach(function (m) { byLeader.set(m, i); }); });

    var aw = new Map();
    DATA.awoken.forEach(function (m) { aw.set(m[0], m); });

    // カテゴリはアクティブ側とリーダー側で語彙が別なので、名前で1本にまとめる
    UNI_CATS = [];
    var idx = {};
    ["active", "leader"].forEach(function (k) {
      DATA.cats[k].forEach(function (n) {
        if (!(n in idx)) { idx[n] = UNI_CATS.length; UNI_CATS.push(n); }
      });
    });
    var mapA = DATA.cats.active.map(function (n) { return idx[n]; });
    var mapL = DATA.cats.leader.map(function (n) { return idx[n]; });

    DATA.chars = Object.keys(DATA.mons).map(function (k) {
      var id = Number(k), m = DATA.mons[k], a = aw.get(id);
      var ai = byActive.has(id) ? byActive.get(id) : -1;
      var li = byLeader.has(id) ? byLeader.get(id) : -1;
      var cats = [];
      function push(u) { if (cats.indexOf(u) === -1) cats.push(u); }
      if (ai >= 0) DATA.active[ai][4].forEach(function (c) { push(mapA[c]); });
      if (li >= 0) DATA.leader[li][4].forEach(function (c) { push(mapL[c]); });
      // [図鑑番号, 名前, 属性, 覚醒, 超覚醒, アクティブ行, リーダー行, カテゴリ]
      return [id, m[0], m[1], a ? a[3] : [], a ? a[4] : [], ai, li, cats];
    }).sort(function (x, y) { return y[0] - x[0]; });
  }

  function charMatchesText(r, q) {
    if (r[1].indexOf(q) !== -1) return true;
    var a = r[5] >= 0 ? DATA.active[r[5]] : null;
    if (a && (a[2].indexOf(q) !== -1 || a[10].indexOf(q) !== -1 || a[1].indexOf(q) !== -1)) return true;
    var l = r[6] >= 0 ? DATA.leader[r[6]] : null;
    if (l && (l[2].indexOf(q) !== -1 || l[10].indexOf(q) !== -1 || l[1].indexOf(q) !== -1)) return true;
    return false;
  }

  function applyChars() {
    var s = S.chars;
    var q = s.q.trim();
    var isNum = /^\d+$/.test(q);
    var qBare = q.replace(/[\[\]]/g, "");
    var out = [];

    for (var i = 0; i < DATA.chars.length; i++) {
      var r = DATA.chars[i];

      if (s.attrs.length) {
        var ok = true;
        for (var a = 0; a < s.attrs.length; a++) {
          if (r[2].indexOf(s.attrs[a]) === -1) { ok = false; break; }
        }
        if (!ok) continue;
      }

      if (s.aw.length) {
        var oka = true;
        for (var w = 0; w < s.aw.length; w++) {
          if (r[3].indexOf(s.aw[w]) === -1 && r[4].indexOf(s.aw[w]) === -1) { oka = false; break; }
        }
        if (!oka) continue;
      }

      if (s.cats.length) {
        var okc = true;
        for (var c = 0; c < s.cats.length; c++) {
          if (r[7].indexOf(s.cats[c]) === -1) { okc = false; break; }
        }
        if (!okc) continue;
      }

      if (s.assist !== "any") {
        var hasA = isAssist(r[0]);
        if (s.assist === "only" && !hasA) continue;
        if (s.assist === "not" && hasA) continue;
      }

      if (s.cdMax < 30) {
        if (r[5] < 0 || DATA.active[r[5]][3] > s.cdMax) continue;
      }
      if (s.multMin > 0) {
        if (r[6] < 0 || !(DATA.leader[r[6]][6] >= s.multMin)) continue;
      }

      if (s.my.length) {
        var okm = true;
        for (var mi = 0; mi < s.my.length; mi++) {
          var mc = MYCATS[s.my[mi]];
          var hit = (r[5] >= 0 && matchMy(mc, DATA.active[r[5]])) ||
                    (r[6] >= 0 && matchMy(mc, DATA.leader[r[6]]));
          if (!hit) { okm = false; break; }
        }
        if (!okm) continue;
      }

      if (q) {
        if (isNum) { if (String(r[0]) !== q) continue; }
        else if (!charMatchesText(r, q) && !charMatchesText(r, qBare)) continue;
      }

      out.push(r);
    }

    if (s.sort === "oldest") out.sort(function (x, y) { return x[0] - y[0]; });
    else if (s.sort === "holders") out.sort(function (x, y) {
      return (y[3].length + y[4].length) - (x[3].length + x[4].length) || y[0] - x[0];
    });
    else if (s.sort === "skill") out.sort(function (x, y) {
      var cx = x[5] >= 0 ? DATA.active[x[5]][3] : 99;
      var cy = y[5] >= 0 ? DATA.active[y[5]][3] : 99;
      return cx - cy || y[0] - x[0];
    });
    else out.sort(function (x, y) { return y[0] - x[0]; });

    view = out;
    el.hits.textContent = out.length.toLocaleString() + " 体";
    if (!out.length) {
      showState("該当なし", "条件をゆるめるか、別の言い回しを試してください。");
      return;
    }
    hideState();
    window.scrollTo(0, 0);
    render();
  }

  function skillBlock(r, kind) {
    var isL = kind === "leader";
    if (!r) {
      return '<div class="uni-block is-empty"><span class="uni-label' +
             (isL ? " is-leader" : "") + '">' + (isL ? "LEADER" : "ACTIVE") +
             '</span><div class="uni-empty">なし</div></div>';
    }
    var meta = isL
      ? (r[6] ? '<span class="row-cd">最大 ×' + r[6] + "</span>" : "")
      : (r[3] ? '<span class="row-cd">初期CD ' + r[3] + "</span>" : "");
    return '<div class="uni-block">' +
      '<div class="uni-top"><span class="uni-label' + (isL ? " is-leader" : "") + '">' +
        (isL ? "LEADER" : "ACTIVE") + "</span>" +
        '<span class="uni-id">#' + r[0] + "</span>" + meta + "</div>" +
      '<div class="uni-name">' + highlight(r[1] || "(名称なし)") + "</div>" +
      '<div class="uni-desc">' + highlight(r[2]) + "</div></div>";
  }

  function charRowHtml(r) {
    var dots = "";
    for (var i = 0; i < r[2].length; i++) {
      dots += '<b style="background:' + ATTR_COLOR[r[2][i]] + '"></b>';
    }
    var aw = "";
    for (var j = 0; j < r[3].length; j++) aw += awIcon(r[3][j]);
    var sup = "";
    for (var k = 0; k < r[4].length; k++) sup += awIcon(r[4][k]);

    return '<div class="crow">' +
      '<div class="crow-head">' +
        '<span class="mrow-attrs">' + dots + "</span>" +
        '<span class="mrow-id">No.' + r[0] + "</span>" +
        '<span class="mrow-name">' + highlight(r[1]) + "</span>" +
        (isAssist(r[0]) ? '<span class="assist-mark">アシスト</span>' : "") +
      "</div>" +
      (aw || sup ? '<div class="aw-row crow-aw">' + aw +
        (sup ? '<span class="aw-super">' + sup + "</span>" : "") + "</div>" : "") +
      '<div class="uni">' +
        skillBlock(r[5] >= 0 ? DATA.active[r[5]] : null, "active") +
        skillBlock(r[6] >= 0 ? DATA.leader[r[6]] : null, "leader") +
      "</div></div>";
  }

  function showState(t, b) {
    el.state.hidden = false;
    el.state.innerHTML = "<strong>" + t + "</strong>" + (b || "");
    el.viewport.innerHTML = "";
  }
  function hideState() { el.state.hidden = true; }

  function b64ToBytes(b64) {
    var bin = atob(b64), n = bin.length, out = new Uint8Array(n);
    for (var i = 0; i < n; i++) out[i] = bin.charCodeAt(i);
    return out;
  }

  function load() {
    var bytes = b64ToBytes(document.getElementById("payload").textContent.trim());
    if (typeof DecompressionStream === "undefined") {
      showState("このブラウザでは展開できません",
        "gzip の展開に DecompressionStream を使っています。新しめの Chrome・Edge・Firefox・Safari で開いてください。");
      return;
    }
    var st = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("gzip"));
    new Response(st).text().then(function (txt) {
      DATA = JSON.parse(txt);
      MONS = DATA.mons;
      ASSIST = new Set(DATA.assist || []);
      buildMonAw();
      buildChars();
      el.nChars.textContent = DATA.chars.length.toLocaleString();

      // 検索用にキャラ名をあらかじめ連結しておく
      ["active","leader"].forEach(function (k) {
        DATA[k].forEach(function (r) {
          var names = "", ids = "";
          for (var i = 0; i < r[7].length; i++) {
            var m = MONS[r[7][i]];
            if (m) names += m[0] + " ";
            ids += r[7][i] + " ";
          }
          r.push(names);                          // [8] 所持キャラ名
          r.push(ids);                            // [9] 図鑑番号
          r.push(r[2].replace(/[\[\]]/g, ""));    // [10] 角括弧を外した説明文
        });
      });

      el.nActive.textContent = DATA.active.length.toLocaleString();
      el.nLeader.textContent = DATA.leader.length.toLocaleString();
      el.stamp.textContent = "モンスター " + Object.keys(MONS).length.toLocaleString() + " 体";
      loadMy();
      renderMyCats();
      saveMy();
      buildCats();
      apply();
    }).catch(function (e) { showState("データを読み込めませんでした", String(e)); });
  }

  function buildCats() {
    var isChars = tab === "chars";
    var names = isChars ? UNI_CATS : DATA.cats[tab];
    var counts = new Array(names.length).fill(0);
    DATA[tab].forEach(function (r) {
      var list = isChars ? r[7] : r[4];
      for (var i = 0; i < list.length; i++) counts[list[i]]++;
    });
    var order = names.map(function (n, i) { return { n:n, i:i, c:counts[i] }; })
                     .sort(function (a, b) { return b.c - a.c; });
    var html = "";
    order.forEach(function (t) {
      html += '<button class="cat" type="button" aria-pressed="' +
              (S[tab].cats.indexOf(t.i) !== -1) + '" data-cat="' + t.i + '">' +
              t.n + "<em>" + t.c.toLocaleString() + "</em></button>";
    });
    el.cats.innerHTML = html;
  }

  // r[7] は図鑑番号の昇順なので、末尾が「そのスキルを持つ一番新しいキャラ」になる
  function newestOf(r) { return r[7].length ? r[7][r[7].length - 1] : 0; }

  function oldestOf(r) { return r[7].length ? r[7][0] : 0; }

  // r[7] は図鑑番号の昇順。末尾が最新、先頭が最古のキャラ。
  function sortRows(list) {
    var mode = S[tab].sort;
    if (mode === "skill") {
      list.sort(function (a, b) { return a[0] - b[0]; });
    } else if (mode === "holders") {
      list.sort(function (a, b) {
        return (b[7].length - a[7].length) || (newestOf(b) - newestOf(a));
      });
    } else if (mode === "oldest") {
      list.sort(function (a, b) {
        return (oldestOf(a) - oldestOf(b)) || (a[0] - b[0]);
      });
    } else {
      list.sort(function (a, b) {
        return (newestOf(b) - newestOf(a)) || (b[0] - a[0]);
      });
    }
    return list;
  }


  function apply() {
    if (tab === "chars") { applyChars(); return; }
    var s = S[tab];
    var rows = DATA[tab];
    var q = s.q.trim();
    var qLower = q.toLowerCase();
    var isNum = /^\d+$/.test(q);
    var qNum = isNum ? Number(q) : -1;
    // ゲーム内表記は [火] のように角括弧つき。入力側と本文側の両方から外して照合する
    var qBare = q.replace(/[\[\]]/g, "");
    var out = [];

    for (var i = 0; i < rows.length; i++) {
      var r = rows[i];

      if (s.attrs.length) {
        var ok = true;
        for (var a = 0; a < s.attrs.length; a++) {
          if (r[5].indexOf(s.attrs[a]) === -1) { ok = false; break; }
        }
        if (!ok) continue;
      }

      if (s.cats.length) {
        var okc = true;
        for (var c = 0; c < s.cats.length; c++) {
          if (r[4].indexOf(s.cats[c]) === -1) { okc = false; break; }
        }
        if (!okc) continue;
      }

      if (s.my.length) {
        var okm = true;
        for (var mi = 0; mi < s.my.length; mi++) {
          if (!matchMy(MYCATS[s.my[mi]], r)) { okm = false; break; }
        }
        if (!okm) continue;
      }

      if (s.aw.length && !skillHasAwakenings(r, s.aw)) continue;

      if (s.assist !== "any") {
        var hasA = skillHasAssist(r);
        if (s.assist === "only" && !hasA) continue;
        if (s.assist === "not" && hasA) continue;
      }

      if (tab === "active" && s.cdMax < 30 && r[3] > s.cdMax) continue;
      if (tab === "leader" && s.multMin > 0 && !(r[6] >= s.multMin)) continue;

      if (q) {
        if (isNum) {
          // 数字だけの入力は図鑑番号／スキルIDの完全一致として扱う。
          // 説明文の中の数字に引っかかると探しものが埋もれるため。
          if (String(r[0]) !== q && r[7].indexOf(qNum) === -1) continue;
        } else if (r[2].indexOf(q) === -1 &&
                   r[10].indexOf(qBare) === -1 &&
                   r[1].indexOf(q) === -1 &&
                   r[8].indexOf(q) === -1 &&
                   r[1].toLowerCase().indexOf(qLower) === -1) {
          continue;
        }
      }

      out.push(r);
    }

    view = sortRows(out);
    el.hits.textContent = out.length.toLocaleString() + " 件";

    if (!out.length) {
      showState("該当なし",
        "条件をゆるめるか、別の言い回しを試してください。<br>" +
        "スキル文はゲーム内表記そのままなので、属性は「[火]」のように角括弧つきで書かれています。");
      return;
    }
    hideState();
    window.scrollTo(0, 0);
    render();
  }

  function escapeHtml(s) {
    return s.replace(/[&<>"]/g, function (c) {
      return { "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;" }[c];
    });
  }

  function highlight(text) {
    var safe = escapeHtml(text).replace(/\n/g, "<br>");
    var q = S[tab].q.trim();
    if (!q) return safe;
    // 入力に括弧が無くても本文の [火] などに印がつくようにする
    var pattern = q.split("").map(function (ch) {
      var e = escapeHtml(ch).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      return e + "(?:<br>)?";
    }).join("[\\[\\]]*");
    try {
      return safe.replace(new RegExp(pattern, "g"), function (m) { return "<mark>" + m + "</mark>"; });
    } catch (e) { return safe; }
  }

  function monChip(id) {
    var m = MONS[id];
    if (!m) return "";
    var dots = "";
    for (var i = 0; i < m[1].length; i++) {
      dots += '<b style="background:' + ATTR_COLOR[m[1][i]] + '"></b>';
    }
    var assist = isAssist(Number(id));
    return '<span class="mon' + (assist ? " is-assist" : "") + '"><i>' + dots +
           "</i><u>No." + id + "</u>" + escapeHtml(m[0]) +
           (assist ? '<span class="assist-mark">アシスト</span>' : "") + "</span>";
  }

  function rowHtml(r, idx) {
    var rail = "";
    for (var i = 0; i < ATTR_ORDER.length; i++) {
      if (r[5].indexOf(ATTR_ORDER[i]) !== -1) {
        rail += '<span style="background:' + ATTR_COLOR[ATTR_ORDER[i]] + '"></span>';
      }
    }

    // 元データは昇順。新しいキャラ順に見せたいので反転する
    // 先頭8体しか出さないので、並び順の基準になったキャラが隠れないよう向きを揃える
    var asc = S[tab].sort === "oldest" || S[tab].sort === "skill";
    var mons = asc ? r[7] : r[7].slice().reverse();
    var key = tab + ":" + r[0];
    var openAll = !!expanded[key];
    var limit = openAll ? mons.length : Math.min(MON_LIMIT, mons.length);
    var chips = "";
    for (var j = 0; j < limit; j++) chips += monChip(mons[j]);
    if (mons.length > MON_LIMIT) {
      chips += '<button class="mon-more" data-key="' + key + '">' +
               (openAll ? "畳む" : "他 " + (mons.length - MON_LIMIT) + " 体") + "</button>";
    }

    var marks = "";
    if (r[4].length) {
      marks = '<div class="cat-marks">';
      for (var k = 0; k < r[4].length; k++) {
        marks += '<span class="cat-mark">' + DATA.cats[tab][r[4][k]] + "</span>";
      }
      marks += "</div>";
    }

    // マイカテゴリへの出し入れ
    var mine = visibleMy();
    var inCount = 0;
    mine.forEach(function (mc) { if (mc.ids.indexOf(r[0]) !== -1) inCount++; });
    var pinKey = tab + ":" + r[0];
    var pin = '<button class="pin' + (inCount ? " on" : "") + '" data-pin="' + r[0] + '">' +
              (inCount ? "★ " + inCount : "＋ マイ") + "</button>";
    var pinPanel = "";
    if (pinOpen[pinKey]) {
      pinPanel = '<div class="pin-panel">';
      if (!mine.length) {
        pinPanel += '<span class="empty">まだマイカテゴリがありません。上の「＋ 追加」から作れます。</span>';
      } else {
        MYCATS.forEach(function (mc, i) {
          if (!myInScope(mc)) return;
          var has = mc.ids.indexOf(r[0]) !== -1;
          pinPanel += '<button data-put="' + i + '" data-sid="' + r[0] +
                      '" aria-pressed="' + has + '">' + escapeHtml(mc.name) + "</button>";
        });
      }
      pinPanel += "</div>";
    }

    var meta = "";
    if (tab === "active" && r[3]) meta = '<span class="row-cd">初期CD ' + r[3] + "</span>";
    else if (tab === "leader" && r[6]) meta = '<span class="row-cd">最大 ×' + r[6] + "</span>";

    return '<div class="row">' +
      '<div class="rail">' + rail + "</div>" +
      '<div class="row-body">' +
        '<div class="row-head">' +
          '<span class="row-id">#' + r[0] + "</span>" +
          '<span class="row-name">' + escapeHtml(r[1] || "(名称なし)") + "</span>" +
          meta + pin +
        "</div>" +
        '<div class="row-desc">' + highlight(r[2]) + "</div>" +
        pinPanel +
        '<div class="holders"><span class="holders-label">所持 ' + mons.length + "体</span>" +
          chips + "</div>" +
        marks +
      "</div></div>";
  }

  function renderMore() {
    if (shown >= view.length) return;
    var end = Math.min(view.length, shown + CHUNK), html = "";
    for (var i = shown; i < end; i++) {
      html += tab === "chars" ? charRowHtml(view[i]) : rowHtml(view[i], i);
    }
    el.viewport.insertAdjacentHTML("beforeend", html);
    shown = end;
  }
  function fill() {
    var g = 0;
    while (shown < view.length &&
           document.documentElement.scrollHeight <= window.innerHeight + 400 && g++ < 40) renderMore();
  }
  function render() { el.viewport.innerHTML = ""; shown = 0; renderMore(); fill(); }

  // ---------- 入力 ----------
  var timer = null;
  function debounce(fn) { clearTimeout(timer); timer = setTimeout(fn, 130); }

  el.q.addEventListener("input", function () {
    debounce(function () { S[tab].q = el.q.value; apply(); });
  });

  document.getElementById("tabs").addEventListener("click", function (e) {
    var b = e.target.closest("button"); if (!b) return;
    tab = b.dataset.tab;
    [].forEach.call(this.querySelectorAll("button"), function (x) {
      x.setAttribute("aria-selected", String(x === b));
    });
    syncControls();
    buildCats();
    renderMyCats();
    if (!el.awpick.hidden) renderAwPick();
    apply();
  });

  function syncControls() {
    var s = S[tab];
    var isChars = tab === "chars";
    el.q.value = s.q;
    el.sort.value = s.sort;
    syncAwPickLabel();
    var healOrb = document.querySelector('.orb[data-attr="heal"]');
    healOrb.hidden = isChars;
    if (isChars && s.attrs.indexOf("heal") !== -1) {
      s.attrs = s.attrs.filter(function (x) { return x !== "heal"; });
    }
    // 統合タブでは初期CDも攻撃倍率も両方意味を持つ
    [].forEach.call(document.querySelectorAll("#assistSeg button"), function (x) {
      x.setAttribute("aria-pressed", String(x.dataset.assist === s.assist));
    });
    el.cdGroup.hidden = !(tab === "active" || isChars);
    el.multGroup.hidden = !(tab === "leader" || isChars);
    el.toggleCats.textContent = el.cats.classList.contains("is-open")
      ? "カテゴリを畳む" : "カテゴリを広げる";
    el.q.placeholder = isChars
      ? "キャラ名・スキル文・スキル名で検索（数字だけなら図鑑番号）"
      : "スキル文・スキル名・キャラ名で検索（数字だけなら図鑑番号／スキルID）";
    [].forEach.call(document.querySelectorAll(".orb"), function (o) {
      o.setAttribute("aria-pressed", String(s.attrs.indexOf(o.dataset.attr) !== -1));
    });
    if (s.cdMax !== undefined) {
      el.cdMax.value = s.cdMax;
      el.cdOut.textContent = s.cdMax >= 30 ? "指定なし" : s.cdMax + "ターン以下";
    }
    if (s.multMin !== undefined) {
      el.multMin.value = s.multMin;
      el.multOut.textContent = s.multMin === 0 ? "指定なし" : "×" + s.multMin + "以上";
    }
  }

  document.getElementById("orbs").addEventListener("click", function (e) {
    var b = e.target.closest("button"); if (!b) return;
    var on = b.getAttribute("aria-pressed") !== "true";
    b.setAttribute("aria-pressed", String(on));
    var a = b.dataset.attr, s = S[tab];
    s.attrs = on ? s.attrs.concat([a]) : s.attrs.filter(function (x) { return x !== a; });
    apply();
  });

  el.cats.addEventListener("click", function (e) {
    var b = e.target.closest(".cat"); if (!b) return;
    var on = b.getAttribute("aria-pressed") !== "true";
    b.setAttribute("aria-pressed", String(on));
    var i = Number(b.dataset.cat), s = S[tab];
    s.cats = on ? s.cats.concat([i]) : s.cats.filter(function (x) { return x !== i; });
    apply();
  });

  // マイカテゴリのチップ操作
  el.mycatChips.addEventListener("click", function (e) {
    var del = e.target.closest(".mc-del");
    if (del) {
      var di = Number(del.dataset.del);
      if (!confirm("マイカテゴリ「" + MYCATS[di].name + "」を削除します。よろしいですか。")) return;
      MYCATS.splice(di, 1);
      // 選択中の添字が繰り上がるので張り直す
      ["active","leader"].forEach(function (k) {
        S[k].my = S[k].my.filter(function (x) { return x !== di; })
                         .map(function (x) { return x > di ? x - 1 : x; });
      });
      compileMy(); saveMy(); renderMyCats(); apply();
      return;
    }
    var on = e.target.closest(".mc-on");
    if (!on) return;
    var i = Number(on.dataset.i), sel = S[tab].my;
    S[tab].my = sel.indexOf(i) === -1 ? sel.concat([i])
                                      : sel.filter(function (x) { return x !== i; });
    renderMyCats(); apply();
  });

  // 追加フォーム
  function previewMy() {
    var pat = el.mcPattern.value.trim();
    if (!pat) { el.mcPreview.textContent = "–"; el.mcPreview.className = "mc-preview"; return; }
    try {
      var probe = { pattern: pat, scope: el.mcScope.value, ids: [] };
      probe._re = new RegExp(pat, "i");
      el.mcPreview.textContent = "該当 " + countMy(probe).toLocaleString() + " 件";
      el.mcPreview.className = "mc-preview";
    } catch (err) {
      el.mcPreview.textContent = "正規表現エラー";
      el.mcPreview.className = "mc-preview bad";
    }
  }
  el.mcPattern.addEventListener("input", function () { clearTimeout(timer); timer = setTimeout(previewMy, 200); });
  el.mcScope.addEventListener("change", previewMy);

  el.mcAdd.addEventListener("click", function () {
    el.mcForm.hidden = !el.mcForm.hidden;
    if (!el.mcForm.hidden) { el.mcName.value = ""; el.mcPattern.value = ""; previewMy(); el.mcName.focus(); }
  });
  el.mcCancel.addEventListener("click", function () { el.mcForm.hidden = true; });

  el.mcSave.addEventListener("click", function () {
    var name = el.mcName.value.trim();
    var pat = el.mcPattern.value.trim();
    if (!name) { el.mcName.focus(); return; }
    if (pat) { try { new RegExp(pat, "i"); } catch (err) { el.mcPattern.focus(); return; } }
    MYCATS.push({ name: name, pattern: pat, scope: el.mcScope.value, ids: [] });
    compileMy(); saveMy(); renderMyCats();
    el.mcForm.hidden = true;
    render();
  });

  el.mcName.addEventListener("keydown", function (e) { if (e.key === "Enter") el.mcSave.click(); });
  el.mcPattern.addEventListener("keydown", function (e) { if (e.key === "Enter") el.mcSave.click(); });

  // JSONでの持ち出しと取り込み
  el.mcIoToggle.addEventListener("click", function () {
    el.mcIo.hidden = !el.mcIo.hidden;
    if (!el.mcIo.hidden) {
      el.mcJson.value = JSON.stringify(MYCATS.map(function (mc) {
        return { name: mc.name, pattern: mc.pattern, scope: mc.scope, ids: mc.ids };
      }), null, 2);
    }
  });
  el.mcLoad.addEventListener("click", function () {
    var parsed;
    try { parsed = JSON.parse(el.mcJson.value); }
    catch (e) { alert("JSONとして読めませんでした。"); return; }
    if (!Array.isArray(parsed)) { alert("配列の形で書いてください。"); return; }
    MYCATS = parsed;
    ["active","leader"].forEach(function (k) { S[k].my = []; });
    compileMy(); saveMy(); renderMyCats(); apply();
  });

  // 行からの出し入れ
  el.viewport.addEventListener("click", function (e) {
    var pin = e.target.closest(".pin");
    if (pin) {
      var k = tab + ":" + pin.dataset.pin;
      pinOpen[k] = !pinOpen[k];
      render();
      return;
    }
    var put = e.target.closest("[data-put]");
    if (!put) return;
    var mc = MYCATS[Number(put.dataset.put)], sid = Number(put.dataset.sid);
    var at = mc.ids.indexOf(sid);
    if (at === -1) mc.ids.push(sid); else mc.ids.splice(at, 1);
    saveMy(); renderMyCats(); apply();
  });

  el.awPickToggle.addEventListener("click", function () {
    el.awpick.hidden = !el.awpick.hidden;
    if (!el.awpick.hidden) { renderAwPick(); el.awFilter.focus(); }
  });

  el.awFilter.addEventListener("input", function () {
    clearTimeout(timer); timer = setTimeout(renderAwPick, 150);
  });

  el.awpickList.addEventListener("click", function (e) {
    var b = e.target.closest("[data-awp]"); if (!b) return;
    var id = Number(b.dataset.awp), sel = S[tab].aw;
    S[tab].aw = sel.indexOf(id) === -1 ? sel.concat([id])
                                       : sel.filter(function (x) { return x !== id; });
    b.setAttribute("aria-pressed", String(S[tab].aw.indexOf(id) !== -1));
    syncAwPickLabel();
    apply();
  });

  el.awPickClear.addEventListener("click", function () {
    S[tab].aw = [];
    syncAwPickLabel();
    renderAwPick();
    apply();
  });

  document.getElementById("assistSeg").addEventListener("click", function (e) {
    var b = e.target.closest("button"); if (!b) return;
    [].forEach.call(this.querySelectorAll("button"), function (x) {
      x.setAttribute("aria-pressed", String(x === b));
    });
    S[tab].assist = b.dataset.assist;
    apply();
  });

  el.sort.addEventListener("change", function () {
    S[tab].sort = el.sort.value;
    apply();
  });

  // 統合タブでも使うので、書き込み先は今のタブの状態にする
  el.cdMax.addEventListener("input", function () {
    var v = Number(el.cdMax.value);
    S[tab].cdMax = v;
    el.cdOut.textContent = v >= 30 ? "指定なし" : v + "ターン以下";
    debounce(apply);
  });
  el.multMin.addEventListener("input", function () {
    var v = Number(el.multMin.value);
    S[tab].multMin = v;
    el.multOut.textContent = v === 0 ? "指定なし" : "×" + v + "以上";
    debounce(apply);
  });

  el.viewport.addEventListener("click", function (e) {
    var b = e.target.closest(".mon-more"); if (!b) return;
    expanded[b.dataset.key] = !expanded[b.dataset.key];
    render();
  });

  document.getElementById("reset").addEventListener("click", function () {
    if (tab === "chars") S.chars = { q:"", attrs:[], cats:[], my:[], aw:[], cdMax:30,
                                     multMin:0, assist:"any", sort:"newest" };
    else if (tab === "active") S.active = { q:"", attrs:[], cats:[], my:[], aw:[], cdMax:30, assist:"any", sort:"newest" };
    else S.leader = { q:"", attrs:[], cats:[], my:[], aw:[], multMin:0, assist:"any", sort:"newest" };
    syncControls();
    buildCats();
    renderMyCats();
    if (!el.awpick.hidden) renderAwPick();
    apply();
  });

  el.noteToggle.addEventListener("click", function () {
    el.notePanel.hidden = !el.notePanel.hidden;
    this.textContent = el.notePanel.hidden ? "この表の見かた" : "閉じる";
    // 下の方で開いても見えないので先頭に戻す
    if (!el.notePanel.hidden) window.scrollTo(0, 0);
  });

  el.toggleCats.addEventListener("click", function () {
    this.textContent = el.cats.classList.toggle("is-open") ? "カテゴリを畳む" : "カテゴリを広げる";
  });

  window.addEventListener("scroll", function () {
    if (window.innerHeight + window.pageYOffset >
        document.documentElement.scrollHeight - 700) renderMore();
  }, { passive: true });

  window.addEventListener("resize", fill);
  document.addEventListener("keydown", function (e) {
    if (e.key === "/" && document.activeElement !== el.q) { e.preventDefault(); el.q.focus(); }
  });

  syncControls();
  load();
})();
</script>
</body>
</html>
"""


def load_mycategories(path):
    """任意。置いておくとマイカテゴリの初期値としてHTMLに焼き込まれる。

    形式: [{"name": "変身", "pattern": "変身|転生", "scope": "both", "ids": []}]
    scope は "both" / "active" / "leader"。
    """
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit(f"{path} は配列で書いてください")
    cleaned = []
    for i, item in enumerate(data):
        if not item.get("name"):
            raise SystemExit(f"{path} の {i} 番目に name がありません")
        pattern = item.get("pattern", "")
        if pattern:
            try:
                re.compile(pattern)
            except re.error as e:
                raise SystemExit(f"{path} の「{item['name']}」の pattern が不正です: {e}")
        cleaned.append({
            "name": item["name"],
            "pattern": pattern,
            "scope": item.get("scope", "both"),
            "ids": item.get("ids", []),
        })
    return cleaned


def build_awoken_sheet(src):
    """覚醒アイコンを縦1列に切り出し、減色して data URI にする。

    元画像は 96x4608 の3列構成で、覚醒ID N は N 行目にある（1列目のみ使う）。
    そのまま埋めると 261KB あるが、256色に落とすと 53KB まで縮む。
    """
    from PIL import Image
    im = Image.open(src).convert("RGBA")
    cell = im.width // 3
    col = im.crop((0, 0, cell, im.height))
    col = col.quantize(colors=256, method=Image.FASTOCTREE)
    buf = io.BytesIO()
    col.save(buf, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def main():
    gz = Path(sys.argv[1] if len(sys.argv) > 1 else "out2/archive.json.gz")
    out = Path(sys.argv[2] if len(sys.argv) > 2 else "out2/pad_skill_archive.html")
    mycats_path = Path(sys.argv[3] if len(sys.argv) > 3 else "mycategories.json")

    mycats = load_mycategories(mycats_path)
    if mycats:
        print(f"マイカテゴリ既定値: {len(mycats)} 件 ({mycats_path})")

    sheet_path = Path(sys.argv[4]) if len(sys.argv) > 4 else Path("awoken.png")
    if not sheet_path.exists():
        print(f"  取得中: awoken.png（{sheet_path} が無いのでGitHubから）")
        with urllib.request.urlopen(AWOKEN_URL, timeout=180) as r:
            sheet_path = io.BytesIO(r.read())
    sheet = build_awoken_sheet(sheet_path)
    print(f"覚醒アイコン: {len(sheet)/1024:.0f} KB (data URI)")

    html = (TEMPLATE
            .replace("__AWOKEN__", sheet)
            .replace("__MYCATS__", json.dumps(mycats, ensure_ascii=False))
            .replace("__DATA__", base64.b64encode(gz.read_bytes()).decode("ascii")))
    out.write_text(html, encoding="utf-8")
    print(f"HTML 出力: {out} ({out.stat().st_size/1024/1024:.2f} MB)")


if __name__ == "__main__":
    main()
