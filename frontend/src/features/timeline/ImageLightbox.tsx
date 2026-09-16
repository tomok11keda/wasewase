import { useEffect, useId } from "react";
import { createPortal } from "react-dom";

type Props = {
  src: string;
  alt?: string;
  open: boolean;
  onClose: () => void;
};

export function ImageLightbox({ src, alt = "", open, onClose }: Props) {
  const titleId = useId();

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);

  if (!open) return null;

  return createPortal(
    <div className="image-lightbox" aria-hidden="false">
      <button
        type="button"
        className="image-lightbox__backdrop"
        aria-label="閉じる"
        onClick={onClose}
      />
      <button
        type="button"
        className="image-lightbox__close"
        aria-label="閉じる"
        onClick={onClose}
      >
        ×
      </button>
      <div
        className="image-lightbox__stage"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
      >
        <h2 id={titleId} className="visually-hidden">
          画像
        </h2>
        <img
          className="image-lightbox__img"
          src={src}
          alt={alt}
          onClick={(event) => event.stopPropagation()}
        />
      </div>
    </div>,
    document.body
  );
}
