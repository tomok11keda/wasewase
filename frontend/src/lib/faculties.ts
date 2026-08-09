/** Stable faculty IDs (= UserProfile.department / FACULTY_CHOICES values). */

export const FACULTY_IDS = [
  "政治経済学部",
  "法学部",
  "教育学部",
  "商学部",
  "社会科学部",
  "国際教養学部",
  "文化構想学部",
  "文学部",
  "基幹理工学部",
  "創造理工学部",
  "先進理工学部",
  "人間科学部",
  "スポーツ科学部",
  "その他",
] as const;

export type FacultyId = (typeof FACULTY_IDS)[number];

/** Short chip labels for the horizontal faculty filter tabs. */
export const FACULTY_SHORT_LABELS: Record<string, string> = {
  政治経済学部: "政経",
  法学部: "法",
  教育学部: "教育",
  商学部: "商",
  社会科学部: "社学",
  国際教養学部: "国教",
  文化構想学部: "文構",
  文学部: "文",
  基幹理工学部: "基幹",
  創造理工学部: "創造",
  先進理工学部: "先進",
  人間科学部: "人科",
  スポーツ科学部: "スポ科",
  その他: "その他",
};

export function facultyShortLabel(id: string): string {
  return FACULTY_SHORT_LABELS[id] || id;
}

export function isFacultyId(value: string): value is FacultyId {
  return (FACULTY_IDS as readonly string[]).includes(value);
}
