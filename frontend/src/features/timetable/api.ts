import { getCsrfToken } from "../timeline/api";

export type SlotEntry = {
  slot_key?: string;
  name: string;
  room: string;
  credits: string;
  memo: string;
};

export type SlotsMap = Record<string, SlotEntry>;

export type OwnSlotsResponse = {
  slots: SlotsMap;
  is_timetable_public: boolean;
};

export type PublicSlotsResponse = {
  ok: boolean;
  owner: { id: number; display_name: string };
  is_own: boolean;
  is_timetable_public: boolean;
  read_only: boolean;
  slots: SlotsMap;
};

export const TIMETABLE_DAYS = ["月", "火", "水", "木", "金", "土"] as const;

export const TIMETABLE_PERIODS = [
  { number: 1, label: "1限", time: "8:50-10:30" },
  { number: 2, label: "2限", time: "10:40-12:20" },
  { number: 3, label: "3限", time: "13:10-14:50" },
  { number: 4, label: "4限", time: "15:05-16:45" },
  { number: 5, label: "5限", time: "17:00-18:40" },
] as const;

export const TIMETABLE_OD_SLOTS = [
  { number: 1, label: "OD1", time: "オンデマンド" },
  { number: 2, label: "OD2", time: "オンデマンド" },
] as const;

export function emptyEntry(): SlotEntry {
  return { name: "", room: "", credits: "", memo: "" };
}

export function metaText(entry: SlotEntry, kind: "period" | "od"): string {
  if (kind === "od") {
    if (entry.credits) return `${entry.credits}単位`;
    return entry.name ? "OD" : "";
  }
  if (entry.room) return entry.room;
  if (entry.credits) return `${entry.credits}単位`;
  return "";
}

export async function fetchOwnSlots(): Promise<OwnSlotsResponse> {
  const res = await fetch("/api/timetable/slots/", {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  });
  if (!res.ok) throw new Error(`slots_${res.status}`);
  return res.json();
}

export async function fetchUserSlots(userPk: number): Promise<PublicSlotsResponse> {
  const res = await fetch(`/api/timetable/user/${userPk}/`, {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  });
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || `user_slots_${res.status}`);
  return data as PublicSlotsResponse;
}

export async function saveSlot(
  slotKey: string,
  entry: SlotEntry
): Promise<{ deleted: boolean; entry: SlotEntry }> {
  const res = await fetch("/api/timetable/slot/", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-CSRFToken": getCsrfToken(),
    },
    body: JSON.stringify({
      slot_key: slotKey,
      name: entry.name || "",
      room: entry.room || "",
      credits: entry.credits || "",
      memo: entry.memo || "",
    }),
  });
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || "save_failed");
  return {
    deleted: Boolean(data.deleted),
    entry: {
      name: data.entry?.name || "",
      room: data.entry?.room || "",
      credits: data.entry?.credits || "",
      memo: data.entry?.memo || "",
    },
  };
}

export async function setTimetableVisibility(
  isPublic: boolean
): Promise<{ is_timetable_public: boolean; label: string }> {
  const res = await fetch("/api/timetable/visibility/", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-CSRFToken": getCsrfToken(),
    },
    body: JSON.stringify({ is_public: isPublic }),
  });
  if (!res.ok) throw new Error("visibility_update_failed");
  return res.json();
}
