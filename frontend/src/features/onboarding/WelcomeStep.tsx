type Props = {
  onDone: () => void;
  busy: boolean;
};

export function WelcomeStep({ onDone, busy }: Props) {
  return (
    <>
      <h1>WaseWaseへようこそ</h1>
      <p className="hint">準備ができました。タイムラインを見てみましょう。</p>
      <button type="button" className="btn" disabled={busy} onClick={onDone}>
        WaseWaseをはじめる
      </button>
    </>
  );
}
