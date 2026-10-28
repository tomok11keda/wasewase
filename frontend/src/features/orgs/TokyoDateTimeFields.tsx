import { useEffect, useState } from "react";
import {
  joinTokyoDateTime,
  normalizeTokyoTime,
  splitTokyoDateTime,
  tokyoTimeInputStep,
} from "./tokyoDateTime.ts";

type Props = {
  id: string;
  legend: string;
  value: string;
  onChange: (next: string) => void;
  required?: boolean;
  error?: string;
  dateLabel?: string;
  timeLabel?: string;
};

export function TokyoDateTimeFields({
  id,
  legend,
  value,
  onChange,
  required = false,
  error,
  dateLabel = "日付",
  timeLabel = "時刻",
}: Props) {
  const parsed = splitTokyoDateTime(value);
  const [date, setDate] = useState(parsed.date);
  const [time, setTime] = useState(parsed.time);

  useEffect(() => {
    const next = splitTokyoDateTime(value);
    if (!value) {
      setDate("");
      setTime("");
      return;
    }
    if (next.date && next.time) {
      setDate(next.date);
      setTime(next.time);
      return;
    }
    if (next.date) setDate(next.date);
  }, [value]);

  const emit = (nextDate: string, nextTime: string) => {
    setDate(nextDate);
    setTime(nextTime);
    onChange(joinTokyoDateTime(nextDate, nextTime));
  };

  return (
    <fieldset className="form-group tokyo-datetime">
      <legend>{legend}</legend>
      <div className="tokyo-datetime__fields">
        <div className="tokyo-datetime__field">
          <label htmlFor={`${id}-date`}>{dateLabel}</label>
          <input
            id={`${id}-date`}
            type="date"
            value={date}
            required={required}
            autoComplete="off"
            onChange={(event) => emit(event.target.value, time)}
          />
        </div>
        <div className="tokyo-datetime__field">
          <label htmlFor={`${id}-time`}>{timeLabel}</label>
          <input
            id={`${id}-time`}
            type="time"
            value={time}
            required={required}
            step={tokyoTimeInputStep(time)}
            autoComplete="off"
            onChange={(event) =>
              emit(date, normalizeTokyoTime(event.target.value) || event.target.value)
            }
          />
        </div>
      </div>
      {error ? <p className="org-edit-field-error">{error}</p> : null}
    </fieldset>
  );
}
