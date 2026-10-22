export type ManagedOrganization = {
  id: number;
  name: string;
  slug: string;
  avatar_url: string;
  is_verified: boolean;
  my_role: string;
  can_manage: boolean;
};

export type ManagedOrganizationsPayload = {
  ok: boolean;
  organizations: ManagedOrganization[];
};

const STORAGE_PREFIX = "wase_active_organization:";
const ALLOWED_KEYS = new Set([
  "id",
  "name",
  "slug",
  "avatar_url",
  "is_verified",
  "my_role",
  "can_manage",
]);

export function organizationStorageKey(userId: number): string {
  return `${STORAGE_PREFIX}${userId}`;
}

export function organizationRoleLabel(role: string): string {
  if (role === "owner") return "代表管理者";
  if (role === "admin") return "管理者";
  return role;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

export function parseManagedOrganization(
  value: unknown
): ManagedOrganization | null {
  const item = asRecord(value);
  if (!item) return null;
  if (typeof item.id !== "number" || !Number.isInteger(item.id) || item.id <= 0) {
    return null;
  }
  if (typeof item.name !== "string" || !item.name.trim()) return null;
  if (typeof item.slug !== "string" || !item.slug.trim()) return null;
  if (typeof item.avatar_url !== "string") return null;
  if (typeof item.is_verified !== "boolean") return null;
  if (typeof item.my_role !== "string" || !item.my_role) return null;
  if (item.can_manage !== true) return null;
  if (item.my_role !== "owner" && item.my_role !== "admin") return null;
  return {
    id: item.id,
    name: item.name,
    slug: item.slug,
    avatar_url: item.avatar_url,
    is_verified: item.is_verified,
    my_role: item.my_role,
    can_manage: true,
  };
}

export function parseManagedOrganizationsPayload(
  value: unknown
): ManagedOrganization[] | null {
  const data = asRecord(value);
  if (!data || data.ok !== true || !Array.isArray(data.organizations)) {
    return null;
  }
  const organizations: ManagedOrganization[] = [];
  for (const raw of data.organizations) {
    const parsed = parseManagedOrganization(raw);
    if (!parsed) return null;
    const extra = Object.keys(asRecord(raw) || {}).some(
      (key) => !ALLOWED_KEYS.has(key)
    );
    if (extra) return null;
    organizations.push(parsed);
  }
  return organizations;
}

export function resolveActiveOrganization(
  organizations: ManagedOrganization[],
  storedId: number | null,
  listLoaded: boolean
): ManagedOrganization | null {
  if (!listLoaded || storedId == null) return null;
  return (
    organizations.find((item) => item.id === storedId && item.can_manage) ||
    null
  );
}

function storage(): Storage | null {
  try {
    const root =
      typeof window !== "undefined"
        ? window
        : (globalThis as { localStorage?: Storage });
    return root.localStorage ?? null;
  } catch {
    return null;
  }
}

export function readStoredOrganizationId(userId: number): number | null {
  if (!Number.isInteger(userId) || userId <= 0) return null;
  const raw = storage()?.getItem(organizationStorageKey(userId));
  if (!raw) return null;
  const parsed = Number(raw);
  if (!Number.isInteger(parsed) || parsed <= 0) return null;
  return parsed;
}

export function writeStoredOrganizationId(
  userId: number,
  organizationId: number
): void {
  if (!Number.isInteger(userId) || userId <= 0) return;
  if (!Number.isInteger(organizationId) || organizationId <= 0) return;
  try {
    storage()?.setItem(
      organizationStorageKey(userId),
      String(organizationId)
    );
  } catch {
    /* ignore quota / private mode */
  }
}

export function clearStoredOrganizationId(userId: number): void {
  if (!Number.isInteger(userId) || userId <= 0) return;
  try {
    storage()?.removeItem(organizationStorageKey(userId));
  } catch {
    /* ignore */
  }
}
