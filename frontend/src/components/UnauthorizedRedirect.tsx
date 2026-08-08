import { useEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";

/**
 * Convert /api/v1/* HTTP 401 into SPA login navigation (no full reload when possible).
 */
export function UnauthorizedRedirect() {
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    const original = window.fetch.bind(window);
    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const res = await original(input, init);
      try {
        let url = "";
        if (typeof input === "string") url = input;
        else if (input instanceof URL) url = input.href;
        else url = input.url;
        const isV1 = url.includes("/api/v1/");
        const isAuthBootstrap =
          url.includes("/api/v1/auth/") || url.includes("/api/v1/me/");
        if (res.status === 401 && isV1 && !isAuthBootstrap) {
          const next = `/app${location.pathname}${location.search}`;
          // Avoid loops while already on auth screens
          if (!location.pathname.startsWith("/login")) {
            navigate(`/login?next=${encodeURIComponent(next)}`, {
              replace: true,
            });
          }
        }
      } catch {
        /* ignore */
      }
      return res;
    };
    return () => {
      window.fetch = original;
    };
  }, [navigate, location.pathname, location.search]);

  return null;
}
