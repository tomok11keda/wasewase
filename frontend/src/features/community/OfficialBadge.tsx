export function shouldShowOfficialBadge(
  official?: boolean | null
): boolean {
  return official === true;
}

export function officialBoardClass(
  baseClass: string,
  official?: boolean | null
): string {
  if (!shouldShowOfficialBadge(official)) return baseClass;
  return `${baseClass} ${baseClass}--official`;
}

export function OfficialBadge({
  official,
}: {
  official?: boolean | null;
}) {
  if (!shouldShowOfficialBadge(official)) return null;
  return (
    <span className="official-badge" aria-label="公式コミュニティ">
      公式
    </span>
  );
}
