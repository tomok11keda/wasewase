# 商学部パイロットを安全に本番導入するまでの残り作業

このブランチで完了したローカル検証の先。**本番DB変更・Renderデプロイはまだ行わない。**

## 完了（本PR / ローカル）

- [x] PR#4 の8件レビュー / 26件除外の妥当性検証
- [x] タイトルガードによるゴミ行除外、72行クリーンCSV
- [x] Option B モデル: `OfficialClass` / `OfficialMeeting` / `OfferingOfficialLink`
- [x] `provisional_identity`（公式キー推測なし）
- [x] CSV dry-run / import、複数リンク時の非マージ解決
- [x] migration `0081_official_course_master` / `0082_official_class_import_history`
- [x] Django Admin（公式クラス・ミーティング・リンク・インポート履歴）
- [x] management command `import_official_classes_csv`（デフォルト dry-run、履歴保存）
- [x] 代表 `canonical_offering` の人手設定 / 未設定時は `pending_canonical`
- [x] 既存時間割・トーク・口コミ非改変テスト
- [x] 単体テスト・UI最小仕様・設計ドキュメント

## 残り作業（優先順）

### A. 法務・データ許諾（ブロッカー）

1. 配当表PDF / カタログ再利用の許諾確認、または大学公式フィード取得
2. 許諾前は `publication_status=research_only` のまま。学生向け公開禁止
3. Webシラバスの `subject_key` 取得は許諾＋レート制限付きでのみ

### B. アプリ実装（非本番）

1. Admin UI から CSV アップロード（現状は management command）
2. 候補リンクの一括 suggested 生成ジョブ（自動確定なし）
3. `GET/POST` 公式検索・履修 API（`STUDENT_UI_MINI_SPEC.md`）
4. 学生UIタブ「公式から選ぶ」＋ feature flag（商学部のみ）
5. Staging での運用手順書（dry-run → レビュー → commit → canonical 設定）

### C. 移行オペレーション

1. Staging のみで migration 適用・CSV import（research_only）
2. 既存 Offering との候補マッチ統計を出し、人手レビュー枠を見積もる
3. 新規ユーザーのみ公式フローを staging で試験
4. 既存ユーザーは据え置き。オプトイン統合は別リリース
5. 本番: migration → research_only import → 許諾後に status を public へ切替（データ再公開ではなくステータス更新）

### D. 品質・拡張

1. ビジネス法入門 #1 の教員欠損を人手補完
2. 経営トラック以外（会計・マーケ等）へセクション拡大（抽出品質ゲート後）
3. 演習表のPDF崩れは別パーサまたは人手CSV
4. 公式キー付与後の provisional → syllabus 照合バッチ

### E. 明示的にやらないこと（当面）

- 本番DBへの OfficialClass 投入
- Render デプロイ
- Offering / 授業トーク / 口コミの自動マージ・削除
- 大学サイトへの大量スクレイピング
- 許諾未確認データの学生向け公開
