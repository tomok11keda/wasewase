import { useEffect, useRef, useState } from "react";
import {
  REPORT_REASONS,
  submitContentReport,
} from "../timeline/api";

export type CommunityReportTarget = "community_thread" | "community_reply";

type Props = {
  targetType: CommunityReportTarget;
  targetId: number;
  canReport: boolean;
  ariaLabel?: string;
};

export function CommunityReportMenu({
  targetType,
  targetId,
  canReport,
  ariaLabel = "通報",
}: Props) {
  const [open, setOpen] = useState(false);
  const [choosing, setChoosing] = useState(false);
  const [busy, setBusy] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const onPointer = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
        setChoosing(false);
      }
    };
    document.addEventListener("mousedown", onPointer);
    return () => document.removeEventListener("mousedown", onPointer);
  }, [open]);

  if (!canReport) return null;

  return (
    <div className="community-overflow" ref={rootRef}>
      <button
        type="button"
        className="community-overflow__btn"
        aria-label={ariaLabel}
        aria-expanded={open}
        aria-haspopup="menu"
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          setOpen((v) => !v);
          setChoosing(false);
        }}
      >
        ⋯
      </button>
      {open ? (
        <div className="community-overflow__menu" role="menu">
          {choosing ? (
            <>
              <p className="community-overflow__heading">通報理由</p>
              {REPORT_REASONS.map((reason) => (
                <button
                  key={reason.value}
                  type="button"
                  className="community-overflow__item"
                  role="menuitem"
                  disabled={busy}
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    void (async () => {
                      setBusy(true);
                      try {
                        const message = await submitContentReport(
                          targetType,
                          targetId,
                          reason.value
                        );
                        setOpen(false);
                        setChoosing(false);
                        window.alert(message);
                      } catch (err) {
                        window.alert(
                          err instanceof Error
                            ? err.message
                            : "通報に失敗しました"
                        );
                      } finally {
                        setBusy(false);
                      }
                    })();
                  }}
                >
                  {reason.label}
                </button>
              ))}
              <button
                type="button"
                className="community-overflow__item community-overflow__item--muted"
                role="menuitem"
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  setChoosing(false);
                }}
              >
                キャンセル
              </button>
            </>
          ) : (
            <button
              type="button"
              className="community-overflow__item"
              role="menuitem"
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                setChoosing(true);
              }}
            >
              通報
            </button>
          )}
        </div>
      ) : null}
    </div>
  );
}
