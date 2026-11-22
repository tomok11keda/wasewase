# Canonical 運用スケールと provisional_identity 更新方針

PR #4 Option B（OfficialClass ≠ CourseOffering）向けの運用設計メモ。  
auto-merge 禁止・PDF 由来 public 切替禁止を前提とする。

## A. 72 件パイロットの canonical 作業量

### 現状フロー（人手）

1. OfficialClass を public（または internal）にする前に、候補 CourseOffering を確認
2. 一致すれば `set_canonical_offering`（管理画面）
3. 無ければ admin 明示作成 `create_offering_from_official` → canonical 設定
4. 複数リンクなら conflict キューで canonical を1つ選ぶ（他リンクは残す・マージしない）

### 72 件の見積り

| 区分（想定） | 件数感 | 1件あたり | 合計感 |
|--------------|--------|-----------|--------|
| 一意一致（タイトル+教員+学期+スロット） | ~40–50 | 30–60秒（候補確認+承認） | ~30–50分 |
| 候補0（新規 Offering 作成） | ~10–15 | 1–2分 | ~15–30分 |
| 複数候補 / 表記揺れ | ~5–15 | 3–8分（人手判断） | ~30–90分 |
| **合計** | 72 | — | **約 1.5〜3 時間**（レビュー込み半日以内） |

結論: **72 件は現行管理画面の手動 canonical で運用可能**。ボトルネックは全学展開時。

## B. 全学数千クラスへの展開（手作業をボトルネックにしない）

### 原則（変えない）

- 学生 enroll は canonical 必須
- Offering の自動マージ禁止
- research_only → public は人間ゲート

### 推奨パイプライン

```
CSV import (research_only)
  → match scorer（候補提示のみ）
  → 一意高信頼: suggest_canonical キュー（バッチ承認）
  → 曖昧/複数: human review キュー
  → 承認後のみ canonical +（必要なら）public
```

### 具体施策

1. **マッチスコアリング（書き込みなし）**  
   キー: `academic_year + semester + title_normalized + instructor_normalized (+ school) (+ slot)`  
   出力: `unique_high` / `unique_low` / `multi` / `none`。DB 変更はしない。

2. **バッチ承認 UI**  
   `unique_high` のみ「一括で canonical 設定」ボタン。1件ずつ undo 可能。  
   `multi` / `none` は個別レビュー。

3. **新規 Offering のバッチ作成**  
   `none` かつ public 予定の行だけ、admin が明示チェックして `create_offering_from_official` をバッチ実行。  
   CSV import 経路では create_if_missing=False のまま。

4. **conflict は残す**  
   複数コミュニティ Offering が既にある場合、マージせず canonical を1つ選ぶ。他はリンク維持。

5. **メトリクス**  
   - public かつ ready 率  
   - pending / conflict 残件数  
   - 承認リードタイム  
   公開 Flag ON のゲートに使う。

6. **段階公開**  
   pilot school → 学部単位 → 全学。Flag + `WASE_OFFICIAL_CLASS_PILOT_SCHOOLS` で制御済み。

### やってはいけないこと

- 信頼度スコアだけで silent canonical 確定（少なくとも初回全学は人間承認）
- 複数 Offering の自動マージ / 削除
- PDF 由来 research_only の一括 public

## C. provisional_identity が曜日時限変更で変わる問題

### 現状

`build_provisional_identity` は meeting fingerprint を含む。  
配当表で曜日/時限だけ変わると identity が変わり、再 import で **別 OfficialClass が作られる** → 旧行に残った canonical / リンクが孤児化、学生が二重クラスを見るリスク。

### 目標

同一開講クラス（同じ year/school/semester/title/class_no/instructor）は **1 OfficialClass を更新**し、meeting だけ差し替える。canonical と OfferingOfficialLink は維持。

### 推奨モデル（段階導入）

#### Phase 1（短期・破壊的でない）

1. **stable_key** を追加（または identity から meeting を外した `class_key`）:

   ```
   haibun:v2:{year}|{school}|{semester}|{title_norm}|{class_no}|{instructor_norm}
   ```

2. Import 照合順:
   - `subject_key` があれば最優先
   - 次に `stable_key` / `class_key`
   - 旧 `provisional_identity`（v1+meeting）は後方互換の lookup のみ

3. Meeting 差分:
   - 既存 OfficialMeeting を fingerprint 集合で diff
   - 追加/削除/更新を同一 OfficialClass 配下で実施
   - ImportRow.action = `update` + change payload（`meetings_changed`）

4. Identity カラム:
   - 新規行は v2（meeting なし）を `provisional_identity` に保存
   - または `provisional_identity` は互換維持し、`stable_key` を UNIQUE 追加

#### Phase 2（運用）

- 時限変更があっても canonical は触らない（Offering の meeting 同期は別ジョブ・明示実行）
- 「公式スロットと Offering スロット不一致」を admin 警告キューへ
- 学生 enroll 時の `slot_mismatch` は現状どおり 409（上書きしない）

#### Phase 3（任意）

- Offering meeting の追従を「承認付き sync」で提供（自動上書きはしない）

### 移行手順（概略）

1. migration: `stable_key` nullable → backfill → unique
2. import ロジックを stable_key 優先に切替（feature flag 可）
3. 既存の meeting 差分で作られた重複 OfficialClass は **自動マージせず**、admin に「同一 stable_key の重複」レポートを出し人手で片側を research_only / 破棄

### 受け入れ条件

- 同一 CSV を曜日だけ変えて再 import → OfficialClass 件数増なし
- 既存 canonical_offering_id が維持される
- student search に二重行が出ない
- 単体テスト: `test_meeting_change_updates_same_official_class`

## D. 本検証との関係

E2E では架空データのみを使い、identity 更新ロジック自体は未実装（提案のみ）。  
実装は別 PR とし、本ブランチでは検証・ドキュメントに限定する。
