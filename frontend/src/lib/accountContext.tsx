import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { fetchManagedOrganizations } from "../features/orgs/api";
import {
  clearStoredOrganizationId,
  readStoredOrganizationId,
  resolveActiveOrganization,
  writeStoredOrganizationId,
  type ManagedOrganization,
} from "../features/orgs/managedOrganizations";
import { useSession } from "./session";

export type AccountActor =
  | { type: "personal" }
  | { type: "organization"; organization: ManagedOrganization };

type AccountState = {
  actor: AccountActor;
  organizations: ManagedOrganization[];
  loading: boolean;
  error: string | null;
  selectPersonal: () => void;
  selectOrganization: (id: number) => ManagedOrganization | null;
  refreshOrganizations: () => Promise<ManagedOrganization[]>;
};

const AccountContext = createContext<AccountState | null>(null);

export function AccountProvider({ children }: { children: ReactNode }) {
  const { me, loading: sessionLoading } = useSession();
  const userId = me?.authenticated ? me.user?.id ?? null : null;
  const userIdRef = useRef<number | null>(null);
  const [actor, setActor] = useState<AccountActor>({ type: "personal" });
  const [organizations, setOrganizations] = useState<ManagedOrganization[]>(
    []
  );
  const organizationsRef = useRef<ManagedOrganization[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const applyList = useCallback(
    (userPk: number, list: ManagedOrganization[], listLoaded: boolean) => {
      organizationsRef.current = list;
      setOrganizations(list);
      const stored = listLoaded ? readStoredOrganizationId(userPk) : null;
      const match = resolveActiveOrganization(list, stored, listLoaded);
      if (match) {
        setActor({ type: "organization", organization: match });
        return;
      }
      setActor({ type: "personal" });
      if (listLoaded && stored != null) {
        clearStoredOrganizationId(userPk);
      }
    },
    []
  );

  const refreshOrganizations = useCallback(async () => {
    const userPk = userIdRef.current;
    if (userPk == null) {
      organizationsRef.current = [];
      setOrganizations([]);
      setActor({ type: "personal" });
      setLoading(false);
      return [];
    }
    setLoading(true);
    try {
      const list = await fetchManagedOrganizations();
      setError(null);
      applyList(userPk, list, true);
      return list;
    } catch {
      setError("load_failed");
      organizationsRef.current = [];
      setOrganizations([]);
      setActor({ type: "personal" });
      return [];
    } finally {
      setLoading(false);
    }
  }, [applyList]);

  useEffect(() => {
    if (sessionLoading) return;
    const previous = userIdRef.current;
    if (userId == null) {
      if (previous != null) {
        clearStoredOrganizationId(previous);
      }
      userIdRef.current = null;
      organizationsRef.current = [];
      setOrganizations([]);
      setActor({ type: "personal" });
      setError(null);
      setLoading(false);
      return;
    }
    if (previous != null && previous !== userId) {
      clearStoredOrganizationId(previous);
      setActor({ type: "personal" });
      organizationsRef.current = [];
      setOrganizations([]);
    }
    userIdRef.current = userId;
    void refreshOrganizations();
  }, [sessionLoading, userId, refreshOrganizations]);

  const selectPersonal = useCallback(() => {
    const userPk = userIdRef.current;
    setActor({ type: "personal" });
    if (userPk != null) clearStoredOrganizationId(userPk);
  }, []);

  const selectOrganization = useCallback((id: number) => {
    const userPk = userIdRef.current;
    const match = organizationsRef.current.find(
      (item) => item.id === id && item.can_manage
    );
    if (!match || userPk == null) return null;
    setActor({ type: "organization", organization: match });
    writeStoredOrganizationId(userPk, match.id);
    return match;
  }, []);

  const value = useMemo(
    () => ({
      actor,
      organizations,
      loading,
      error,
      selectPersonal,
      selectOrganization,
      refreshOrganizations,
    }),
    [
      actor,
      organizations,
      loading,
      error,
      selectPersonal,
      selectOrganization,
      refreshOrganizations,
    ]
  );

  return (
    <AccountContext.Provider value={value}>{children}</AccountContext.Provider>
  );
}

export function useAccount(): AccountState {
  const ctx = useContext(AccountContext);
  if (!ctx) {
    throw new Error("useAccount must be used within AccountProvider");
  }
  return ctx;
}
