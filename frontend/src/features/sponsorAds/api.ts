import { getCsrfToken } from "../timeline/api";

export async function recordSponsorImpression(
  adId: number,
  placement: string
): Promise<boolean> {
  try {
    const res = await fetch(`/api/v1/sponsor-ads/${adId}/impression/`, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-CSRFToken": getCsrfToken(),
      },
      body: JSON.stringify({ placement }),
    });
    return res.ok;
  } catch {
    return false;
  }
}

export async function recordSponsorClick(
  adId: number,
  placement: string
): Promise<boolean> {
  try {
    const res = await fetch(`/api/v1/sponsor-ads/${adId}/click/`, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-CSRFToken": getCsrfToken(),
      },
      body: JSON.stringify({ placement }),
    });
    return res.ok;
  } catch {
    return false;
  }
}
