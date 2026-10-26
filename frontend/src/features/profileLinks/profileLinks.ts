export const PROFILE_LINK_MAX = 5;
export const PROFILE_LINK_TITLE_MAX = 40;
export const PROFILE_LINK_URL_MAX = 200;

export type ProfileLinkItem = {
  id: number | null;
  title: string;
  url: string;
  position: number;
};

export type ProfileLinkDraft = {
  clientKey: string;
  id: number | null;
  title: string;
  url: string;
};

export function isSafeHttpUrl(value: string): boolean {
  const raw = value.trim();
  if (!raw || raw.length > PROFILE_LINK_URL_MAX) return false;
  try {
    const parsed = new URL(raw);
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}

export function safeExternalHref(value: string): string | null {
  return isSafeHttpUrl(value) ? value.trim() : null;
}

export function profileLinkHostname(url: string): string {
  try {
    return new URL(url.trim()).hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
}

export function profileLinkDisplayTitle(link: {
  title?: string;
  url: string;
}): string {
  const title = (link.title || "").trim();
  if (title) return title;
  return profileLinkHostname(link.url) || link.url;
}

export function profileLinksChipLabel(links: ProfileLinkItem[]): string | null {
  const safe = visibleProfileLinks(links);
  if (!safe.length) return null;
  const first = profileLinkDisplayTitle(safe[0]);
  if (safe.length === 1) return first;
  return `${first} 他${safe.length - 1}件`;
}

export function visibleProfileLinks(links: ProfileLinkItem[]): ProfileLinkItem[] {
  return links.filter((link) => safeExternalHref(link.url));
}

export function parseProfileLinks(raw: unknown): ProfileLinkItem[] {
  if (!Array.isArray(raw)) return [];
  const items: ProfileLinkItem[] = [];
  for (const entry of raw) {
    if (!entry || typeof entry !== "object") continue;
    const row = entry as Record<string, unknown>;
    const url = typeof row.url === "string" ? row.url.trim() : "";
    if (!url || !isSafeHttpUrl(url)) continue;
    const idRaw = row.id;
    const id =
      idRaw == null || idRaw === ""
        ? null
        : Number.isFinite(Number(idRaw))
          ? Number(idRaw)
          : null;
    const position = Number(row.position);
    items.push({
      id,
      title: typeof row.title === "string" ? row.title : "",
      url,
      position: Number.isFinite(position) ? position : items.length,
    });
  }
  items.sort((a, b) => a.position - b.position);
  return items.slice(0, PROFILE_LINK_MAX);
}

export function draftsFromLinks(links: ProfileLinkItem[]): ProfileLinkDraft[] {
  return links.map((link, index) => ({
    clientKey:
      link.id != null ? `id-${link.id}` : `seed-${index}-${link.url}`,
    id: link.id,
    title: link.title,
    url: link.url,
  }));
}

export function emptyLinkDraft(): ProfileLinkDraft {
  return {
    clientKey: `new-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    id: null,
    title: "",
    url: "",
  };
}

export function compactLinkDrafts(drafts: ProfileLinkDraft[]): ProfileLinkDraft[] {
  return drafts.filter((draft) => draft.url.trim());
}

export function serializeLinksForApi(drafts: ProfileLinkDraft[]): Array<{
  title: string;
  url: string;
  position: number;
}> {
  return compactLinkDrafts(drafts).map((draft, index) => ({
    title: draft.title.trim(),
    url: draft.url.trim(),
    position: index,
  }));
}

export function linksSignature(drafts: ProfileLinkDraft[]): string {
  return JSON.stringify(
    serializeLinksForApi(drafts).map((item) => ({
      title: item.title,
      url: item.url,
    }))
  );
}

export function isInstagramUrl(url: string): boolean {
  const host = profileLinkHostname(url).toLowerCase();
  return host === "instagram.com" || host.endsWith(".instagram.com");
}

export function legacyUrlsFromLinks(drafts: ProfileLinkDraft[]): {
  instagram_url: string;
  website_url: string;
} {
  let instagram_url = "";
  let website_url = "";
  for (const draft of compactLinkDrafts(drafts)) {
    const url = draft.url.trim();
    if (!instagram_url && isInstagramUrl(url)) {
      instagram_url = url;
      continue;
    }
    if (!website_url) website_url = url;
  }
  return { instagram_url, website_url };
}

export function seedLinksFromLegacyUrls(
  instagramUrl: string,
  websiteUrl: string
): ProfileLinkItem[] {
  const items: ProfileLinkItem[] = [];
  const seen = new Set<string>();
  const add = (title: string, raw: string) => {
    const url = raw.trim();
    if (!url || !isSafeHttpUrl(url)) return;
    const key = url.replace(/\/+$/, "").toLowerCase();
    if (seen.has(key)) return;
    seen.add(key);
    items.push({
      id: null,
      title,
      url,
      position: items.length,
    });
  };
  add("Instagram", instagramUrl);
  add("公式Webサイト", websiteUrl);
  return items;
}

export function validateProfileLinkDrafts(
  drafts: ProfileLinkDraft[]
): Record<string, string> {
  const errors: Record<string, string> = {};
  const compacted = compactLinkDrafts(drafts);
  if (compacted.length > PROFILE_LINK_MAX) {
    errors.links = `リンクは${PROFILE_LINK_MAX}件までです。`;
    return errors;
  }
  const seen = new Set<string>();
  compacted.forEach((draft, index) => {
    const title = draft.title.trim();
    if (title.length > PROFILE_LINK_TITLE_MAX) {
      errors[`links.${index}.title`] =
        `表示名は${PROFILE_LINK_TITLE_MAX}文字以内で入力してください。`;
    }
    const url = draft.url.trim();
    if (!isSafeHttpUrl(url)) {
      errors[`links.${index}.url`] = "URLは http または https で入力してください。";
      return;
    }
    const key = url.replace(/\/+$/, "").toLowerCase();
    if (seen.has(key)) {
      errors.links = "同じURLは登録できません。";
    }
    seen.add(key);
  });
  drafts.forEach((draft, index) => {
    if (!draft.url.trim() && draft.title.trim()) {
      errors[`links.${index}.url`] = "URLを入力してください。";
    }
  });
  return errors;
}
