import { useEffect, useState, type FormEvent } from "react";

type Props = {
  value: string;
  onSubmit: (query: string) => void;
  onClear?: () => void;
  placeholder: string;
  ariaLabel: string;
  /** Compact inline bar for page-local search (not the global search tab). */
  compact?: boolean;
};

/**
 * Reusable local search form for timeline / communities (and similar).
 * Does not perform navigation by itself — parent decides scope.
 */
export function LocalSearchBar({
  value,
  onSubmit,
  onClear,
  placeholder,
  ariaLabel,
  compact = true,
}: Props) {
  const [input, setInput] = useState(value);

  useEffect(() => {
    setInput(value);
  }, [value]);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    onSubmit(input.trim());
  };

  return (
    <form
      className={`local-search${compact ? " local-search--compact" : ""}`}
      onSubmit={submit}
      role="search"
    >
      <input
        value={input}
        onChange={(e) => setInput(e.target.value)}
        placeholder={placeholder}
        aria-label={ariaLabel}
      />
      <button type="submit">検索</button>
      {value && onClear ? (
        <button
          type="button"
          className="local-search__clear"
          onClick={onClear}
        >
          解除
        </button>
      ) : null}
    </form>
  );
}
