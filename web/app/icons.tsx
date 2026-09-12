/* The icon set.
 *
 * Drawn inline rather than pulled from a package: the console needs nine
 * glyphs, and a dependency for nine glyphs costs a bundle, a version to
 * keep current, and a second visual language the moment someone reaches
 * for a tenth that happens to be styled differently.
 *
 * One family, one voice: 24x24 box, 1.5 stroke, round caps and joins,
 * currentColor throughout, no fills. That consistency is the whole reason
 * these read as a set - per icon-style-consistent and stroke-consistency.
 *
 * All of them are decorative. Every icon in this app sits beside text that
 * already says the same thing, so they carry aria-hidden and contribute
 * nothing to the accessibility tree. If one is ever used alone, it needs
 * an accessible name on the control around it, not a label here.
 */

type IconProps = {
  /** Pixel size of the square box. Defaults to 1em so it tracks font-size. */
  size?: number | string;
  className?: string;
};

function Svg({
  size = "1em",
  className,
  children,
}: IconProps & { children: React.ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      className={className}
    >
      {children}
    </svg>
  );
}

/** Résumé round - a document. */
export const IconDocument = (p: IconProps) => (
  <Svg {...p}>
    <path d="M14 3v5h5" />
    <path d="M19 8v11a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h7z" />
    <path d="M9 13h6M9 17h4" />
  </Svg>
);

/** Backend / SDE - a server stack. */
export const IconServer = (p: IconProps) => (
  <Svg {...p}>
    <rect x="3" y="4" width="18" height="6" rx="1.5" />
    <rect x="3" y="14" width="18" height="6" rx="1.5" />
    <path d="M7 7h.01M7 17h.01" />
  </Svg>
);

/** Computer fundamentals - a chip. */
export const IconChip = (p: IconProps) => (
  <Svg {...p}>
    <rect x="7" y="7" width="10" height="10" rx="1.5" />
    <path d="M10 3v4M14 3v4M10 17v4M14 17v4M3 10h4M3 14h4M17 10h4M17 14h4" />
  </Svg>
);

/** HLD - distributed boxes with links. */
export const IconNetwork = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="12" cy="5" r="2.5" />
    <circle cx="5" cy="18" r="2.5" />
    <circle cx="19" cy="18" r="2.5" />
    <path d="M10.4 7.1 6.6 15.9M13.6 7.1l3.8 8.8M7.5 18h9" />
  </Svg>
);

/** LLD - nested class boxes. */
export const IconBlocks = (p: IconProps) => (
  <Svg {...p}>
    <rect x="3" y="3" width="8" height="8" rx="1.5" />
    <rect x="13" y="3" width="8" height="8" rx="1.5" />
    <rect x="3" y="13" width="8" height="8" rx="1.5" />
    <rect x="13" y="13" width="8" height="8" rx="1.5" />
  </Svg>
);

/** AI engineer - a spark. */
export const IconSpark = (p: IconProps) => (
  <Svg {...p}>
    <path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z" />
    <path d="M18 16l.7 1.8L20.5 19l-1.8.7L18 21.5l-.7-1.8L15.5 19l1.8-.7z" />
  </Svg>
);

export const IconCheck = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 12.5l5 5L20 6.5" />
  </Svg>
);

export const IconCross = (p: IconProps) => (
  <Svg {...p}>
    <path d="M6 6l12 12M18 6L6 18" />
  </Svg>
);

export const IconMinus = (p: IconProps) => (
  <Svg {...p}>
    <path d="M5 12h14" />
  </Svg>
);

export const IconArrowRight = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 12h15M13 6l6 6-6 6" />
  </Svg>
);

export const IconArrowLeft = (p: IconProps) => (
  <Svg {...p}>
    <path d="M20 12H5M11 18l-6-6 6-6" />
  </Svg>
);

export const IconMic = (p: IconProps) => (
  <Svg {...p}>
    <rect x="9" y="3" width="6" height="11" rx="3" />
    <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
  </Svg>
);

export const IconSun = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
  </Svg>
);

export const IconMoon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M20 14.5A8.5 8.5 0 1 1 9.5 4a6.8 6.8 0 0 0 10.5 10.5z" />
  </Svg>
);

/** Which glyph fronts which round. Keyed by the backend's mode key, with
 * a document as the fallback so an unregistered mode still renders. */
const MODE_ICONS: Record<string, (p: IconProps) => React.JSX.Element> = {
  resume_projects: IconDocument,
  sde_backend: IconServer,
  computer_fundamentals: IconChip,
  system_design_hld: IconNetwork,
  system_design_lld: IconBlocks,
  ai_engineer: IconSpark,
};

/**
 * The glyph for a round, as a component rather than a lookup returning one.
 *
 * `const Glyph = modeIcon(key)` reads fine but hands React what it treats
 * as a freshly declared component on every render, which resets any state
 * inside it and is what the react-hooks rule flags. Doing the lookup in
 * here keeps the component identity stable.
 */
export function ModeIcon({ mode, ...rest }: IconProps & { mode: string }) {
  const Glyph = MODE_ICONS[mode] ?? IconDocument;
  return <Glyph {...rest} />;
}
