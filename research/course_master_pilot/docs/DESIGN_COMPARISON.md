# Course master DB design comparison (pilot)

Scope: design validation only. No production schema change in this branch.

## Option A — Extend `CourseOffering`

Add columns such as `subject_key`, `syllabus_class_code`, `course_code`, `official_school`, `source=official` onto the existing offering row that already owns timetable slots, enrollments, reviews, and `chat_room`.

| Criterion | Assessment |
|-----------|------------|
| Existing user data protection | Risky if backfilled/merged eagerly. One row mixes user-created and official identity. |
| Course-talk dedupe | Helps only after successful in-place merge; mistakes rewrite the live talk FK target. |
| Implementation / maintenance | Fewer tables, but migrations touch the hottest course table; year rollover mutates live rows. |
| AI timetable registration | OCR can write keys onto offerings, but bad matches pollute production identity. |
| Academic-year updates | Old-year offerings must be cloned or overwritten carefully. |
| Campus-wide rollout | Harder: every faculty’s quirks land on the same mutable table. |

## Option B — Separate `OfficialClass` (+ link table) **recommended**

Keep `Course` / `CourseOffering` / talk as today. Add official catalog tables and an optional link:

- `OfficialSubject` — subject-level facts for a year (`subject_key` when known)
- `OfficialClass` — class offering unit (`academic_year + subject_key + class_code` when known; pilot may key by haibun identity until syllabus IDs exist)
- `OfficialMeeting` — published meetings
- `OfferingOfficialLink` — `offering_id` ↔ `official_class_id` with confidence / method / reviewer

| Criterion | Assessment |
|-----------|------------|
| Existing user data protection | **Best.** Official import never rewrites offerings; links are additive and reversible. |
| Course-talk dedupe | Talk stays on `CourseOffering`. Dedup uses existing `merge_offerings` only after explicit review of links. |
| Implementation / maintenance | Extra models, but clear boundaries; official reload can truncate/replace official tables safely. |
| AI timetable registration | AI/OCR proposes `OfficialClass` candidates; user confirms → create/link offering. Failures stay out of live talk. |
| Academic-year updates | Load a new year into official tables; prior years remain queryable. |
| Campus-wide rollout | Per-faculty import pipelines feed the same official schema. |

## Recommendation

**Choose B (OfficialClass + link).**

It is the simplest *safe* design relative to WaseWase’s current constraints:

1. Free-text offerings and course talks already exist in production.
2. This pilot proved we can build a useful catalog **without** syllabus `subject_key` yet.
3. Until official IDs arrive, B still works with provisional natural keys from the haibun (`year+school+title+class_no+semester+meetings`) while leaving `subject_key` / `syllabus_class_code` nullable.

Do **not** auto-merge production offerings in the first production rollout.

## Minimal schema sketch (not applied)

```text
OfficialClass
  id
  academic_year
  school
  title
  title_normalized
  haibun_class_no          # from 配当表; not a fabricated syllabus code
  subject_key              # nullable until syllabus/API available
  syllabus_class_code      # nullable
  course_code              # nullable
  semester_code
  instructor_text
  credits                  # nullable if absent in source
  modality_raw
  is_cancelled
  source_url
  source_extract_line
  source_raw_line
  UNIQUE soft # when subject_key present
    (academic_year, subject_key, syllabus_class_code)
  UNIQUE NULLS NOT DISTINCT  # provisional pilot identity when keys absent
    (academic_year, school, title_normalized, haibun_class_no, semester_code)

OfferingOfficialLink
  offering_id UNIQUE
  official_class_id
  match_method  # exact_haibun / manual / ai_suggested
  confidence
  reviewed_at / reviewed_by
```
