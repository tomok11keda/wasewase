# 学生向け：公式授業の検索・選択登録（最小仕様）

商学部パイロット向け。既存の自由入力登録は残す（フラグで併存）。

## 画面

**「公式から選ぶ」**（時間割追加フロー内のタブ / セカンダリCTA）

1. 検索ボックス（科目名・教員）
2. 任意フィルタ: 学期 / 曜日時限 / オンライン
3. 結果リスト（カードではなく行）: 科目名、教員、学期、曜日時限、休講バッジ
4. 行タップ → 確認シート → 「この授業を時間割に追加」

## データ条件

- `OfficialClass.publication_status == public` のみ
- `is_cancelled == true` は一覧に出さない（または「休講」で選択不可）
- `needs_human_review` は非表示
- `research_only` は絶対に出さない

## 登録時

1. 選択した `official_class_id` を API へ
2. サーバ: `resolve_enrollment_offering` → `enroll_user_in_offering`
3. 成功: 既存時間割画面へ戻り、スロット反映
4. 失敗 `MultipleOfferingsForOfficial`: 「この授業は準備中です」＋報告導線（自動マージしない）

## 出さないもの（v1）

- 公式キー未取得の説明を学生に詳細表示しない（内部のみ）
- 「既存の別ルームと統合」ボタン
- OCR / スクショ登録（次フェーズ）
- 口コミの横断表示変更

## API（実装済み）

```
GET  /api/v1/courses/official/?q=&semester=&year=&day=&period=&school=&limit=&offset=
POST /api/v1/courses/official/<id>/enroll/
```

- 検索は `publication_status=public` のみ（`research_only` は絶対に返さない）
- 履修は canonical Offering 必須。未設定は `409 pending_canonical`
- レスポンスは `offering` + `slot`（既存履修と同形）+ `official_class`

## フラグ

- `WASE_OFFICIAL_CLASS_STUDENT_UI`（既定 `False`）— OFF ならタブ非表示・API 404
- `WASE_OFFICIAL_CLASS_PILOT_SCHOOLS`（既定 `商学部`）
- meta: `official_class_search_enabled` / `official_class_pilot_schools`
