type Props = {
  label: string;
};

export function ChatDateDivider({ label }: Props) {
  return (
    <li className="chat-day">
      <time className="chat-day__label">{label}</time>
    </li>
  );
}
