import { facultyShortLabel } from "../lib/faculties";
import { useRecentFaculties } from "../lib/recentFaculties";

type Props = {
  /** Selected faculty ID, or "" for すべて. */
  value: string;
  /** Current user's UserProfile.department (may be empty). */
  ownFaculty?: string;
  onChange: (facultyId: string) => void;
  ariaLabel?: string;
  className?: string;
};

/**
 * Shared horizontal faculty filter: すべて | own | recent MRU | rest.
 */
export function FacultyFilterTabs({
  value,
  ownFaculty = "",
  onChange,
  ariaLabel = "学部フィルター",
  className = "",
}: Props) {
  const { orderedFaculties, rememberFaculty } = useRecentFaculties(ownFaculty);

  const select = (facultyId: string) => {
    if (facultyId) rememberFaculty(facultyId);
    onChange(facultyId);
  };

  return (
    <div
      className={`faculty-filter-section${className ? ` ${className}` : ""}`}
      aria-label={ariaLabel}
    >
      <div className="faculty-tabs" role="tablist" aria-label={ariaLabel}>
        <button
          type="button"
          role="tab"
          aria-selected={value === ""}
          className={`faculty-tab${value === "" ? " is-active" : ""}`}
          onClick={() => select("")}
        >
          すべて
        </button>
        {orderedFaculties.map((id) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={value === id}
            title={id}
            className={`faculty-tab${value === id ? " is-active" : ""}`}
            onClick={() => select(id)}
          >
            {facultyShortLabel(id)}
          </button>
        ))}
      </div>
    </div>
  );
}
