export type ReplyTarget = {
  id: number;
  senderName: string;
  preview: string;
};

type Props = {
  reply: ReplyTarget;
  onClear: () => void;
};

export function ChatReplyPreview({ reply, onClear }: Props) {
  return (
    <div className="chat-reply-preview" role="status">
      <div className="chat-reply-preview__body">
        <span className="chat-reply-preview__label">返信先</span>
        <strong className="chat-reply-preview__name">{reply.senderName}</strong>
        <span className="chat-reply-preview__text">「{reply.preview}」</span>
      </div>
      <button
        type="button"
        className="chat-reply-preview__clear"
        aria-label="返信を解除"
        onClick={onClear}
      >
        ×
      </button>
    </div>
  );
}
