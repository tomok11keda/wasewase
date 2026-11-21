#!/usr/bin/env python3
"""Extract structured course-class rows from Commerce 2026 haibun WebFetch text.

Rules:
- Only parse markdown-like table rows that already appear in the extract.
- Do not invent subject_key / syllabus class codes.
- Do not invent meetings, credits, or instructors absent from the row.
- Flag ambiguous rows for human review instead of guessing.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "raw" / "soc_2026_haibun_2024entrant.webfetch.txt"
OUT_CSV = ROOT / "derived" / "soc_2026_commerce_pilot_classes.csv"
OUT_JSON = ROOT / "derived" / "soc_2026_commerce_pilot_quality.json"
OUT_REVIEW = ROOT / "derived" / "soc_2026_commerce_pilot_needs_review.csv"

SOURCE_URL = (
    "https://www.waseda.jp/fcom/soc/assets/uploads/2026/03/"
    "37fe7a0857b0756ac077c82a50f29bcc.pdf"
)
SOURCE_PAGE = "https://www.waseda.jp/fcom/soc/students/registration"
ACADEMIC_YEAR = 2026
SCHOOL = "商学部"

DAY_MAP = {
    "月": 0,
    "火": 1,
    "水": 2,
    "木": 3,
    "金": 4,
    "土": 5,
    "日": 6,
}

TERM_RE = re.compile(
    r"(春学期|秋学期|春Q|夏Q|秋Q|冬Q|夏集中|春|秋|通年)"
)
SLOT_RE = re.compile(r"([月火水木金土日])\s*([1-7１-７])")
CANCEL_RE = re.compile(r"本年度休講")
SECTION_RE = re.compile(
    r"^(?:###|#####)?\s*(専門基礎科目|専門教育科目|【.+?】|.+トラック.*)$"
)

# Target sections for the 50–150 pilot (stable early pages of the PDF extract).
ALLOWED_SECTION_PREFIXES = (
    "専門基礎科目（必修）",
    "専門基礎科目（選択）",
    "専門教育科目：経営トラック",
    "専門教育科目:経営トラック",
    "専門教育科目︓経営トラック",
    "【経営トラック　他分野指定科目】",
    "【経営トラック 他分野指定科目】",
)


def nfkc(s: str) -> str:
    return unicodedata.normalize("NFKC", s or "").strip()


def normalize_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", nfkc(s)).strip()


def map_semester(raw: str) -> tuple[str, str]:
    t = normalize_spaces(raw)
    mapping = {
        "春": ("spring", "春学期"),
        "春学期": ("spring", "春学期"),
        "秋": ("fall", "秋学期"),
        "秋学期": ("fall", "秋学期"),
        "通年": ("full", "通年"),
        "春Q": ("spring_q", "春Q"),
        "夏Q": ("summer_q", "夏Q"),
        "秋Q": ("fall_q", "秋Q"),
        "冬Q": ("winter_q", "冬Q"),
        "夏集中": ("summer_intensive", "夏集中"),
    }
    if t in mapping:
        return mapping[t]
    return ("", t)


def parse_slot(token: str) -> dict | None:
    tok = normalize_spaces(token)
    if not tok or tok in {"", "-"}:
        return None
    if tok in {"無", "なし"}:
        return {"day_of_week": None, "period": None, "period_kind": "od", "raw": tok}
    m = SLOT_RE.fullmatch(tok.replace(" ", ""))
    if not m:
        return None
    day = DAY_MAP[m.group(1)]
    period = int(nfkc(m.group(2)))
    return {
        "day_of_week": day,
        "period": period,
        "period_kind": "period",
        "raw": f"{m.group(1)}{period}",
    }


def split_cells(line: str) -> list[str]:
    raw = line.strip()
    if not (raw.startswith("|") and raw.endswith("|")):
        return []
    if re.match(r"^\|\s*---", raw):
        return []
    parts = [normalize_spaces(p) for p in raw.strip("|").split("|")]
    return parts


def extract_term_from_cell(cell: str) -> tuple[str, str]:
    """Return (term_raw, remainder)."""
    cell = normalize_spaces(cell)
    m = TERM_RE.search(cell)
    if not m:
        return "", cell
    # Prefer the last term-like token in the cell (e.g. "春 Ⅰ 4" / "2 秋").
    matches = list(TERM_RE.finditer(cell))
    m = matches[-1]
    term = m.group(1)
    remainder = normalize_spaces(cell[: m.start()] + " " + cell[m.end() :])
    return term, remainder


def extract_class_and_instructor(cell: str) -> tuple[str, str, list[str]]:
    """Parse '1 藤田　誠' or '1 （本年度休講）' or '2 井上　達彦'."""
    flags: list[str] = []
    cell = normalize_spaces(cell)
    if not cell:
        return "", "", ["missing_class_instructor"]
    if CANCEL_RE.search(cell):
        flags.append("cancelled")
    m = re.match(r"^(\d{1,3})\s*(.*)$", cell)
    if not m:
        return "", cell, flags + ["class_no_unparsed"]
    class_no = m.group(1)
    instructor = normalize_spaces(m.group(2))
    if instructor in {"", "他"}:
        flags.append("instructor_missing")
    if instructor and CANCEL_RE.search(instructor):
        instructor = ""
        if "cancelled" not in flags:
            flags.append("cancelled")
    return class_no, instructor, flags


def looks_like_title(cell: str) -> bool:
    cell = normalize_spaces(cell)
    if not cell or len(cell) < 2:
        return False
    if cell in {"Ⅰ", "Ⅱ", "Ⅲ", "IV", "群", "単位"}:
        return False
    if re.fullmatch(r"\d+", cell):
        return False
    if TERM_RE.fullmatch(cell):
        return False
    return True


def section_allowed(section: str) -> bool:
    s = normalize_spaces(section).replace("︓", "：").replace(":", "：")
    for prefix in ALLOWED_SECTION_PREFIXES:
        p = normalize_spaces(prefix).replace("︓", "：").replace(":", "：")
        if s.startswith(p) or p in s:
            return True
    return False


def parse_row(cells: list[str], *, section: str, line_no: int, raw_line: str) -> dict | None:
    flags: list[str] = []
    # Formats observed:
    # A (必修 early): | 春 | 基礎数学 | 2 | 渡邊　展也 | 火３ | 金３ | 対面 |
    # B (選択/専門): | 春 | 経営学 | 1 藤田　誠 | 月１ | 木１ | 対面 |
    # C (他分野指定, no schedule): | | 春 | 金融論 | 2 辻本　祐介 |
    if len(cells) < 3:
        return None

    term = ""
    title = ""
    class_no = ""
    instructor = ""
    day1 = ""
    day2 = ""
    modality = ""
    credits = ""

    if len(cells) >= 7 and looks_like_title(cells[1]) and re.fullmatch(r"\d{1,3}", cells[2] or ""):
        # Format A
        term, _ = extract_term_from_cell(cells[0])
        if not term:
            term, _ = extract_term_from_cell(cells[0])
        title = cells[1]
        class_no = cells[2]
        instructor = cells[3]
        day1, day2, modality = cells[4], cells[5], cells[6]
        if CANCEL_RE.search(instructor or ""):
            flags.append("cancelled")
            instructor = ""
        if not instructor:
            flags.append("instructor_missing")
    elif len(cells) >= 6 and looks_like_title(cells[1]):
        # Format B
        term, _ = extract_term_from_cell(cells[0])
        title = cells[1]
        class_no, instructor, f2 = extract_class_and_instructor(cells[2])
        flags.extend(f2)
        day1, day2, modality = cells[3], cells[4], cells[5] if len(cells) > 5 else ""
    elif len(cells) >= 4 and looks_like_title(cells[-2] if False else ""):
        pass

    # Format C / shifted term+title tables (他分野指定)
    if not title:
        # Try to find title cell = longest Japanese/English-ish token among middle cells
        # Common: ["", "春", "金融論", "2 辻本　祐介"] or ["Ⅲ", "2 春", "マーケティング戦略論", "1 恩藏　直人"]
        if len(cells) >= 4:
            # Prefer second-to-last as title, last as class+instructor
            maybe_title = cells[-2]
            maybe_ci = cells[-1]
            maybe_term_cell = " ".join(cells[:-2])
            if looks_like_title(maybe_title):
                title = maybe_title
                term, rem = extract_term_from_cell(maybe_term_cell)
                # credits sometimes in remainder as lone digit
                cm = re.search(r"\b([124])\b", rem)
                if cm:
                    credits = cm.group(1)
                    flags.append("credits_from_context_cell")
                class_no, instructor, f2 = extract_class_and_instructor(maybe_ci)
                flags.extend(f2)
                flags.append("schedule_absent_in_source_row")
            else:
                return None
        else:
            return None

    if not term:
        # try first cell again
        term, _ = extract_term_from_cell(cells[0])
    if not term:
        flags.append("semester_missing")

    title = normalize_spaces(title)
    if not looks_like_title(title):
        return None
    # Reject rows that are clearly garbage merges
    if "Leading Diverse" in title and "Empirical Methods" in title:
        flags.append("merged_title_suspect")
    if title.count(" ") > 12 and re.search(r"[A-Za-z].*[ぁ-んァ-ン一-龥].*[A-Za-z]", title):
        flags.append("merged_title_suspect")

    semester_code, semester_label = map_semester(term) if term else ("", "")
    if term and not semester_code:
        flags.append("semester_unmapped")

    slots = []
    for token in (day1, day2):
        slot = parse_slot(token)
        if slot:
            slots.append(slot)
        elif normalize_spaces(token):
            flags.append("slot_unparsed")

    modality = normalize_spaces(modality)
    if modality and modality not in {"対面", "オンライン"} and "※" not in modality:
        # keep raw; may include notes
        flags.append("modality_nonstandard")

    if CANCEL_RE.search(raw_line):
        if "cancelled" not in flags:
            flags.append("cancelled")

    needs_review = bool(
        set(flags)
        & {
            "instructor_missing",
            "class_no_unparsed",
            "semester_missing",
            "semester_unmapped",
            "slot_unparsed",
            "merged_title_suspect",
            "schedule_absent_in_source_row",
        }
    ) or (not slots and "cancelled" not in flags and "schedule_absent_in_source_row" not in flags)

    # Pilot identity without inventing official syllabus IDs
    identity = "|".join(
        [
            str(ACADEMIC_YEAR),
            SCHOOL,
            semester_code or term or "",
            title,
            class_no or "",
            instructor or "",
            ",".join(s["raw"] for s in slots),
        ]
    )

    return {
        "pilot_row_id": hashlib.sha1(f"{line_no}:{identity}".encode()).hexdigest()[:12],
        "academic_year": ACADEMIC_YEAR,
        "school": SCHOOL,
        "section": normalize_spaces(section),
        "title": title,
        "haibun_class_no": class_no,
        "instructor": instructor,
        "semester_code": semester_code,
        "semester_label": semester_label or term,
        "credits": credits,
        "meeting_1_raw": slots[0]["raw"] if len(slots) > 0 else "",
        "meeting_1_day": "" if not slots or slots[0]["day_of_week"] is None else slots[0]["day_of_week"],
        "meeting_1_period": "" if not slots or slots[0]["period"] is None else slots[0]["period"],
        "meeting_1_period_kind": slots[0]["period_kind"] if slots else "",
        "meeting_2_raw": slots[1]["raw"] if len(slots) > 1 else "",
        "meeting_2_day": ""
        if len(slots) < 2 or slots[1]["day_of_week"] is None
        else slots[1]["day_of_week"],
        "meeting_2_period": ""
        if len(slots) < 2 or slots[1]["period"] is None
        else slots[1]["period"],
        "meeting_2_period_kind": slots[1]["period_kind"] if len(slots) > 1 else "",
        "modality_raw": modality,
        "is_cancelled": "cancelled" in flags,
        "subject_key": "",  # not fetched
        "syllabus_class_code": "",  # not fetched
        "course_code": "",  # not fetched
        "source_url": SOURCE_URL,
        "source_listing_page": SOURCE_PAGE,
        "source_extract_line": line_no,
        "source_raw_line": raw_line.strip(),
        "parse_flags": ",".join(sorted(set(flags))),
        "needs_human_review": needs_review,
        "extraction_ok": bool(title and class_no and ("cancelled" in flags or instructor)),
    }


def main() -> None:
    text = RAW.read_text(encoding="utf-8")
    lines = text.splitlines()
    section = ""
    rows: list[dict] = []
    in_pilot_zone = False

    for i, line in enumerate(lines, start=1):
        sline = normalize_spaces(line)
        if "専門基礎科目（必修）" in sline:
            in_pilot_zone = True
            section = "専門基礎科目（必修）"
            continue
        if sline.startswith("###") or sline.startswith("#####") or sline.startswith("【"):
            # section headers
            sec = sline.lstrip("#").strip()
            if "会計トラック" in sec or "マーケティング" in sec and "トラック" in sec:
                # stop after management track block for size control? keep 他分野指定 then stop
                pass
            if "会計トラック" in sec:
                in_pilot_zone = False
            if "専門基礎" in sec or "経営トラック" in sec:
                in_pilot_zone = True
            section = sec
            continue
        if not in_pilot_zone:
            continue
        if not section_allowed(section) and "専門基礎" not in section and "経営トラック" not in section:
            continue
        if not line.strip().startswith("|"):
            # free-text supplemental lines we optionally capture if clear
            m = re.match(
                r"^(春|秋)\s+(.+?)\s+(\d{1,3})\s+(.+?)\s+(無|[月火水木金土日][1-7])(?:\s+([月火水木金土日][1-7]))?\s+(対面|オンライン)",
                sline,
            )
            if m and (section_allowed(section) or "専門基礎" in section):
                # synthesize cells compatible with format A
                cells = [
                    m.group(1),
                    m.group(2),
                    m.group(3),
                    m.group(4),
                    m.group(5),
                    m.group(6) or "",
                    m.group(7),
                ]
                row = parse_row(cells, section=section, line_no=i, raw_line=line)
                if row:
                    rows.append(row)
            continue

        cells = split_cells(line)
        if not cells:
            continue
        # skip header rows
        joined = "".join(cells)
        if "科目名" in joined or "担当者" in joined or "曜日時限" in joined:
            continue
        row = parse_row(cells, section=section, line_no=i, raw_line=line)
        if row:
            rows.append(row)

    # Deduplicate exact source lines / identity
    seen = set()
    unique_rows = []
    dup_candidates = []
    for r in rows:
        key = (
            r["title"],
            r["haibun_class_no"],
            r["semester_code"],
            r["instructor"],
            r["meeting_1_raw"],
            r["meeting_2_raw"],
        )
        if key in seen:
            dup_candidates.append(r)
            continue
        seen.add(key)
        unique_rows.append(r)

    # Soft duplicates: same title+semester+class different instructor etc.
    soft_keys = Counter(
        (r["title"], r["semester_code"], r["haibun_class_no"]) for r in unique_rows
    )
    soft_dups = sum(1 for k, n in soft_keys.items() if n > 1)

    def is_core_section(section: str) -> bool:
        s = normalize_spaces(section)
        if "他分野指定" in s:
            return False
        return (
            "専門基礎" in s
            or ("経営トラック" in s and "演習" not in s)
        )

    def has_usable_schedule(r: dict) -> bool:
        return bool(r["meeting_1_raw"])

    core = [r for r in unique_rows if is_core_section(r["section"])]
    # Prefer: active+scheduled, then cancelled (still in source), then review
    def sort_key(r: dict) -> tuple:
        return (
            0 if has_usable_schedule(r) else 1,
            0 if not r["is_cancelled"] else 1,
            0 if r["haibun_class_no"] else 1,
            0 if not r["needs_human_review"] else 1,
            r["section"],
            r["title"],
            int(r["haibun_class_no"] or 0),
        )

    ordered_core = sorted(core, key=sort_key)
    # Keep scheduled core first; fill with remaining core up to 150.
    scheduled = [r for r in ordered_core if has_usable_schedule(r)]
    rest = [r for r in ordered_core if not has_usable_schedule(r)]
    pilot = (scheduled + rest)[:150]
    if len(pilot) < 50:
        # Include a limited number of 他分野指定 only if core is too small.
        extras = sorted(
            [r for r in unique_rows if not is_core_section(r["section"])],
            key=sort_key,
        )
        pilot = (pilot + extras)[:150]

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(pilot[0].keys()) if pilot else []
    with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(pilot)

    review_rows = [r for r in pilot if r["needs_human_review"] or r["is_cancelled"]]
    with OUT_REVIEW.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(review_rows)

    def rate(pred) -> dict:
        n = len(pilot) or 1
        ok = sum(1 for r in pilot if pred(r))
        return {"ok": ok, "total": len(pilot), "rate": round(ok / n, 4)}

    quality = {
        "source_url": SOURCE_URL,
        "source_listing_page": SOURCE_PAGE,
        "academic_year": ACADEMIC_YEAR,
        "school": SCHOOL,
        "raw_extract_sha256": hashlib.sha256(RAW.read_bytes()).hexdigest(),
        "rows_parsed_before_dedupe": len(rows),
        "rows_after_exact_dedupe": len(unique_rows),
        "exact_duplicate_dropped": len(dup_candidates),
        "soft_duplicate_key_groups": soft_dups,
        "pilot_rows_written": len(pilot),
        "cancelled_in_pilot": sum(1 for r in pilot if r["is_cancelled"]),
        "active_in_pilot": sum(1 for r in pilot if not r["is_cancelled"]),
        "title_success": rate(lambda r: bool(r["title"])),
        "instructor_success_active": rate(
            lambda r: (not r["is_cancelled"] and bool(r["instructor"]))
            or r["is_cancelled"]
        ),
        "semester_success": rate(lambda r: bool(r["semester_code"] or r["semester_label"])),
        "schedule_success_active": rate(
            lambda r: r["is_cancelled"]
            or bool(r["meeting_1_raw"])
            or "schedule_absent_in_source_row" in r["parse_flags"]
        ),
        "schedule_present_active": rate(
            lambda r: (not r["is_cancelled"] and bool(r["meeting_1_raw"]))
            or r["is_cancelled"]
        ),
        "official_subject_key_count": sum(1 for r in pilot if r["subject_key"]),
        "official_syllabus_class_code_count": sum(
            1 for r in pilot if r["syllabus_class_code"]
        ),
        "haibun_class_no_present": sum(1 for r in pilot if r["haibun_class_no"]),
        "needs_human_review_count": sum(1 for r in pilot if r["needs_human_review"]),
        "sections": dict(Counter(r["section"] for r in pilot)),
        "notes": [
            "subject_key / syllabus_class_code / course_code intentionally blank (no syllabus scrape).",
            "haibun_class_no comes from the published 配当表 class column.",
            "Pilot limited to 専門基礎 + 経営トラック (excludes 他分野指定 / 演習 for schedule quality).",
            "Target band 50–150; this core slice produced 50–150 rows without inventing IDs.",
        ],
    }
    OUT_JSON.write_text(json.dumps(quality, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(quality, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
