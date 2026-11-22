# Option B 設計：OfficialClass と CourseOffering の安全な対応

本番公開前の設計メモ。既存 Offering / 授業トークの自動マージは禁止。

## 1. 暫定識別（公式キー未取得時）

**禁止:** `subject_key` / `syllabus_class_code` を推測で埋める。

**採用:** `provisional_identity = "haibun:v1:" + sha256(...)[:20]`

入力フィールド（配当表のみ）:

- `academic_year`, `school`, `semester_code`
- `title`, `haibun_class_no`, `instructor`
- 正規化ミーティング指紋（例: `p4-d1`, `od`）

性質:

- 決定的・再実行可能
- 公式シラバスIDの代替ではない（フィールド名・ヘルプで明示）
- 後から公式キーが取れたら `subject_key` + `syllabus_class_code` を埋め、ユニーク制約で正式一意化。`provisional_identity` は履歴キーとして残す

## 2. モデル対応関係

```
OfficialClass 1 ─── * OfficialMeeting
OfficialClass 1 ─── * OfferingOfficialLink * ─── 1 CourseOffering
OfficialClass 0..1 ── canonical_offering → CourseOffering
```

- 1 Offering は最大1 OfficialClass（OneToOne）
- 1 OfficialClass は複数 Offering をリンクしうる（既存ユーザー作成分の併存）
- `canonical_offering` は新規履修・共通トークの受け皿。人手または「公式から作成」時のみ設定
- `CourseOffering.source` に `official` を追加（新規作成分の出所表示）

## 3. 同一 OfficialClass に複数 Offering がある場合

| 状況 | 取り扱い |
|------|----------|
| リンク0件 | 新規選択時のみ `create_offering_from_official`（canonical 設定） |
| リンク1件 | その Offering を履修先に使用。任意で canonical 化 |
| リンク2件以上 | **自動マージしない**。`canonical_offering` 未設定なら `MultipleOfferingsForOfficial` |
| 既存履修・トーク・口コミ | 各 Offering に残置。削除・移動しない |
| 管理画面 | 候補一覧 + 履修数を見せ、canonical を人手選択。任意の後日マージは別オペ |

`official_link_conflict_summary()` が `needs_manual_canonical` / `auto_merge_allowed=False` を返す。

## 4. 新規ユーザーが公式授業を選んだとき

1. UI は `OfficialClass`（`publication_status=public` のみ）を検索
2. `resolve_enrollment_offering(official, create_if_missing=True)`
   - canonical があればそれを使う
   - なければ単一リンク、なければ新規 Offering 作成 + link + canonical
   - 複数リンクで canonical なし → エラー（パイロットでは「選択できない」UI）
3. 既存の `enroll_user_in_offering` で履修・時間割・授業トークへ参加
4. 研究CSV（`research_only`）は学生UIに出さない

## 5. 既存ユーザーの段階移行

原則: **削除しない・自動統合しない・既存トークを壊さない**。

フェーズ:

1. **並列導入** — OfficialClass を import。Offering は無変更
2. **候補リンク** — タイトル+年度+学期+教員のヒューリスティックで `match_method=suggested`（自動確定しない）
3. **人手確認** — 管理者が link / canonical を確定
4. **新フロー優先** — 新規登録は公式選択のみ（フラグ）。既存履修は現状維持
5. **任意オプトイン** — 「同じ公式クラスの共通ルームへ移る」をユーザー操作で。未操作のトークは残す
6. **公式キー付与後** — provisional → syllabus identity の照合更新。Offering は触らない

口コミ (`CourseReview`) は Offering 紐づきのまま。canonical 統合時もレビュー移行は別設計・人手バッチ。

## 6. 公開状態ゲート

| status | 用途 |
|--------|------|
| `research_only` | ローカル/検証のみ。学生UI非表示 |
| `internal` | 社内プレビュー |
| `public` | 許諾確認後の学生公開 |

商学部パイロットCSVは当面すべて `research_only`。
