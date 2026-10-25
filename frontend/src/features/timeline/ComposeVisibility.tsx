import {
  DEFAULT_ORGANIZATION_COMPOSE_VISIBILITY,
  ORGANIZATION_POST_VISIBILITY,
  type OrganizationPostVisibility,
} from "./organizationPostVisibility";

const OPTIONS: {
  value: OrganizationPostVisibility;
  title: string;
  description: string;
}[] = [
  {
    value: ORGANIZATION_POST_VISIBILITY.public,
    title: "公開",
    description: "タイムライン・検索・団体プロフィールに表示します。",
  },
  {
    value: ORGANIZATION_POST_VISIBILITY.draft,
    title: "下書き",
    description: "管理者だけが見られます。あとから公開できます。",
  },
];

export function ComposeVisibility({
  value,
  onChange,
  disabled,
}: {
  value: OrganizationPostVisibility;
  onChange: (next: OrganizationPostVisibility) => void;
  disabled?: boolean;
}) {
  const selected = value || DEFAULT_ORGANIZATION_COMPOSE_VISIBILITY;
  return (
    <fieldset className="spa-compose__visibility" disabled={disabled}>
      <legend>公開範囲</legend>
      <p className="spa-compose__visibility-note">
        初期状態は下書きです。公開を選ぶまで、一般のタイムラインと検索には出ません。
      </p>
      <div className="spa-compose__visibility-options" role="radiogroup">
        {OPTIONS.map((option) => {
          const checked = selected === option.value;
          return (
            <label
              key={option.value}
              className={`spa-compose__visibility-option${
                checked ? " is-selected" : ""
              }`}
            >
              <input
                type="radio"
                name="organization-visibility"
                value={option.value}
                checked={checked}
                disabled={disabled}
                onChange={() => onChange(option.value)}
              />
              <span>
                <strong>{option.title}</strong>
                <small>{option.description}</small>
              </span>
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}
