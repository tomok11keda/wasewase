import {
  PROFILE_LINK_MAX,
  PROFILE_LINK_TITLE_MAX,
  emptyLinkDraft,
  type ProfileLinkDraft,
} from "./profileLinks";

type Props = {
  drafts: ProfileLinkDraft[];
  disabled?: boolean;
  errors?: Record<string, string>;
  onChange: (drafts: ProfileLinkDraft[]) => void;
};

export function ProfileLinksEditor({
  drafts,
  disabled = false,
  errors = {},
  onChange,
}: Props) {
  const fieldError = (key: string) => errors[key] || null;
  const canAdd = drafts.length < PROFILE_LINK_MAX;

  const updateAt = (index: number, patch: Partial<ProfileLinkDraft>) => {
    onChange(
      drafts.map((draft, current) =>
        current === index ? { ...draft, ...patch } : draft
      )
    );
  };

  const move = (index: number, direction: -1 | 1) => {
    const next = index + direction;
    if (next < 0 || next >= drafts.length) return;
    const copy = drafts.slice();
    const [row] = copy.splice(index, 1);
    copy.splice(next, 0, row);
    onChange(copy);
  };

  return (
    <div className="profile-links-editor">
      <div className="profile-links-editor__head">
        <label>リンク</label>
        <p className="org-edit-hint">
          最大{PROFILE_LINK_MAX}件。表示名が空のときはドメイン名を表示します。
        </p>
      </div>
      {fieldError("links") ? (
        <p className="org-edit-field-error">{fieldError("links")}</p>
      ) : null}
      <ul className="profile-links-editor__list">
        {drafts.map((draft, index) => (
          <li key={draft.clientKey} className="profile-links-editor__row">
            <div className="profile-links-editor__fields">
              <label
                className="profile-links-editor__label"
                htmlFor={`profile-link-title-${draft.clientKey}`}
              >
                表示名
              </label>
              <input
                id={`profile-link-title-${draft.clientKey}`}
                type="text"
                value={draft.title}
                maxLength={PROFILE_LINK_TITLE_MAX}
                disabled={disabled}
                placeholder="例：Instagram"
                onChange={(event) =>
                  updateAt(index, { title: event.target.value })
                }
              />
              {fieldError(`links.${index}.title`) ? (
                <p className="org-edit-field-error">
                  {fieldError(`links.${index}.title`)}
                </p>
              ) : null}
              <label
                className="profile-links-editor__label"
                htmlFor={`profile-link-url-${draft.clientKey}`}
              >
                URL
              </label>
              <input
                id={`profile-link-url-${draft.clientKey}`}
                type="url"
                inputMode="url"
                value={draft.url}
                disabled={disabled}
                placeholder="https://"
                onChange={(event) =>
                  updateAt(index, { url: event.target.value })
                }
              />
              {fieldError(`links.${index}.url`) ? (
                <p className="org-edit-field-error">
                  {fieldError(`links.${index}.url`)}
                </p>
              ) : null}
            </div>
            <div className="profile-links-editor__actions">
              <button
                type="button"
                className="profile-links-editor__move"
                disabled={disabled || index === 0}
                aria-label="上へ"
                onClick={() => move(index, -1)}
              >
                ↑
              </button>
              <button
                type="button"
                className="profile-links-editor__move"
                disabled={disabled || index === drafts.length - 1}
                aria-label="下へ"
                onClick={() => move(index, 1)}
              >
                ↓
              </button>
              <button
                type="button"
                className="profile-links-editor__remove"
                disabled={disabled}
                aria-label="削除"
                onClick={() =>
                  onChange(drafts.filter((_, current) => current !== index))
                }
              >
                削除
              </button>
            </div>
          </li>
        ))}
      </ul>
      <button
        type="button"
        className="btn btn-secondary profile-links-editor__add"
        disabled={disabled || !canAdd}
        onClick={() => onChange([...drafts, emptyLinkDraft()])}
      >
        リンクを追加
      </button>
    </div>
  );
}
