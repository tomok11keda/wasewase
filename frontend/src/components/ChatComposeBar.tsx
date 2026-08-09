import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type FormEvent,
} from "react";
import { SfIcon } from "./SfIcon";
import { isNativeCapacitorApp } from "../lib/nativeApp";

type Props = {
  value: string;
  onChange: (value: string) => void;
  onSend: (e: FormEvent) => void | Promise<void>;
  disabled?: boolean;
  busy?: boolean;
  placeholder?: string;
  maxLength?: number;
  className?: string;
};

/**
 * DM / group / trade compose row:
 * left: camera + photo library (always)
 * center: text input
 * right: send (only when text is non-empty)
 *
 * Native: data-image-pick-source buttons → capacitor_native.js CAMERA/PHOTOS.
 * Web: hidden file inputs (capture vs library).
 */
export function ChatComposeBar({
  value,
  onChange,
  onSend,
  disabled = false,
  busy = false,
  placeholder = "メッセージを入力...",
  maxLength = 500,
  className = "",
}: Props) {
  const cameraRef = useRef<HTMLInputElement | null>(null);
  const libraryRef = useRef<HTMLInputElement | null>(null);
  const [pendingImage, setPendingImage] = useState<File | null>(null);
  const [imageNote, setImageNote] = useState<string | null>(null);

  const hasText = value.trim().length > 0;

  const previewUrl = useMemo(
    () => (pendingImage ? URL.createObjectURL(pendingImage) : null),
    [pendingImage]
  );

  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  const onFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] || null;
    setPendingImage(file);
    setImageNote(null);
    e.target.value = "";
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (disabled || busy) return;
    if (!hasText && pendingImage) {
      setImageNote(
        "画像送信は現在準備中です。テキストを入力して送信するか、プレビューを削除してください。"
      );
      return;
    }
    if (!hasText) return;
    setPendingImage(null);
    setImageNote(null);
    await onSend(e);
  };

  return (
    <form
      className={`chat-compose-bar image-pick${className ? ` ${className}` : ""}${
        disabled ? " chat-compose-bar--disabled" : ""
      }`}
      onSubmit={(e) => void handleSubmit(e)}
      aria-disabled={disabled}
    >
      <input
        ref={cameraRef}
        type="file"
        accept="image/*"
        capture="environment"
        data-image-source="camera"
        className="image-pick__native"
        disabled={disabled || busy}
        tabIndex={-1}
        aria-hidden="true"
        onChange={onFileChange}
      />
      <input
        ref={libraryRef}
        type="file"
        accept="image/*"
        data-image-source="photos"
        className="image-pick__native"
        disabled={disabled || busy}
        tabIndex={-1}
        aria-hidden="true"
        onChange={onFileChange}
      />

      {pendingImage ? (
        <div className="chat-compose-bar__preview">
          {previewUrl ? (
            <img
              className="chat-compose-bar__thumb"
              src={previewUrl}
              alt="選択中の画像プレビュー"
            />
          ) : null}
          <div className="chat-compose-bar__preview-meta">
            <span className="chat-compose-bar__filename">
              {pendingImage.name || "画像"}
            </span>
            <button
              type="button"
              className="chat-compose-bar__clear"
              disabled={disabled || busy}
              onClick={() => {
                setPendingImage(null);
                setImageNote(null);
              }}
            >
              削除
            </button>
          </div>
        </div>
      ) : null}

      {imageNote ? (
        <p className="chat-compose-bar__note" role="status">
          {imageNote}
        </p>
      ) : null}

      <div className="chat-compose-bar__row">
        <div
          className="chat-compose-bar__media"
          role="group"
          aria-label="メディアを追加"
        >
          <button
            type="button"
            className="chat-compose-bar__icon-btn"
            data-image-pick-source="camera"
            disabled={disabled || busy}
            aria-label="カメラで撮影"
            title="カメラで撮影"
            onClick={() => {
              if (isNativeCapacitorApp()) return;
              cameraRef.current?.click();
            }}
          >
            <SfIcon name="camera" size={22} />
          </button>
          <button
            type="button"
            className="chat-compose-bar__icon-btn"
            data-image-pick-source="photos"
            disabled={disabled || busy}
            aria-label="写真ライブラリから選ぶ"
            title="写真ライブラリから選ぶ"
            onClick={() => {
              if (isNativeCapacitorApp()) return;
              libraryRef.current?.click();
            }}
          >
            <SfIcon name="photo" size={22} />
          </button>
        </div>

        <input
          className="chat-compose-bar__input"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          maxLength={maxLength}
          placeholder={placeholder}
          disabled={disabled || busy}
          autoComplete="off"
          enterKeyHint="send"
          aria-label="メッセージ"
        />

        {hasText ? (
          <button
            type="submit"
            className="chat-compose-bar__icon-btn chat-compose-bar__send"
            disabled={disabled || busy}
            aria-label="送信"
            title="送信"
          >
            <SfIcon name="paperplane" size={22} />
          </button>
        ) : null}
      </div>
    </form>
  );
}
