import { Link } from "react-router-dom";
import { followListPath } from "./followLists";
import {
  formatMutualFriendsLabel,
  type MutualFriendsPreview,
} from "./mutualFriends";

export function MutualFriendsRow({
  userId,
  preview,
}: {
  userId: number;
  preview: MutualFriendsPreview;
}) {
  if (preview.count < 1) return null;
  const label = formatMutualFriendsLabel(preview);
  return (
    <Link
      className="mutual-friends"
      to={followListPath(userId, "mutuals")}
      aria-label={label}
    >
      {preview.users.length > 0 ? (
        <span className="mutual-friends__avatars" aria-hidden="true">
          {preview.users.slice(0, 3).map((user) =>
            user.avatar_url ? (
              <img
                key={user.id}
                className="mutual-friends__avatar"
                src={user.avatar_url}
                alt=""
              />
            ) : (
              <span
                key={user.id}
                className="mutual-friends__avatar is-initial"
              >
                {user.initial || "?"}
              </span>
            )
          )}
        </span>
      ) : null}
      <span className="mutual-friends__label">{label}</span>
    </Link>
  );
}
