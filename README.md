# パズドラ スキルアーカイブ

モンスター 13,982 体、アクティブスキル 8,774 種、リーダースキル 7,604 種。
スキルから所持キャラ（図鑑番号つき）を、キャラ名からスキルを、どちらからでも引ける。

## 中身

| ファイル | 用途 |
|---|---|
| `pad_skill_archive.html` | 単一HTMLの検索UI。ダブルクリックで開くだけ。オフラインで動く |
| `pad_archive.sqlite` | SQL用。FTS5 trigram つきで日本語の部分一致が効く |
| `build_pad_archive.py` | 元データ取得 → SQLite / 圧縮JSON |
| `build_archive_html.py` | 圧縮JSON → 単一HTML |
| `update-archive.yml` | 週次で最新に追従する GitHub Actions ワークフロー |
| `mycategories.json` | マイカテゴリの初期値。ビルド時にHTMLへ焼き込まれる |
| `awakening_names.json` | 覚醒ID → 日本語名。136種すべて入力済み |
| `awoken.png` | 覚醒アイコンのスプライト。無ければビルド時にGitHubから取得する |

## データの素性

出典は [Mapaler/PADDashFormation](https://github.com/Mapaler/PADDashFormation) の
`monsters-info/`（`mon_ja.json` と `skill_ja.json`）。**日次で更新されている**。

前回調べた DadGuide 系（2023年4月で凍結）とは別系統で、こちらは現行データ。
日本語のスキル名・説明文がそのまま入っているうえ、初期の溜まりターンも取れる。

```bash
python build_pad_archive.py --remote out
python build_archive_html.py out/archive.json.gz out/pad_skill_archive.html
```

引数なしでGitHubから直接取ってくるので、リポジトリ全体（2.2GB ある）を
clone する必要はない。取得するのは JSON 2本で約26MB。

`update-archive.yml` を `.github/workflows/` に置けば毎週月曜の朝に自動で回る。

## アクティブとリーダーは完全に別物

図鑑データ上、アクティブスキルIDとリーダースキルIDの集合は**重複がゼロ**だった
（8,774 と 7,604 で共通ID なし）。なので推測ではなく、データそのものに沿って
タブで分けている。タブごとに検索語・属性・カテゴリを別々に保持する。

## 画面の構成

ページ全体が下方向にスクロールする。**固定されるのはタブと検索欄だけ**（約120px）で、
属性・並び順・カテゴリの各行は結果と一緒に流れていく。
スクロールすると画面の 86% が結果に使える。

出典や注意書きは常設せず、右上の「この表の見かた」に畳んである。

## 検索のしかた

- **スキル文** … ゲーム内表記は `[火]` のように角括弧つきだが、括弧を外して入力しても当たるようにしてある。`ロックを解除` でも `[ロック]を解除` でも 3,003 件
- **キャラ名** … `ツバキ` で、そのキャラたちが持つスキルに絞れる
- **数字だけ** … 図鑑番号かスキルIDの完全一致。`3000` で No.3000 の持つスキルが出る
- `/` キーで検索欄にフォーカス

絞り込みはタブごとに別。アクティブ側は**初期CD の上限**、リーダー側は**攻撃倍率の下限**。

## 並び順

既定は**新しいキャラ順**。1つのスキルを複数キャラが持つので、
**所持キャラのうち最大の図鑑番号**を基準に降順にしている。

| 選択肢 | 基準 |
|---|---|
| 新しいキャラ順 | 所持キャラの最大図鑑番号の降順（既定） |
| 古いキャラ順 | 所持キャラの最小図鑑番号の昇順 |
| 所持キャラ数 | 持っているキャラが多い順 |
| スキルID順 | スキルIDの昇順 |

所持キャラのチップは先頭8体までしか出さないので、並び順の基準になったキャラが
隠れないようチップの向きも並び順に合わせてある。並び順もタブごとに独立。

## 覚醒タブ

3つ目のタブ。ここだけ行が**スキルではなくモンスター**になる。

- 覚醒チップを押すと、その覚醒を持つキャラに絞れる。複数選ぶと AND
- 属性オーブも併用できる。覚醒タブでは推定ではなく**図鑑の属性そのもの**で絞られる
- キャラ名か図鑑番号で検索できる
- 超覚醒は「超」の仕切りの右側に分けて表示

覚醒 136 種、キャラとの紐付けは 106,776 レコード。

### 覚醒名について

ID 1〜106 は TsubakiBotPad/pad-data-pipeline の
`etl/pad/storage_processor/awoken_skill.json` 由来。
2023年以降に追加された 107〜143 の 37 種はそこに無かったので手入力で補ってある。
136 種すべてに名前が入っている状態。

アイコンは現行データ（Mapaler/PADDashFormation の `images/awoken.png`）から
IDで引いている。名前を直したい場合は `awakening_names.json` の `name` を書き換える。
`count` は所持キャラ数の参考値で、ビルドでは `id` と `name` しか読まない。

```json
{"id": 111, "name": "超コンボ強化＋", "count": 1648}
```

## アシストで絞り込む

覚醒アシストを持つキャラはアシスト運用されるので、
アクティブ／リーダーの両タブに **指定なし / アシストのみ / アシスト以外** の3択を置いた。

- 判定は「そのスキルを持つキャラの中に覚醒アシスト持ちが1体でもいるか」
- 所持キャラのチップにも `アシスト` の印がつく
- アクティブ 8,774 件のうち アシストのみ 3,746 / アシスト以外 5,028

覚醒アシストのIDは直書きせず `awakening_names.json` で `名前 == "覚醒アシスト"` の
エントリから引いている。名前表を差し替えても追随する。

## マイカテゴリ

自動分類とは別枠で、自分でカテゴリを足したり消したりできる。UIの黄色い帯がそれ。

- **＋ 追加** … 名前とキーワードを入れると新しいカテゴリになる。キーワードは正規表現も書ける（`変身|転生` のように）。入力中に該当件数が出るので、当たり具合を見ながら決められる
- **対象** … 両方のタブ／アクティブのみ／リーダーのみ を選べる。選んだタブにしかチップは出ない
- **削除** … チップ右の `×`
- **絞り込み** … チップを押すと自動カテゴリと同じく AND で効く
- **手動で入れる** … キーワードで表せないものは、各行の「＋ マイ」から個別に放り込める。入れた件数は `★ N` で出る

キーワードにマッチしたスキルと、手動で入れたスキルの **和集合** がそのカテゴリの中身になる。

### 保存のされ方

ブラウザの localStorage に入る。同じ端末で同じ場所のファイルを開く限りは残るし、
ビルドし直しても消えない。ただし別の端末には引き継がれない。

引き継ぎたいときは「JSON」ボタンで中身を出して、`mycategories.json` に貼る。
次のビルドから初期値として焼き込まれるので、GitHub Actions で回している場合も維持される。

```bash
python build_archive_html.py out/archive.json.gz out/pad_skill_archive.html mycategories.json
```

`mycategories.json` の形式:

```json
[
  {"name": "変身", "pattern": "変身", "scope": "active", "ids": []},
  {"name": "無効貫通", "pattern": "ダメージ無効を貫通", "scope": "both", "ids": []},
  {"name": "7×6マス", "pattern": "7[×x]6", "scope": "both", "ids": []}
]
```

`scope` は `both` / `active` / `leader`、`ids` は手動で入れたスキルID。
ビルド時に name の有無と pattern の正規表現としての妥当性を検査する。

## 目安として使う項目

- **属性オーブ** … スキル文中の属性語からの推定。厳密な属性判定ではない
- **カテゴリ** … 説明文の正規表現マッチによる自動分類。`build_pad_archive.py` の
  `ACTIVE_RULES` / `LEADER_RULES` を書き換えれば自分好みに調整できる
- **説明文** … 元データには `^ff3600^`（色指定）`^qs^`（装飾開始）`^p`（解除）という
  装飾コードが 1,461 件混ざっているので、ETL 側で除去している
- **最大 ×N** … 説明文の「攻撃力がN倍」から拾った最大値。複合条件のリーダースキルでは
  実際に出せる倍率とは一致しない

**所持キャラと図鑑番号は図鑑データそのもの**なので、ここだけは推定ではない。
同じ内容は画面右上の「この表の見かた」からも読める。

## SQL で引く

```sql
-- あるスキルを持つキャラを図鑑番号つきで
SELECT m.monster_id, m.name, m.attrs
FROM skill_holders h JOIN monsters m ON m.monster_id = h.monster_id
WHERE h.kind='active' AND h.skill_id = 2637
ORDER BY m.monster_id;

-- キャラ名からスキルを逆引き
SELECT m.monster_id, m.name, s.kind, s.name, s.description
FROM monsters m
JOIN skill_holders h ON h.monster_id = m.monster_id
JOIN skills s ON s.rowid = h.rowid
WHERE m.name LIKE '%ヤマトタケル%';

-- 初期CD5以下でロック解除できるアクティブ
SELECT s.skill_id, s.name, s.cooldown, s.description
FROM skills s JOIN skill_categories c ON c.rowid = s.rowid
WHERE s.kind='active' AND s.cooldown <= 5 AND c.category = 'ロック解除'
ORDER BY s.cooldown;

-- 全文検索（trigram なので部分一致が効く）
SELECT s.skill_id, s.name, s.description
FROM skills_fts f JOIN skills s ON s.rowid = f.rowid
WHERE skills_fts MATCH '無効貫通';

-- 所持キャラが多い順
SELECT skill_id, name, holder_count FROM skills
WHERE kind='active' ORDER BY holder_count DESC LIMIT 20;

-- アシスト運用されるキャラが持つアクティブスキル
SELECT DISTINCT s.skill_id, s.name, s.description
FROM skills s JOIN skill_holders h ON h.rowid = s.rowid
JOIN monsters m ON m.monster_id = h.monster_id
WHERE s.kind = 'active' AND m.is_assist = 1
ORDER BY s.skill_id DESC LIMIT 20;

-- ある覚醒を持つキャラ
SELECT m.monster_id, m.name FROM monster_awakenings ma
JOIN monsters m ON m.monster_id = ma.monster_id
JOIN awakenings a ON a.awakening_id = ma.awakening_id
WHERE a.name = '封印耐性' ORDER BY m.monster_id DESC LIMIT 20;

-- 覚醒の組み合わせで絞る（両方持つキャラ）
SELECT count(*) FROM (
  SELECT monster_id FROM monster_awakenings
  WHERE awakening_id IN (SELECT awakening_id FROM awakenings
                         WHERE name IN ('封印耐性','操作時間延長+'))
  GROUP BY monster_id HAVING count(DISTINCT awakening_id) = 2);

-- 新しいキャラ順（UIの既定と同じ並び）
SELECT s.skill_id, s.name, s.newest_monster_id, m.name
FROM skills s JOIN monsters m ON m.monster_id = s.newest_monster_id
WHERE s.kind='active' ORDER BY s.newest_monster_id DESC LIMIT 20;
```

## 入っていないもの

- 敵スキル・ダンジョン行動パターン
- 進化ツリーの構造（`evoBaseId` / `evoRootId` は元データにあるので追加は可能）
