import {
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type UIEvent,
} from "react";
import { createPortal } from "react-dom";
import {
  clampDay,
  daysInMonth,
  formatTokyoDateTimeLabel,
  pad2,
  tokyoDateTimeToWheels,
  tokyoYearOptions,
  wheelsToTokyoInput,
  type TokyoDateTimeWheels,
} from "./tokyoDateTime.ts";

const ITEM_H = 36;
const HOURS = Array.from({ length: 24 }, (_, index) => index);
const MINUTES = Array.from({ length: 60 }, (_, index) => index);
const MONTHS = Array.from({ length: 12 }, (_, index) => index + 1);

type Props = {
  id: string;
  legend: string;
  value: string;
  onChange: (next: string) => void;
  required?: boolean;
  error?: string;
};

type ColumnProps = {
  unit: string;
  values: number[];
  value: number;
  onChange: (next: number) => void;
};

function WheelColumn({ unit, values, value, onChange }: ColumnProps) {
  const scrollerRef = useRef<HTMLDivElement | null>(null);
  const skipScroll = useRef(false);
  const index = Math.max(0, values.indexOf(value));
  const valuesKey = `${values[0]}-${values[values.length - 1]}-${values.length}`;

  useEffect(() => {
    const el = scrollerRef.current;
    if (!el) return;
    skipScroll.current = true;
    el.scrollTop = index * ITEM_H;
    const timer = window.setTimeout(() => {
      skipScroll.current = false;
    }, 80);
    return () => window.clearTimeout(timer);
  }, [index, valuesKey]);

  const commit = (nextIndex: number) => {
    const clamped = Math.min(values.length - 1, Math.max(0, nextIndex));
    const next = values[clamped];
    if (next != null && next !== value) onChange(next);
  };

  const onScroll = (event: UIEvent<HTMLDivElement>) => {
    if (skipScroll.current) return;
    const nextIndex = Math.round(event.currentTarget.scrollTop / ITEM_H);
    commit(nextIndex);
  };

  const onKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (event.key === "ArrowUp") {
      event.preventDefault();
      commit(index - 1);
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      commit(index + 1);
    } else if (event.key === "Home") {
      event.preventDefault();
      commit(0);
    } else if (event.key === "End") {
      event.preventDefault();
      commit(values.length - 1);
    }
  };

  return (
    <div className="tokyo-wheel-col">
      <div className="tokyo-wheel-col__unit">{unit}</div>
      <div className="tokyo-wheel-col__viewport">
        <div className="tokyo-wheel-col__highlight" aria-hidden="true" />
        <div
          ref={scrollerRef}
          className="tokyo-wheel-col__scroller"
          role="listbox"
          aria-label={unit}
          tabIndex={0}
          onScroll={onScroll}
          onKeyDown={onKeyDown}
          onWheel={(event) => event.stopPropagation()}
          onTouchMove={(event) => event.stopPropagation()}
        >
          <div
            className="tokyo-wheel-col__spacer"
            style={{ height: ITEM_H * 2 }}
            aria-hidden="true"
          />
          {values.map((item) => (
            <button
              key={item}
              type="button"
              role="option"
              aria-selected={item === value}
              className={`tokyo-wheel-col__item${item === value ? " is-selected" : ""}`}
              style={{ height: ITEM_H }}
              onClick={() => onChange(item)}
            >
              {unit === "年" ? String(item) : pad2(item)}
            </button>
          ))}
          <div
            className="tokyo-wheel-col__spacer"
            style={{ height: ITEM_H * 2 }}
            aria-hidden="true"
          />
        </div>
      </div>
    </div>
  );
}

function DateTimeWheelDialog({
  title,
  value,
  onConfirm,
  onCancel,
}: {
  title: string;
  value: string;
  onConfirm: (next: string) => void;
  onCancel: () => void;
}) {
  const titleId = useId();
  const [draft, setDraft] = useState<TokyoDateTimeWheels>(() =>
    tokyoDateTimeToWheels(value)
  );
  const onConfirmRef = useRef(onConfirm);
  const onCancelRef = useRef(onCancel);
  onConfirmRef.current = onConfirm;
  onCancelRef.current = onCancel;
  const years = tokyoYearOptions(draft.year);
  const days = Array.from(
    { length: daysInMonth(draft.year, draft.month) },
    (_, index) => index + 1
  );

  useEffect(() => {
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onCancelRef.current();
      }
    };
    window.addEventListener("keydown", onKey);
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = previous;
    };
  }, []);

  const setPart = <K extends keyof TokyoDateTimeWheels>(
    key: K,
    next: TokyoDateTimeWheels[K]
  ) => {
    setDraft((current) => {
      const updated = { ...current, [key]: next };
      updated.day = clampDay(updated.year, updated.month, updated.day);
      return updated;
    });
  };

  return createPortal(
    <div className="tokyo-datetime-picker">
      <button
        type="button"
        className="tokyo-datetime-picker__backdrop"
        aria-label="閉じる"
        onClick={() => onCancelRef.current()}
      />
      <div
        className="tokyo-datetime-picker__panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
      >
        <h2 id={titleId} className="tokyo-datetime-picker__title">
          {title}
        </h2>
        <div className="tokyo-wheel" role="group" aria-label="年月日と時刻">
          <WheelColumn
            unit="年"
            values={years}
            value={draft.year}
            onChange={(next) => setPart("year", next)}
          />
          <WheelColumn
            unit="月"
            values={MONTHS}
            value={draft.month}
            onChange={(next) => setPart("month", next)}
          />
          <WheelColumn
            unit="日"
            values={days}
            value={draft.day}
            onChange={(next) => setPart("day", next)}
          />
          <WheelColumn
            unit="時"
            values={HOURS}
            value={draft.hour}
            onChange={(next) => setPart("hour", next)}
          />
          <WheelColumn
            unit="分"
            values={MINUTES}
            value={draft.minute}
            onChange={(next) => setPart("minute", next)}
          />
        </div>
        <div className="tokyo-datetime-picker__actions">
          <button
            type="button"
            className="tokyo-datetime-picker__cancel"
            onClick={() => onCancelRef.current()}
          >
            キャンセル
          </button>
          <button
            type="button"
            className="tokyo-datetime-picker__confirm"
            onClick={() => onConfirmRef.current(wheelsToTokyoInput(draft))}
          >
            決定
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
}

export function TokyoDateTimeFields({
  id,
  legend,
  value,
  onChange,
  required = false,
  error,
}: Props) {
  const [open, setOpen] = useState(false);
  const label = formatTokyoDateTimeLabel(value);
  const canClear = !required && Boolean(label);

  return (
    <fieldset className="form-group tokyo-datetime">
      <legend>{legend}</legend>
      <button
        type="button"
        id={id}
        className="tokyo-datetime__trigger"
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-required={required || undefined}
        onClick={() => setOpen(true)}
      >
        {label || "日時を選択"}
      </button>
      {canClear ? (
        <button
          type="button"
          className="tokyo-datetime__clear"
          onClick={() => onChange("")}
        >
          クリア
        </button>
      ) : null}
      {error ? <p className="org-edit-field-error">{error}</p> : null}
      {open ? (
        <DateTimeWheelDialog
          title={legend}
          value={value}
          onCancel={() => setOpen(false)}
          onConfirm={(next) => {
            onChange(next);
            setOpen(false);
          }}
        />
      ) : null}
    </fieldset>
  );
}
