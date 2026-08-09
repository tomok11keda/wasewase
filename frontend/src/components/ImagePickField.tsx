import { useEffect, useMemo, useRef, type ChangeEvent } from "react";
import { SfIcon } from "./SfIcon";

type Props = {
  id?: string;
  value: File | null;
  onChange: (file: File | null) => void;
  disabled?: boolean;
  /** Optional hint under the action buttons */
  hint?: string;
  /** Show clear control when a file is selected (default true) */
  allowClear?: boolean;
};

/**
 * Mobile-friendly image picker: camera vs library.
 * Keeps native file inputs (hidden) so Capacitor / browser pickers still work.
 */
export function ImagePickField({
  id,
  value,
  onChange,
  disabled = false,
  hint,
  allowClear = true,
}: Props) {
  const cameraRef = useRef<HTMLInputElement | null>(null);
  const libraryRef = useRef<HTMLInputElement | null>(null);
  const previewUrl = useMemo(
    () => (value ? URL.createObjectURL(value) : null),
    [value]
  );

  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  const onFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] || null;
    onChange(file);
    // Allow selecting the same file again after clear
    e.target.value = "";
  };

  return (
    <div className="image-pick" id={id ? `${id}-wrap` : undefined}>
      <input
        ref={cameraRef}
        id={id ? `${id}-camera` : undefined}
        type="file"
        accept="image/*"
        capture="environment"
        data-image-source="camera"
        className="image-pick__native"
        disabled={disabled}
        tabIndex={-1}
        aria-hidden="true"
        onChange={onFileChange}
      />
      <input
        ref={libraryRef}
        id={id}
        type="file"
        accept="image/*"
        data-image-source="photos"
        className="image-pick__native"
        disabled={disabled}
        tabIndex={-1}
        aria-hidden="true"
        onChange={onFileChange}
      />

      <div className="image-pick__actions" role="group" aria-label="画像を追加">
        <button
          type="button"
          className="image-pick__btn"
          disabled={disabled}
          onClick={() => cameraRef.current?.click()}
        >
          <span className="image-pick__btn-icon" aria-hidden="true">
            <SfIcon name="camera" size={22} />
          </span>
          <span className="image-pick__btn-label">写真を撮る</span>
        </button>
        <button
          type="button"
          className="image-pick__btn"
          disabled={disabled}
          onClick={() => libraryRef.current?.click()}
        >
          <span className="image-pick__btn-icon" aria-hidden="true">
            <SfIcon name="photo" size={22} />
          </span>
          <span className="image-pick__btn-label">写真を選ぶ</span>
        </button>
      </div>

      {hint ? <p className="image-pick__hint">{hint}</p> : null}

      {value ? (
        <div className="image-pick__preview">
          {previewUrl ? (
            <img
              className="image-pick__thumb"
              src={previewUrl}
              alt="選択中の画像プレビュー"
            />
          ) : null}
          <div className="image-pick__meta">
            <p className="image-pick__filename">{value.name}</p>
            {allowClear ? (
              <button
                type="button"
                className="image-pick__clear"
                disabled={disabled}
                onClick={() => onChange(null)}
              >
                削除
              </button>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
