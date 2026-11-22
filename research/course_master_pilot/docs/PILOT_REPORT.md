# Commerce 2026 course-master pilot report

Generated as a **research artifact**. Not loaded into production DB.

## 1. Could we create a usable trial CSV?

**Yes.**  
File: `derived/soc_2026_commerce_pilot_classes.csv`  
**72** structured class rows (cleaned; previously 74 before rejecting 2 PDF fragments) from the public 2026 商学部学科目配当表 (2024-entrant edition), limited to:

- 専門基礎科目（必修）
- 専門基礎科目（選択）
- 専門教育科目：経営トラック

### Reuse / acquisition notes (confirmed vs unknown)

| Item | Status |
|------|--------|
| PDF is publicly linked from the faculty registration page | Confirmed |
| Binary PDF download from this agent host | Blocked by Cloudflare interstitial; text extract retained via WebFetch |
| Dedicated ToS on the haibun PDF itself | **Not found** on the registration page |
| 『早稲田商学』publication reuse rules | Confirmed for that journal site only — **not** automatically the same as the haibun PDF |
| Webシラバス scrape for subject_key | **Not performed** (policy) |
| Intended use of this CSV | Internal technical validation only |

**Recommendation before productizing:** ask the faculty/university for redistribution permission or an official data feed.

## 2. Extraction quality

From `derived/soc_2026_commerce_pilot_quality.json` (after title-guard cleanup):

| Metric | Result |
|--------|--------|
| Pilot class rows | **72** (in 50–150 target) |
| Active (not cancelled) | 57 |
| Cancelled (kept, flagged) | 15 |
| Title extraction success | **100%** |
| Instructor success (active or cancelled-ok) | **98.6%** (71/72) |
| Semester success | **100%** |
| Schedule present | **100%** |
| Official `subject_key` | **0** (intentionally blank) |
| Exact duplicate rows dropped | **0** (was 26 garbage slot-titles; now rejected pre-parse) |
| Needs human review | **6** (was 8; 2 garbage fragments removed) |

See `VALIDATION_REVIEW.md` for the PR#4 8/26 audit.

## 3. Option A vs B

See `DESIGN_COMPARISON.md`. Implementation follows **Option B**.

## 4. Recommended DB design

**OfficialClass (+ OfficialMeeting) with `OfferingOfficialLink`.**  
Details: `OPTION_B_DESIGN.md`. Code: `app/models.py`, `app/official_course_services.py`, migration `0081_official_course_master`.

## 5. Student UI (minimal)

See `STUDENT_UI_MINI_SPEC.md`.

## 6. Remaining work to safe prod

See `REMAINING_PROD_WORK.md`.

## Files

- `raw/SOURCE.md` — provenance
- `raw/soc_2026_haibun_2024entrant.webfetch.txt` — source extract
- `scripts/extract_haibun_tables.py` — deterministic parser
- `derived/soc_2026_commerce_pilot_classes.csv` — pilot dataset
- `derived/soc_2026_commerce_pilot_needs_review.csv` — review subset
- `derived/soc_2026_commerce_pilot_quality.json` — metrics
- `docs/VALIDATION_REVIEW.md` — 8/26 audit
- `docs/OPTION_B_DESIGN.md` — linking / migration design
- `docs/STUDENT_UI_MINI_SPEC.md` — UI mini-spec
- `docs/REMAINING_PROD_WORK.md` — prod checklist
