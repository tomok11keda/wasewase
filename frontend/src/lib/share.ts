/** External share helpers. Payload is generic — no student UGC or media URLs. */

export const SHARE_TITLE = "わせわせ";
export const SHARE_TEXT = "わせわせ";

export type SharePayload = {
  title: string;
  text: string;
  url: string;
};

export function siteOrigin(): string {
  if (typeof window !== "undefined" && window.location?.origin) {
    return window.location.origin;
  }
  return "https://wasewase.onrender.com";
}

export function timelinePostShareUrl(postId: number): string {
  return `${siteOrigin()}/app/posts/${postId}`;
}

export function fleaProductShareUrl(productId: number): string {
  return `${siteOrigin()}/app/flea/products/${productId}`;
}

export function genericSharePayload(url: string): SharePayload {
  return { title: SHARE_TITLE, text: SHARE_TEXT, url };
}

export function canUseWebShare(): boolean {
  return typeof navigator !== "undefined" && typeof navigator.share === "function";
}

export async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    /* fall through */
  }
  try {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.left = "-9999px";
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(ta);
    return ok;
  } catch {
    return false;
  }
}

export async function shareWithSystemSheet(
  payload: SharePayload
): Promise<"shared" | "cancelled" | "failed"> {
  if (!canUseWebShare()) return "failed";
  try {
    await navigator.share({
      title: payload.title,
      text: payload.text,
      url: payload.url,
    });
    return "shared";
  } catch (err) {
    const name =
      err && typeof err === "object" && "name" in err
        ? String((err as { name: unknown }).name)
        : "";
    if (name === "AbortError") return "cancelled";
    return "failed";
  }
}
