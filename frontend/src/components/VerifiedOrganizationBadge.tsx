export function shouldShowVerifiedOrganizationBadge(
  verified?: boolean | null
): boolean {
  return verified === true;
}

export function VerifiedOrganizationBadge({
  verified,
}: {
  verified?: boolean | null;
}) {
  if (!shouldShowVerifiedOrganizationBadge(verified)) return null;
  return (
    <span className="org-verified-badge">
      <span
        className="account-verified-badge"
        aria-hidden="true"
      >
        <svg
          viewBox="0 0 16 16"
          width="14"
          height="14"
          focusable="false"
        >
          <circle cx="8" cy="8" r="8" fill="currentColor" />
          <path
            d="M4.55 8.2 6.85 10.45 11.45 5.7"
            fill="none"
            stroke="#fff"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </span>
      <span className="org-verified-badge__label">運営確認済み団体</span>
    </span>
  );
}
