#!/usr/bin/env python3
"""
パズドラ スキルアーカイブ ビルダー（現行データ版）

データ元: Mapaler/PADDashFormation の monsters-info/
  - mon_ja.json   … モンスター図鑑（日本語名・属性・タイプ・スキルID）
  - skill_ja.json … スキル定義（日本語名・説明文・溜まりターン）
このリポジトリは日次で更新されているので、再実行すれば最新に追従できる。

出力:
  pad_archive.sqlite … SQL用（FTS5 trigram つき）
  archive.json.gz    … 単一HTML埋め込み用

使い方:
  python build_pad_archive.py                     # GitHubから取得
  python build_pad_archive.py --remote out        # 取得先を明示して出力先指定
  python build_pad_archive.py <monsters-infoのパス> out
"""

import gzip
import json
import re
import sqlite3
import sys
import urllib.request
from pathlib import Path

RAW_BASE = ("https://raw.githubusercontent.com/Mapaler/PADDashFormation"
            "/master/monsters-info/")

# 覚醒アシストを持つキャラはアシスト専用として使われるので、絞り込みに使えるよう印をつける。
# IDを直書きせず名前から引くことで、名前表を差し替えたときも追随する。
ASSIST_AWAKENING_NAME = "覚醒アシスト"

# 覚醒の並び順。出現頻度順だと関連するものが散らばるので、名前で束ねる。
# 上から順に当てはめ、最初に当たったグループに入れる（順序が意味を持つ）。
# 「＋」つきは基本形と隣り合わせたいので、判定は末尾の＋を外した名前で行う。
AWAKENING_GROUPS = [
    ("キラー",         r"キラー$"),
    ("操作時間",       r"操作時間"),
    ("耐性",           r"耐性"),
    ("スキル・アシスト", r"^スキルブースト|^スキルチャージ|^スキルボイス"
                        r"|覚醒アシスト|マルチブースト|ダンジョンボーナス"),
    ("ドロップ強化",   r"ドロップ強化"),
    ("属性強化",       r"^(火|水|木|光|闇)属性強化"),
    ("コンボ",         r"コンボ強化|コンボドロップ"),
    ("消し方",         r"消し|2体攻撃"),
    ("多色",           r"色攻撃強化|同時攻撃$|多色"),
    ("貫通・追撃",     r"無効貫通|ガードブレイク|追加攻撃|部位破壊"),
    ("タイプ・副属性", r"タイプ追加|副属性変更"),
    # 回復と軽減はどちらも耐久側なのでひとまとめ。
    # ドロップ系の加護は状態異常への備えなのでこちらに残す。
    ("回復・軽減",     r"回復$|ダメージ軽減$"
                      r"|^お邪魔ドロップの加護$|^毒ドロップの加護$"),
    # 単体で立たない常時効果はステータス強化に寄せる。
    ("ステータス強化", r"強化$|弱化$|アシスト共鳴"
                      r"|^浮遊$|^陽の加護$|^陰の加護$|^熟成$"
                      r"|^アフタヌーンティー$|^自力$|^加速$"),
    ("その他",         r""),
]

# 属性コード。mon_ja.json の attrs / 既知モンスターで検証済み
ATTR_NAMES = {0: "火", 1: "水", 2: "木", 3: "光", 4: "闇"}
ATTR_KEYS = {0: "fire", 1: "water", 2: "wood", 3: "light", 4: "dark"}

TYPE_NAMES = {
    0: "進化用", 1: "バランス", 2: "体力", 3: "回復", 4: "ドラゴン",
    5: "神", 6: "攻撃", 7: "悪魔", 8: "マシン",
    12: "覚醒用", 14: "強化合成用", 15: "売却用",
}

# スキル説明文から日本語カテゴリを起こす。英語タグより検索語に近い。
ACTIVE_RULES = [
    ("ロック解除",       r"ロック.{0,4}解除"),
    ("ドロップ生成",     r"生成"),
    ("ドロップ変化",     r"変化|変換"),
    ("全ドロップ変化",   r"全ドロップを"),
    ("覚醒無効回復",     r"覚醒無効"),
    ("ダメージ無効貫通", r"ダメージ無効を貫通"),
    ("属性吸収無効",     r"属性吸収"),
    ("ダメージ吸収無効", r"ダメージ吸収"),
    ("バインド回復",     r"バインド"),
    ("攻撃強化",         r"攻撃力が.{0,8}倍"),
    ("固定ダメージ",     r"固定.{0,3}ダメージ"),
    ("敵への攻撃",       r"属性攻撃|ダメージを与え"),
    ("操作時間延長",     r"操作時間"),
    ("HP回復",           r"HPを?.{0,6}回復|回復力"),
    ("落ちコンなし",     r"落ちコン"),
    ("盤面拡張",         r"7[×x]6|盤面"),
    ("ヘイスト",         r"スキルが?\d*ターン.{0,4}溜ま"),
    ("コンボ加算",       r"コンボ加算|コンボ数を"),
    ("ダメージ軽減",     r"ダメージを.{0,8}(減少|激減|半減)"),
    ("状態異常付与",     r"毒|お邪魔|爆弾"),
    ("エンハンス",       r"ドロップを強化|強化ドロップ"),
    ("チェンジザワールド", r"時を止め|操作時間.{0,6}固定"),
    ("目覚め条件",       r"目覚め"),
]

LEADER_RULES = [
    ("攻撃倍率",         r"攻撃力が.{0,8}倍"),
    ("HP倍率",           r"HPが.{0,8}倍"),
    ("回復倍率",         r"回復力が.{0,8}倍"),
    ("ダメージ軽減",     r"ダメージを.{0,8}(減少|激減|半減)"),
    ("コンボ加算",       r"コンボ加算"),
    ("追加攻撃",         r"追い打ち|追加攻撃"),
    ("落ちコンなし",     r"落ちコンなし"),
    ("盤面拡張",         r"7[×x]6|盤面"),
    ("操作時間固定",     r"操作時間.{0,6}固定"),
    ("操作時間延長",     r"操作時間が"),
    ("多色条件",         r"同時攻撃|色以上"),
    ("コンボ条件",       r"\d+コンボ以上"),
    ("HP条件",           r"HPが\d+%"),
    ("十字消し",         r"十字消し"),
    ("L字消し",          r"L字"),
    ("タイプ強化",       r"タイプの"),
    ("属性強化",         r"属性の"),
    ("無効貫通",         r"ダメージ無効を貫通"),
    ("固定ダメージ",     r"固定.{0,3}ダメージ"),
    ("回復ドロップ",     r"回復ドロップ"),
]

# 「攻撃力が8倍」から倍率を拾う。複合表記があるので最大値を代表値にする。
MULT_RE = re.compile(r"攻撃力が([\d.]+)倍")

# ゲーム内テキストの装飾コード。^RRGGBB^ が色指定、^qs^ が装飾開始、^p が解除。
# 1,461 件の説明文に混ざっており、この3つで完全に除去できることを確認済み。
CONTROL_CODES = [
    re.compile(r"\^[0-9a-fA-F]{6}\^"),
    re.compile(r"\^qs\^"),
    re.compile(r"\^p"),
]


def strip_control_codes(text):
    for pattern in CONTROL_CODES:
        text = pattern.sub("", text)
    return text


def load_awakening_names(path):
    """覚醒ID -> 日本語名。

    元は TsubakiBotPad/pad-data-pipeline の etl/pad/storage_processor/awoken_skill.json
    （2023年時点でID 1-106）。それ以降に追加されたIDは名前が空のままにしてあるので、
    埋めたい場合はこのファイルを直接編集する。アイコンはIDから引けるので空でも困らない。
    """
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {int(a["id"]): a.get("name", "") for a in data}


def fetch(name, local_dir=None):
    if local_dir:
        return json.loads((Path(local_dir) / name).read_text(encoding="utf-8"))
    print(f"  取得中: {name}")
    with urllib.request.urlopen(RAW_BASE + name, timeout=180) as r:
        return json.loads(r.read().decode("utf-8"))


def categorize(text, rules):
    return [label for label, pattern in rules if re.search(pattern, text)]


def detect_attrs(text):
    """説明文に出てくる属性語を拾う。絞り込みの目安として使う推定値。"""
    found = []
    for code, name in ATTR_NAMES.items():
        if name in text:
            found.append(ATTR_KEYS[code])
    if "回復" in text:
        found.append("heal")
    return found


def max_multiplier(text):
    vals = [float(v) for v in MULT_RE.findall(text)]
    return max(vals) if vals else 0.0


def build(monsters_raw, skills_raw):
    skills_by_id = {s["id"]: s for s in skills_raw if isinstance(s, dict)}

    monsters = [m for m in monsters_raw
                if not m.get("isEmpty") and m.get("enabled", True)]

    # スキルID -> それを持つモンスター図鑑番号。アクティブとリーダーで別集計。
    holders = {"active": {}, "leader": {}}
    mon_index = {}

    for m in monsters:
        mid = m["id"]
        mon_index[mid] = {
            "id": mid,
            "name": m.get("name", ""),
            "attrs": [a for a in m.get("attrs", []) if a in ATTR_NAMES],
            "types": [t for t in m.get("types", []) if t in TYPE_NAMES],
            "rarity": m.get("rarity", 0),
        }
        for kind, key in (("active", "activeSkillId"), ("leader", "leaderSkillId")):
            sid = m.get(key)
            if sid:
                holders[kind].setdefault(sid, []).append(mid)

    # 覚醒は図鑑データ側の属性なので、モンスターごとにそのまま持たせる
    for m in monsters:
        mi = mon_index[m["id"]]
        mi["awakenings"] = [a for a in (m.get("awakenings") or []) if a]
        mi["super"] = [a for a in (m.get("superAwakenings") or []) if a]

    rows = []
    for kind, rules in (("active", ACTIVE_RULES), ("leader", LEADER_RULES)):
        for sid, mids in holders[kind].items():
            s = skills_by_id.get(sid)
            if not s:
                continue
            desc = strip_control_codes((s.get("description") or "").replace("\r", ""))
            # 図鑑番号順にすると進化ツリーが並ぶので読みやすい
            mids = sorted(set(mids))
            # スキルレベルが1上がるごとに1ターン短くなる。maxLevel が
            # レベルの総数なので、短縮できるのは maxLevel-1 ターン。
            # 対象8,774件で最短が1未満になるものが無いことを確認済み。
            maxlv = s.get("maxLevel", 0) or 0
            cd = s.get("initialCooldown", 0) or 0
            cd_min = cd - (maxlv - 1) if maxlv >= 1 else cd

            rows.append({
                "kind": kind,
                "id": sid,
                "name": s.get("name", "") or "",
                "desc": desc,
                "cooldown": cd,
                "cooldown_min": max(cd_min, 0),
                "maxlv": maxlv,
                "cats": categorize(desc, rules),
                "attrs": detect_attrs(desc),
                "mult": max_multiplier(desc) if kind == "leader" else 0.0,
                "mons": mids,
            })

    # 新しいキャラが持つスキルほど前に来るようにする
    rows.sort(key=lambda r: (r["kind"], -r["mons"][-1]))
    return rows, mon_index


def base_name(name):
    """末尾の ＋ / + を外した名前。X と X＋ を並べるための並び替えキー。"""
    return re.sub(r"[＋+]+$", "", name)


def group_awakenings(aw_names, aw_count):
    """覚醒を名前で束ねて、グループの順・基本名・IDの順に並べる。"""
    buckets = {label: [] for label, _ in AWAKENING_GROUPS}
    for aid, name in aw_names.items():
        base = base_name(name)
        for label, pattern in AWAKENING_GROUPS:
            if not pattern or re.search(pattern, base):
                buckets[label].append((base, aid, name))
                break

    # グループ内はゲーム側のID順に近づけたい。ただし X と X＋ は隣り合わせたいので、
    # 「基本名が最初に現れたID」を第一キー、実IDを第二キーにする。
    base_first = {}
    for base, aid, _ in [x for v in buckets.values() for x in v]:
        if base not in base_first or aid < base_first[base]:
            base_first[base] = aid

    out = []
    for label, _ in AWAKENING_GROUPS:
        items = sorted(buckets[label], key=lambda x: (base_first[x[0]], x[1]))
        if items:
            out.append([label, [aid for _, aid, _ in items]])
    return out


def find_assist_awakening_id(aw_names):
    for aid, name in aw_names.items():
        if name == ASSIST_AWAKENING_NAME:
            return aid
    print(f"  注意: 「{ASSIST_AWAKENING_NAME}」が名前表に無いのでアシスト判定は無効になります")
    return None


def build_sqlite(rows, mons, aw_names, out_path):
    if out_path.exists():
        out_path.unlink()
    conn = sqlite3.connect(out_path)
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE monsters (
            monster_id INTEGER PRIMARY KEY,   -- 図鑑番号
            name TEXT, attrs TEXT, types TEXT, rarity INTEGER,
            awakening_count INTEGER,
            is_assist INTEGER                 -- 覚醒アシスト持ち
        );
        CREATE TABLE awakenings (
            awakening_id INTEGER PRIMARY KEY,
            name TEXT,                        -- 空なら名前が判明していないもの
            holder_count INTEGER
        );
        CREATE TABLE monster_awakenings (
            monster_id INTEGER NOT NULL,
            awakening_id INTEGER NOT NULL,
            slot INTEGER NOT NULL,            -- 覚醒の並び順
            is_super INTEGER NOT NULL         -- 1なら超覚醒
        );
        CREATE INDEX idx_ma_mon ON monster_awakenings(monster_id);
        CREATE INDEX idx_ma_aw  ON monster_awakenings(awakening_id);
        CREATE TABLE skills (
            rowid INTEGER PRIMARY KEY,
            kind TEXT NOT NULL,               -- 'active' | 'leader'
            skill_id INTEGER NOT NULL,
            name TEXT,
            description TEXT,
            cooldown INTEGER,                 -- スキルレベル1での溜まりターン
            cooldown_min INTEGER,             -- 最大レベルでの溜まりターン
            max_level INTEGER,
            attrs TEXT,
            multiplier REAL,                  -- 説明文から拾った最大攻撃倍率
            holder_count INTEGER,
            newest_monster_id INTEGER,        -- 所持キャラのうち最大の図鑑番号
            oldest_monster_id INTEGER         -- 同じく最小
        );
        CREATE TABLE skill_categories (rowid INTEGER, category TEXT);
        CREATE TABLE skill_holders (
            rowid INTEGER, kind TEXT, skill_id INTEGER, monster_id INTEGER
        );
        CREATE INDEX idx_sk_kind ON skills(kind);
        CREATE INDEX idx_sk_id ON skills(skill_id);
        CREATE INDEX idx_cat ON skill_categories(category);
        CREATE INDEX idx_hold_mon ON skill_holders(monster_id);
        CREATE INDEX idx_hold_row ON skill_holders(rowid);
        CREATE INDEX idx_sk_newest ON skills(newest_monster_id DESC);
    """)

    assist_id = find_assist_awakening_id(aw_names)
    cur.executemany(
        "INSERT INTO monsters VALUES (?,?,?,?,?,?,?)",
        [(m["id"], m["name"],
          ",".join(ATTR_NAMES[a] for a in m["attrs"]),
          ",".join(TYPE_NAMES[t] for t in m["types"]),
          m["rarity"], len(m.get("awakenings", [])),
          1 if assist_id and assist_id in
               (set(m.get("awakenings", [])) | set(m.get("super", []))) else 0)
         for m in mons.values()])

    ma_rows, aw_count = [], {}
    for m in mons.values():
        for slot, aid in enumerate(m.get("awakenings", [])):
            ma_rows.append((m["id"], aid, slot, 0))
        for slot, aid in enumerate(m.get("super", [])):
            ma_rows.append((m["id"], aid, slot, 1))
        # 同じ覚醒を複数積んでいても1体として数える（画面側の表示と揃える）
        for aid in set(m.get("awakenings", [])) | set(m.get("super", [])):
            aw_count[aid] = aw_count.get(aid, 0) + 1
    cur.executemany("INSERT INTO monster_awakenings VALUES (?,?,?,?)", ma_rows)
    cur.executemany("INSERT INTO awakenings VALUES (?,?,?)",
                    [(aid, aw_names.get(aid, ""), n) for aid, n in sorted(aw_count.items())])

    try:
        cur.execute("CREATE VIRTUAL TABLE skills_fts USING fts5("
                    "description, name, content='', tokenize='trigram')")
        fts = True
    except sqlite3.OperationalError:
        fts = False

    for i, r in enumerate(rows, start=1):
        cur.execute("INSERT INTO skills VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (i, r["kind"], r["id"], r["name"], r["desc"], r["cooldown"],
                     r["cooldown_min"], r["maxlv"], ",".join(r["attrs"]), r["mult"],
                     len(r["mons"]), r["mons"][-1], r["mons"][0]))
        cur.executemany("INSERT INTO skill_categories VALUES (?,?)",
                        [(i, c) for c in r["cats"]])
        cur.executemany("INSERT INTO skill_holders VALUES (?,?,?,?)",
                        [(i, r["kind"], r["id"], mid) for mid in r["mons"]])
        if fts:
            cur.execute("INSERT INTO skills_fts (rowid, description, name) VALUES (?,?,?)",
                        (i, r["desc"], r["name"]))

    conn.commit()
    conn.close()
    return fts


def build_json(rows, mons, aw_names, out_path):
    assist_id = find_assist_awakening_id(aw_names)
    assist_ids = sorted(
        m["id"] for m in mons.values()
        if assist_id and assist_id in (set(m.get("awakenings", [])) | set(m.get("super", [])))
    )

    cats = {"active": [], "leader": []}
    for r in rows:
        for c in r["cats"]:
            if c not in cats[r["kind"]]:
                cats[r["kind"]].append(c)
    cats["active"].sort()
    cats["leader"].sort()
    cat_idx = {k: {c: i for i, c in enumerate(v)} for k, v in cats.items()}

    def pack(kind):
        # [8] を足すときは build_archive_html.py 側の実行時追加分（[9]以降）も
        # ずらすこと。添字がずれても例外にならず静かに壊れる。
        return [[r["id"], r["name"], r["desc"], r["cooldown"],
                 [cat_idx[kind][c] for c in r["cats"]],
                 r["attrs"], round(r["mult"], 2), r["mons"], r["cooldown_min"]]
                for r in rows if r["kind"] == kind]

    payload = {
        "cats": cats,
        "active": pack("active"),
        "leader": pack("leader"),
        "mons": {str(m["id"]): [m["name"],
                                [ATTR_KEYS[a] for a in m["attrs"]],
                                m["rarity"]]
                 for m in mons.values()},
        # 覚醒タブ用。行はモンスターそのもの。
        "awoken": [[m["id"], m["name"], [ATTR_KEYS[a] for a in m["attrs"]],
                    m.get("awakenings", []), m.get("super", [])]
                   for m in sorted(mons.values(), key=lambda x: -x["id"])
                   if m.get("awakenings") or m.get("super")],
        "awnames": {str(k): v for k, v in sorted(aw_names.items())},
        # 覚醒アシスト持ちの図鑑番号。スキル側の絞り込みと所持キャラの印に使う。
        "assist": assist_ids,
        # 覚醒の表示順。[[グループ名, [覚醒ID...]], ...]
        "awgroups": group_awakenings(aw_names, None),
    }
    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    # mtime を固定しないと中身が同じでも毎回バイト列が変わり、
    # 定期実行のたびに無意味なコミットが積もる
    out_path.write_bytes(gzip.compress(blob.encode("utf-8"), 9, mtime=0))
    return len(blob.encode("utf-8")), out_path.stat().st_size


def main():
    args = [a for a in sys.argv[1:]]
    if args and args[0] == "--remote":
        args.pop(0)
        local = None
    else:
        local = args.pop(0) if args else None
    out_dir = Path(args[0] if args else "out2")
    out_dir.mkdir(parents=True, exist_ok=True)

    print("データ取得" + (f"（ローカル: {local}）" if local else "（GitHub）"))
    monsters_raw = fetch("mon_ja.json", local)
    skills_raw = fetch("skill_ja.json", local)

    rows, mons = build(monsters_raw, skills_raw)
    n_act = sum(1 for r in rows if r["kind"] == "active")
    n_ldr = len(rows) - n_act
    print(f"モンスター {len(mons):,} 体 / "
          f"アクティブ {n_act:,} 種 / リーダー {n_ldr:,} 種")

    aw_names = load_awakening_names(Path("awakening_names.json"))
    if not aw_names:
        aw_names = load_awakening_names(out_dir / "awakening_names.json")
    named = sum(1 for v in aw_names.values() if v)
    print(f"覚醒 {len(aw_names):,} 種 / 名前あり {named:,} / 名前なし {len(aw_names)-named:,}")
    aid = find_assist_awakening_id(aw_names)
    if aid:
        n = sum(1 for m in mons.values()
                if aid in (set(m.get("awakenings", [])) | set(m.get("super", []))))
        print(f"覚醒アシスト持ち: {n:,} 体（ID {aid}）")

    db = out_dir / "pad_archive.sqlite"
    fts = build_sqlite(rows, mons, aw_names, db)
    print(f"SQLite: {db} ({db.stat().st_size/1024/1024:.1f} MB)"
          f"{' / FTS5 trigram 有効' if fts else ''}")

    js = out_dir / "archive.json.gz"
    raw, gz = build_json(rows, mons, aw_names, js)
    print(f"JSON: {js} ({raw/1024/1024:.2f} MB → gzip {gz/1024/1024:.2f} MB)")


if __name__ == "__main__":
    main()
