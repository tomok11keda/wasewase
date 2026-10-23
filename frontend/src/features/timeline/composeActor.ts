export type ComposeOrganization = {
  id: number;
  name: string;
  slug: string;
  avatar_url: string;
  is_verified: boolean;
};

export type ComposeActorSnapshot =
  | { type: "personal" }
  | { type: "organization"; organization: ComposeOrganization };

export function snapshotComposeActor(
  actor: ComposeActorSnapshot | null | undefined
): ComposeActorSnapshot {
  if (actor?.type === "organization" && actor.organization?.id) {
    const org = actor.organization;
    return {
      type: "organization",
      organization: {
        id: org.id,
        name: org.name,
        slug: org.slug,
        avatar_url: org.avatar_url || "",
        is_verified: org.is_verified === true,
      },
    };
  }
  return { type: "personal" };
}

export function composeActorKey(actor: ComposeActorSnapshot | null | undefined): string {
  if (actor?.type === "organization" && actor.organization?.id) {
    return `organization:${actor.organization.id}`;
  }
  return "personal";
}

export function composeActorsEqual(
  a: ComposeActorSnapshot | null | undefined,
  b: ComposeActorSnapshot | null | undefined
): boolean {
  return composeActorKey(a) === composeActorKey(b);
}

export function composeActorLabel(actor: ComposeActorSnapshot | null | undefined): string {
  if (actor?.type === "organization") {
    return actor.organization.name || "学生団体";
  }
  return "個人アカウント";
}

/** 個人モードでは organization_id を付けない。失敗時の個人フォールバック禁止。 */
export function organizationIdForCompose(
  actor: ComposeActorSnapshot | null | undefined
): number | null {
  if (actor?.type !== "organization") return null;
  const id = actor.organization.id;
  return Number.isInteger(id) && id > 0 ? id : null;
}

export function composeModeCaption(actor: ComposeActorSnapshot | null | undefined): string {
  return actor?.type === "organization"
    ? "学生団体として投稿"
    : "個人アカウントとして投稿";
}
