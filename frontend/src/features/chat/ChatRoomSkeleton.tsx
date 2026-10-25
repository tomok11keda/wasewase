import { SkeletonBone, SkeletonCircle } from "../../components/skeleton";
import { ChatRoomHeader } from "./ChatRoomHeader";
import type { ChatHeaderPreview } from "./inboxRoomPreview";

/** A handful of placeholder bubbles — not a reconstructed history. */
export const CHAT_SKELETON_BUBBLE_COUNT = 6;

const BUBBLES: { mine: boolean; width: string }[] = [
  { mine: false, width: "56%" },
  { mine: true, width: "42%" },
  { mine: false, width: "68%" },
  { mine: false, width: "34%" },
  { mine: true, width: "52%" },
  { mine: true, width: "26%" },
];

export function ChatHeaderSkeleton({
  backTo,
  backLabel = "戻る",
  avatarShape = "circle",
  preview,
}: {
  backTo: string;
  backLabel?: string;
  avatarShape?: "circle" | "rounded";
  preview?: ChatHeaderPreview | null;
}) {
  return (
    <ChatRoomHeader
      backTo={backTo}
      backLabel={backLabel}
      title={preview?.title || ""}
      subtitle={preview?.subtitle}
      avatarUrl={preview?.avatarUrl}
      avatarInitial={preview?.avatarInitial}
      avatarShape={preview?.avatarShape || avatarShape}
      pending
    />
  );
}

export function ChatMessageSkeleton({
  mine,
  width,
}: {
  mine?: boolean;
  width?: string;
}) {
  return (
    <li
      className={`chat-row sk-chat-row${mine ? " is-mine" : ""}`}
      aria-hidden="true"
    >
      {!mine ? <SkeletonCircle size={28} className="chat-row__avatar" /> : null}
      <SkeletonBone
        className={`sk-chat-bubble${mine ? " is-mine" : ""}`}
        width={width || "52%"}
      />
    </li>
  );
}

export function ChatThreadSkeleton() {
  return (
    <div className="dm-message-area sk-chat-thread" aria-busy="true" aria-label="読み込み中">
      <ul className="message-list sk-chat-list">
        {BUBBLES.map((bubble, index) => (
          <ChatMessageSkeleton
            key={index}
            mine={bubble.mine}
            width={bubble.width}
          />
        ))}
      </ul>
    </div>
  );
}

export function ChatComposeSkeleton({
  allowMedia = true,
}: {
  allowMedia?: boolean;
}) {
  return (
    <div
      className="chat-compose-bar chat-compose-bar--disabled"
      aria-busy="true"
      aria-disabled="true"
      aria-label="読み込み中"
    >
      <div className="chat-compose-bar__row">
        {allowMedia ? (
          <div className="chat-compose-bar__media" aria-hidden="true">
            <SkeletonCircle size={22} />
            <SkeletonCircle size={22} />
          </div>
        ) : null}
        <SkeletonBone className="sk-chat-input" />
      </div>
    </div>
  );
}

export function ChatLoadError({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <div className="dm-message-area">
      <p className="empty-message">{message}</p>
      <p>
        <button
          type="button"
          className="btn btn-secondary"
          onClick={onRetry}
        >
          再試行
        </button>
      </p>
    </div>
  );
}
