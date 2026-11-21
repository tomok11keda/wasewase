# Commerce 2026 course-master pilot report

Generated as a **research artifact**. Not loaded into production DB.

## 1. Could we create a usable trial CSV?

**Yes.**  
File: `derived/soc_2026_commerce_pilot_classes.csv`  
**74** structured class rows from the public 2026 商学部学科目配当表 (2024-entrant edition), limited to:

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

From `derived/soc_2026_commerce_pilot_quality.json`:

| Metric | Result |
|--------|--------|
| Pilot class rows | **74** (in 50–150 target) |
| Active (not cancelled) | 59 |
| Cancelled (kept, flagged) | 15 |
| Title extraction success | **100%** (74/74) |
| Instructor success (active or cancelled-ok) | **95.9%** (71/74) |
| Semester success | **97.3%** (72/74) |
| Schedule present (incl. OD `無`) | **97.3%** (72/74) among pilot metrics; 57 active rows have concrete weekday slots or OD |
| Official `subject_key` | **0** (intentionally blank) |
| Official syllabus class code | **0** (intentionally blank) |
| Haibun class number present | 72/74 |
| Exact duplicate rows dropped pre-pilot | 26 |
| Soft duplicate groups (title+semester+class) | 0 |
| Needs human review | **8** |
| AI invented fields | **None** — ambiguous rows flagged, not filled |

Typical review reasons: missing instructor on a multi-line PDF cell, semester cell noise, cancelled rows, or rare unparsed class numbers.

## 3. Option A vs B

See `DESIGN_COMPARISON.md`.

## 4. Recommended DB design

**OfficialClass (+ OfficialMeeting) with `OfferingOfficialLink` (Option B).**  
Keep existing `CourseOffering` / course talk untouched until a reviewed link or explicit merge.

## 5. Work to reach production (no steps executed here)

1. Legal/data permission for catalog reuse or university CSV/API.
2. Apply Option B migrations on a branch; never mutate prod offerings on import.
3. Admin importer for haibun/CSV → `OfficialClass`.
4. Optional later: consented, rate-limited syllabus enrichment for `subject_key` only where permitted.
5. UI: “公式から選ぶ” search over `OfficialClass`.
6. Opt-in link / enroll flow; no auto talk merge.
7. Expand beyond 経営トラック after quality bar is met.

## 6. Next features to implement

1. Read-only admin preview of official CSV → dry-run insert counts.
2. Student search against `OfficialClass` (Commerce pilot flag).
3. “Link my free-text offering” review queue (no auto-merge).
4. Screenshot OCR → candidate `OfficialClass` matches (confirm UI).

## Files

- `raw/SOURCE.md` — provenance
- `raw/soc_2026_haibun_2024entrant.webfetch.txt` — source extract
- `scripts/extract_haibun_tables.py` — deterministic parser
- `derived/soc_2026_commerce_pilot_classes.csv` — pilot dataset
- `derived/soc_2026_commerce_pilot_needs_review.csv` — review subset
- `derived/soc_2026_commerce_pilot_quality.json` — metrics
