export function AccountAvatar({
  url,
  initial,
  className,
}: {
  url?: string;
  initial: string;
  className: string;
}) {
  return (
    <span className={className} aria-hidden="true">
      {url ? <img src={url} alt="" /> : initial}
    </span>
  );
}
