// The Spendie mark: a rounded tile, a bold S wearing sunglasses, two sparkles.
//
// Drawn as inline SVG rather than shipped as an image so it stays crisp at any
// size, inherits no network request, and can drop its detail when small — the
// sunglasses and sparkles disappear below about 28px, where they would only
// read as mud.

export const BRAND = {
  blue: '#556ff8',
  navy: '#0f1e52',
  tint: '#d3e6fd',
};

export default function Logo({ size = 34, detail = true, tile = true }) {
  const showDetail = detail && size >= 28;

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 120 120"
      role="img"
      aria-label="Spendie"
      focusable="false"
    >
      {tile && (
        <rect x="0" y="0" width="120" height="120" rx="30" fill={BRAND.tint} />
      )}

      {/* The S. Stroked with round caps so the terminals stay soft. */}
      <path
        d="M78 40
           C78 31, 69 25, 58 25
           C45 25, 36 32, 36 42
           C36 53, 47 57, 60 60
           C73 63, 84 68, 84 79
           C84 90, 74 96, 61 96
           C49 96, 40 91, 38 83"
        fill="none"
        stroke={BRAND.blue}
        strokeWidth="21"
        strokeLinecap="round"
        strokeLinejoin="round"
      />

      {showDetail && (
        <>
          {/* Sunglasses: two lenses and a bridge, sitting across the upper curve. */}
          <g fill={BRAND.navy}>
            <path d="M40 44
                     C40 39, 45 37, 51 38
                     C57 39, 59 43, 56 48
                     C53 53, 47 54, 43 51
                     C41 49, 40 46, 40 44 Z" />
            <path d="M63 40
                     C63 35, 68 33, 74 34
                     C80 35, 82 39, 79 44
                     C76 49, 70 50, 66 47
                     C64 45, 63 42, 63 40 Z" />
            <rect x="55" y="39" width="9" height="5" rx="2.5" />
          </g>
          {/* Highlights, so the lenses read as glass rather than holes. */}
          <g fill="#ffffff" opacity=".9">
            <path d="M45 42 C47 40, 50 40, 51 41 L47 47 C45 46, 44 44, 45 42 Z" />
            <path d="M68 38 C70 36, 73 36, 74 37 L70 43 C68 42, 67 40, 68 38 Z" />
          </g>

          {/* Two four-pointed sparkles, top right. */}
          <g fill={BRAND.blue}>
            <path d="M93 18 C95 26, 97 28, 105 30 C97 32, 95 34, 93 42
                     C91 34, 89 32, 81 30 C89 28, 91 26, 93 18 Z" />
            <path d="M107 40 C108.5 45, 110 46.5, 115 48 C110 49.5, 108.5 51, 107 56
                     C105.5 51, 104 49.5, 99 48 C104 46.5, 105.5 45, 107 40 Z" />
          </g>
        </>
      )}
    </svg>
  );
}
