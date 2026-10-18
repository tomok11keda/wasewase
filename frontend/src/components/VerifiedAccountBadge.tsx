export function shouldShowVerifiedAccountBadge(
  verified?: boolean | null
): boolean {
  return verified === true;
}

export function VerifiedAccountBadge({
  verified,
}: {
  verified?: boolean | null;
}) {
  if (!shouldShowVerifiedAccountBadge(verified)) return null;
  return (
    <span
      className="account-verified-badge"
      aria-label="WaseWase運営認証アカウント"
      role="img"
    >
      <svg
        viewBox="0 0 16 16"
        width="14"
        height="14"
        aria-hidden="true"
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
  );
}

export function AccountDisplayName({
  name,
  verified,
  className,
}: {
  name: string;
  verified?: boolean | null;
  className?: string;
}) {
  return (
    <span
      className={
        className
          ? `account-verified-name ${className}`
          : "account-verified-name"
      }
    >
      <span className="account-verified-name__text">{name}</span>
      <VerifiedAccountBadge verified={verified} />
    </span>
  );
}
