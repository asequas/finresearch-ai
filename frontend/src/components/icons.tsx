import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function Icon({ size = 16, children, ...props }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false" {...props}>
      {children}
    </svg>
  );
}

export const OverviewIcon = (p: IconProps) => (
  <Icon {...p}><path d="M4 13h6V4H4zM14 20h6v-9h-6zM4 20h6v-3H4zM14 7h6V4h-6z" /></Icon>
);
export const ResearchIcon = (p: IconProps) => (
  <Icon {...p}><circle cx="10.5" cy="10.5" r="6" /><path d="m15 15 5 5M10.5 8v5M8 10.5h5" /></Icon>
);
export const ReportIcon = (p: IconProps) => (
  <Icon {...p}><path d="M6 3h9l4 4v14H6z" /><path d="M14 3v5h5M9 12h7M9 16h4" /></Icon>
);
export const CompanyIcon = (p: IconProps) => (
  <Icon {...p}><path d="M4 21V5l8-2v18M12 8l8 3v10M3 21h18M7 8h2M7 12h2M7 16h2M15 14h2M15 18h2" /></Icon>
);
export const SettingsIcon = (p: IconProps) => (
  <Icon {...p}><path d="M4 7h10M18 7h2M4 17h4M12 17h8" /><circle cx="16" cy="7" r="2" /><circle cx="10" cy="17" r="2" /></Icon>
);
export const ExternalIcon = (p: IconProps) => (
  <Icon size={12} {...p}><path d="M14 4h6v6M20 4l-9 9M18 14v6H4V6h6" /></Icon>
);
export const CloseIcon = (p: IconProps) => (
  <Icon {...p}><path d="M6 6l12 12M18 6 6 18" /></Icon>
);
export const ChevronIcon = (p: IconProps) => (
  <Icon size={14} {...p}><path d="m9 6 6 6-6 6" /></Icon>
);
export const CheckIcon = (p: IconProps) => (
  <Icon size={14} {...p}><path d="m5 12 4 4 10-10" /></Icon>
);
export const CrossIcon = (p: IconProps) => (
  <Icon size={14} {...p}><path d="M7 7l10 10M17 7 7 17" /></Icon>
);
export const DownloadIcon = (p: IconProps) => (
  <Icon size={14} {...p}><path d="M12 4v11M7 10l5 5 5-5M5 20h14" /></Icon>
);
export const PrintIcon = (p: IconProps) => (
  <Icon size={14} {...p}><path d="M7 9V3h10v6M7 17H4v-7h16v7h-3M7 14h10v7H7z" /></Icon>
);

/** Product mark: a filing whose last line is the checked one. */
export function Mark({ size = 24 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="3.5" y="2.5" width="17" height="19" rx="2" stroke="var(--muted)" strokeWidth="1.5" />
      <path d="M7.5 8h9M7.5 12h9" stroke="var(--muted)" strokeWidth="1.5" strokeLinecap="round" />
      <path d="M7.5 16h5" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" />
      <circle cx="16" cy="16" r="1.4" fill="var(--accent)" />
    </svg>
  );
}
export const SearchIcon = (p: IconProps) => (
  <Icon {...p}><circle cx="11" cy="11" r="6.5" /><path d="m16 16 4.5 4.5" /></Icon>
);
