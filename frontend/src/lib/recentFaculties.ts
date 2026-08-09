import { useCallback, useMemo, useState } from "react";
import { FACULTY_IDS, isFacultyId } from "./faculties";

const STORAGE_KEY = "wase_recent_faculties";

function readRecent(): string[] {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((v): v is string => typeof v === "string" && isFacultyId(v))
      .filter((v, i, arr) => arr.indexOf(v) === i);
  } catch {
    return [];
  }
}

function writeRecent(ids: string[]) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(ids));
  } catch {
    /* ignore quota / private mode */
  }
}

/**
 * Build tab order: すべて | own faculty (fixed) | recent (MRU) | remaining.
 * Own faculty is never stored/reordered in the recent list.
 */
export function buildFacultyTabOrder(
  ownFaculty: string,
  recent: string[]
): string[] {
  const own = ownFaculty && isFacultyId(ownFaculty) ? ownFaculty : "";
  const recentClean = recent.filter((id) => id !== own && isFacultyId(id));
  const remaining = FACULTY_IDS.filter(
    (id) => id !== own && !recentClean.includes(id)
  );
  return own ? [own, ...recentClean, ...remaining] : [...recentClean, ...remaining];
}

export function useRecentFaculties(ownFaculty: string) {
  const [recent, setRecent] = useState<string[]>(() =>
    typeof window !== "undefined" ? readRecent() : []
  );

  const orderedFaculties = useMemo(
    () => buildFacultyTabOrder(ownFaculty, recent),
    [ownFaculty, recent]
  );

  const rememberFaculty = useCallback(
    (facultyId: string) => {
      if (!facultyId || !isFacultyId(facultyId)) return;
      if (ownFaculty && facultyId === ownFaculty) return;
      setRecent((prev) => {
        const next = [facultyId, ...prev.filter((id) => id !== facultyId)];
        writeRecent(next);
        return next;
      });
    },
    [ownFaculty]
  );

  return { orderedFaculties, rememberFaculty };
}
