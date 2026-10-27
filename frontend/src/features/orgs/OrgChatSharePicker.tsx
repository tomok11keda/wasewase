import { useEffect, useState } from "react";
import { envelopeChats, type RecruitingChat } from "./recruitingChat";
import { fetchRecruitingChat } from "./recruitingChatApi";

type Props = {
  slug: string;
  busy?: boolean;
  submitLabel: string;
  onShare: (chatIds: number[]) => void | Promise<void>;
};

export function OrgChatSharePicker({
  slug,
  busy = false,
  submitLabel,
  onShare,
}: Props) {
  const [chats, setChats] = useState<RecruitingChat[]>([]);
  const [selected, setSelected] = useState<number[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    void fetchRecruitingChat(slug)
      .then((envelope) => {
        if (cancelled) return;
        const rows = envelopeChats(envelope).filter(
          (chat) => chat.is_active !== false && chat.id
        );
        setChats(rows);
        setSelected(rows.length === 1 && rows[0].id ? [rows[0].id] : []);
      })
      .catch(() => {
        if (cancelled) return;
        setError("団体チャットを読み込めませんでした。");
        setChats([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [slug]);

  const toggle = (id: number) => {
    setSelected((prev) =>
      prev.includes(id) ? prev.filter((row) => row !== id) : [...prev, id]
    );
  };

  if (loading) {
    return <p className="org-recruiting-card__lead">団体チャットを読み込み中…</p>;
  }
  if (error) {
    return <p className="org-edit-error" role="alert">{error}</p>;
  }
  if (!chats.length) {
    return (
      <p className="org-recruiting-card__lead">
        共有できる団体チャットがありません。先にチャットを作成してください。
      </p>
    );
  }

  return (
    <div className="org-chat-share-picker">
      <p className="org-recruiting-card__lead">共有する団体チャット</p>
      <ul className="org-recruiting-card__meta">
        {chats.map((chat) => {
          const id = chat.id as number;
          return (
            <li key={id}>
              <label>
                <input
                  type="checkbox"
                  checked={selected.includes(id)}
                  onChange={() => toggle(id)}
                  disabled={busy}
                />{" "}
                {chat.name || "団体チャット"}
                {chat.visibility === "private" ? "（非公開）" : ""}
              </label>
            </li>
          );
        })}
      </ul>
      <button
        type="button"
        className="btn btn-primary"
        disabled={busy || selected.length === 0}
        onClick={() => void onShare(selected)}
      >
        {busy ? "送信中…" : submitLabel}
      </button>
    </div>
  );
}
