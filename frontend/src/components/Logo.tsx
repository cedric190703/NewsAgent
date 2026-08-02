import { cn } from "../lib/utils";

export function Logo({ size = 36, className }: { size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 40 40"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={cn("flex-shrink-0", className)}
    >
      {/* Rounded square background */}
      <rect width="40" height="40" rx="10" fill="#0F172A" />
      {/* Stylized "N" with a folded-paper / newsletter feel */}
      <path
        d="M11 28V12.5C11 12.2 11.2 12 11.5 12H13.5C13.7 12 13.9 12.1 14 12.3L23 24.5V12.5C23 12.2 23.2 12 23.5 12H25.5C25.8 12 26 12.2 26 12.5V28C26 28.3 25.8 28.5 25.5 28.5H23.5C23.3 28.5 23.1 28.4 23 28.2L14 16V28C14 28.3 13.8 28.5 13.5 28.5H11.5C11.2 28.5 11 28.3 11 28Z"
        fill="white"
      />
      {/* Accent dot — the "signal" */}
      <circle cx="30" cy="14" r="3" fill="#3B82F6" />
    </svg>
  );
}

export function LogoDark({ size = 36, className }: { size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 40 40"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={cn("flex-shrink-0", className)}
    >
      <rect width="40" height="40" rx="10" fill="white" />
      <path
        d="M11 28V12.5C11 12.2 11.2 12 11.5 12H13.5C13.7 12 13.9 12.1 14 12.3L23 24.5V12.5C23 12.2 23.2 12 23.5 12H25.5C25.8 12 26 12.2 26 12.5V28C26 28.3 25.8 28.5 25.5 28.5H23.5C23.3 28.5 23.1 28.4 23 28.2L14 16V28C14 28.3 13.8 28.5 13.5 28.5H11.5C11.2 28.5 11 28.3 11 28Z"
        fill="#0F172A"
      />
      <circle cx="30" cy="14" r="3" fill="#3B82F6" />
    </svg>
  );
}
