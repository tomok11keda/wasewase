# 公式授業登録 E2E 検証レポート（ローカル隔離）

最終更新: 2026-11-21（America/Chicago）

本ドキュメントは PR #4（`cursor/course-master-pilot-e87e`）上でのローカル検証結果です。  
本番 DB / Render / 公式 PDF 由来データの public 切替は実施していません。

## 1. 検証環境

| 項目 | 内容 |
|------|------|
| Worktree | `.worktrees/course-master-pilot` |
| Branch | `cursor/course-master-pilot-e87e` |
| DB | ローカル SQLite のみ |
| Feature Flag | `WASE_OFFICIAL_CLASS_STUDENT_UI`（プロセス環境変数） |
| React SPA | `WASE_REACT_SPA=1`（ローカル UI 検証時） |
| Pilot schools | `商学部` |
| 架空データ | `section=E2E_FICTIONAL` / `parse_flags=e2e_fictional_local_only` |
| Seed | `python manage.py seed_official_e2e_fixtures --ensure-user` |
| Cleanup | `python manage.py seed_official_e2e_fixtures --cleanup`（検証後実行済み） |

架空クラス（実在の早稲田授業データではない / 現学期に合わせて seed）:

1. 架空・基礎データ分析（canonical あり / ready）
2. 架空・組織行動入門（canonical なし / pending）
3. 架空・マーケティング演習（複数リンク / conflict）
4. 架空・ビジネス倫理（canonical あり）
5. 架空・財務会計概論（canonical あり / 曜日時限衝突用）

## 2. API・統合テスト結果

```bash
WASE_OFFICIAL_CLASS_STUDENT_UI=1 \
  python3 manage.py test app.test_official_course_e2e app.test_official_course_student_api -v 1
# → 22 tests OK
```

| シナリオ | 結果 | 備考 |
|----------|------|------|
| 架空 public のみ検索 | ✅ | research_only は非表示 |
| canonical あり → 履修 + 時間割 | ✅ | CourseEnrollment + TimetableSlot |
| 授業トーク接続 | ✅ | `/api/v1/courses/offerings/<id>/talk/` |
| pending_canonical | ✅ | 409 + 日本語 `message` |
| 複数リンク conflict | ✅ | 409 + 日本語 `message` |
| 既存履修の再登録 | ✅ | enrollment 1 件のまま idempotent |
| 曜日時限衝突（自由入力） | ✅ | 409 `slot_conflict` + 自由入力保持 |
| Feature Flag OFF | ✅ | official API 404 / community・自由入力 create OK |
| エラー文言（API） | ✅ | `message` フィールドに日本語 |

ローカル runserver 上の Cookie セッションでも同等の enroll / talk / conflict を確認。

## 3. ブラウザ / モバイル画面検証

手段: Playwright headless（390×844）+ `frontend/scripts/verify_official_course_e2e.mjs`  
（computerUse によるクリック操作は SPA 無効時・空セルクリックで一部ブロックされたため、最終証跡は Playwright）

| 項目 | 状態 |
|------|------|
| Flag ON: タブ「みんなの授業」「公式から選ぶ」 | ✅ |
| 「架空」検索で 5 件表示（pending/conflict ラベル含む） | ✅ |
| pending タップ → 日本語 alert（準備中） | ✅ |
| ready（ビジネス倫理）登録 → toast「公式授業を追加しました」 | ✅ |
| 「みんなの授業」タブ切替 | ✅ |
| Flag OFF: 公式タブ非表示 / community 検索 +「新しい授業を追加」 | ✅ |
| モバイル幅でのシート表示 | ✅ |

発見した検証上の注意:

- UI 検索は `CourseMeta.semester` / `academic_year` で絞り込む。seed も現学期に合わせないと「該当なし」になる（今回は seed を `current_semester()` 連動に修正）。

## 4. 成功した操作 / 失敗した操作

### 成功

- 架空 OfficialClass の seed / cleanup
- public 検索、canonical 履修、授業トーク join
- pending / conflict / slot_conflict / existing enrollment
- Flag OFF 回帰（API + モバイル UI）
- API/UI の日本語エラー（`slot_conflict` code 分割 + フロント `message` 優先）
- Playwright モバイル UI 一連（検索→pending alert→enroll toast）

### 失敗 / 制限

- computerUse での空セル直接クリックは応答せず（`＋ 授業を追加` / Playwright では成功）
- 人手の実機タッチ検証は未実施（自動化ブラウザで代替）

## 5. UI 上の問題

- **修正済み**: `slot_conflict:<title>` が error code のまま返り、フロントが日本語 `message` を上書きしていた → API で code 分割、フロントで `code` と `message` を分離。
- **運用注意**: 公式検索が現学期フィルタのため、学期外の public 行は学生 UI に出ない（意図どおりだが、パイロット投入時は学期整合が必須）。
- pending / conflict はリスト上「準備中」表示 + タップで日本語 alert。文言は理解可能。

## 6. 本番公開までのブロッカー

1. **canonical 未設定のまま public にすると履修できない**（auto-create / auto-merge なし）
2. **Feature Flag はデフォルト OFF** — ON 前に pilot 学部・canonical 充足率・監視が必要
3. **公式 PDF 由来行は research_only のまま**（本検証でも public 切替禁止を遵守）
4. **conflict（複数リンク）解消は管理者の明示 canonical 選択が必要**
5. **stable identity / 時限変更更新**は未実装（提案のみ — 下記）

## 7. canonical 設定の作業量（72件 → 全学）

詳細: [`CANONICAL_SCALE_AND_IDENTITY.md`](./CANONICAL_SCALE_AND_IDENTITY.md)

- 72 件: 手動 canonical で **約 1.5〜3 時間**（半日以内）で現実的
- 全学数千: スコアリング → 一意高信頼のバッチ承認 → 曖昧のみ人手。auto-merge 禁止は維持

## 8. provisional_identity と曜日時限変更

詳細: 同上。

- 現状 identity に meeting fingerprint が含まれる → 時限変更で別 OfficialClass 生成リスク
- 推奨: meeting を除いた `stable_key` で同一クラスを更新し、meeting は子テーブル soft-update。canonical / リンクは維持

## 9. 成果物（コード）

- `app/management/commands/seed_official_e2e_fixtures.py`
- `app/test_official_course_e2e.py`
- `frontend/scripts/verify_official_course_e2e.mjs`
- エラー文言修正: `official_course_api_views.py` / `api.ts` / `CourseAddSheet.tsx`
