import { useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import "./Chat.css";

interface ComposerProps {
  disabled: boolean;
  onSend: (content: string) => void;
}

const MAX_LENGTH = 8000; // PostMessageRequest.content maxLength, contracts/openapi.yaml

export function Composer({ disabled, onSend }: ComposerProps) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const submit = () => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
    textareaRef.current?.focus();
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    submit();
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <form className="composer" onSubmit={handleSubmit}>
      <label htmlFor="composer-input" className="sr-only">
        Message
      </label>
      <textarea
        id="composer-input"
        ref={textareaRef}
        className="composer__input"
        value={value}
        maxLength={MAX_LENGTH}
        placeholder="Ask a grounded question, request a Ship 30 essay, or generate an artifact…"
        disabled={disabled}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        rows={1}
      />
      <button type="submit" className="composer__send" disabled={disabled || !value.trim()}>
        {disabled ? "Sending…" : "Send"}
      </button>
    </form>
  );
}
