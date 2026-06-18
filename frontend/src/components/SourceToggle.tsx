import { Check } from "lucide-react";

import type { SourceType } from "../services/api";

interface SourceToggleProps {
  label: string;
  value: SourceType;
  selected: boolean;
  onChange: (value: SourceType) => void;
}

export function SourceToggle({ label, value, selected, onChange }: SourceToggleProps) {
  return (
    <button
      className={`source-toggle ${selected ? "is-selected" : ""}`}
      type="button"
      onClick={() => onChange(value)}
      aria-pressed={selected}
    >
      <span className="source-toggle__icon">{selected ? <Check size={14} /> : null}</span>
      {label}
    </button>
  );
}
