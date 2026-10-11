// Pearl design tokens · generated from Figma 'Pearl Design System' (THL-106) · 2026-10-11 (v3: aligned with Handoff File; filled-secondary tokens removed). Do not edit by hand; re-export from Figma.

export const color = {
  light: {
      "surfacePage": "#fbf8f6",
      "surfaceCard": "#ffffff",
      "surfaceTrack": "#f1e9ee",
      "borderSubtle": "#eedfe6",
      "textPrimary": "#1c1a33",
      "textMuted": "#686580",
      "textOnNacre": "#1c1a33",
      "textOnAction": "#ffffff",
      "textLink": "#b8285a",
      "textPositive": "#12736b",
      "textCaution": "#8a5a12",
      "actionPrimary": "#b8285a",
      "brandRose": "#e2557f",
      "brandLagoon": "#4fd1c5",
      "brandLilac": "#e3d4ff",
      "brandSeaglass": "#cff3ee",
      "brandChampagne": "#f3d9a4",
      "brandBlush": "#ffe4ec",
      "borderStrong": "#8a87a3",
      "borderFocus": "#b8285a",
      "textDisabled": "#b4b1cc",
      "surfaceDisabled": "#f1e9ee",
      "surfaceScrim": "rgba(28, 26, 51, 0.40)",
      "borderError": "#e2557f"
  },
  dark: {
      "surfacePage": "#0b1030",
      "surfaceCard": "#151b44",
      "surfaceTrack": "#252c5e",
      "borderSubtle": "#252c5e",
      "textPrimary": "#fbf8f6",
      "textMuted": "#b4b1cc",
      "textOnNacre": "#1c1a33",
      "textOnAction": "#1c1a33",
      "textLink": "#ff8fb1",
      "textPositive": "#4fd1c5",
      "textCaution": "#f3d9a4",
      "actionPrimary": "#ff8fb1",
      "brandRose": "#e2557f",
      "brandLagoon": "#4fd1c5",
      "brandLilac": "#e3d4ff",
      "brandSeaglass": "#cff3ee",
      "brandChampagne": "#f3d9a4",
      "brandBlush": "#ffe4ec",
      "borderStrong": "#8a87a3",
      "borderFocus": "#ff8fb1",
      "textDisabled": "#686580",
      "surfaceDisabled": "#252c5e",
      "surfaceScrim": "rgba(0, 0, 0, 0.60)",
      "borderError": "#e2557f"
  },
} as const;

export type ColorToken = keyof typeof color.light;

export const space = {"1": 4, "2": 8, "3": 12, "4": 16, "5": 20, "6": 24, "8": 32} as const;
export const radius = {"sm": 12, "md": 20, "lg": 28, "full": 999} as const;

export const type = {
  "displayAmount": {
    "fontFamily": "Fraunces-SemiBold",
    "fontWeight": "600",
    "fontSize": 44,
    "lineHeight": 50,
    "letterSpacing": -0.88
  },
  "displayHeading1": {
    "fontFamily": "Fraunces-SemiBold",
    "fontWeight": "600",
    "fontSize": 30,
    "lineHeight": 36,
    "letterSpacing": -0.3
  },
  "displayHeading2": {
    "fontFamily": "Fraunces-SemiBold",
    "fontWeight": "600",
    "fontSize": 24,
    "lineHeight": 30,
    "letterSpacing": -0.24
  },
  "displayHeading3": {
    "fontFamily": "Fraunces-SemiBold",
    "fontWeight": "600",
    "fontSize": 18,
    "lineHeight": 24,
    "letterSpacing": 0.0
  },
  "displayWordmark": {
    "fontFamily": "Fraunces-SemiBold",
    "fontWeight": "600",
    "fontSize": 30,
    "lineHeight": 34,
    "letterSpacing": -0.6
  },
  "textBodyLarge": {
    "fontFamily": "Figtree-Regular",
    "fontWeight": "400",
    "fontSize": 16,
    "lineHeight": 24,
    "letterSpacing": 0.0
  },
  "textBody": {
    "fontFamily": "Figtree-Medium",
    "fontWeight": "500",
    "fontSize": 15,
    "lineHeight": 22,
    "letterSpacing": 0.0
  },
  "textButton": {
    "fontFamily": "Figtree-SemiBold",
    "fontWeight": "600",
    "fontSize": 16,
    "lineHeight": 20,
    "letterSpacing": 0.0
  },
  "textLabel": {
    "fontFamily": "Figtree-Medium",
    "fontWeight": "500",
    "fontSize": 13,
    "lineHeight": 18,
    "letterSpacing": 0.0
  },
  "textOverline": {
    "fontFamily": "Figtree-SemiBold",
    "fontWeight": "600",
    "fontSize": 12,
    "lineHeight": 16,
    "letterSpacing": 1.44,
    "textTransform": "uppercase"
  },
  "textTab": {
    "fontFamily": "Figtree-SemiBold",
    "fontWeight": "600",
    "fontSize": 11,
    "lineHeight": 14,
    "letterSpacing": 0.0
  }
} as const;

// iOS uses the larger of each style's two Figma shadows; Android uses elevation.
export const shadow = {
  "glowPearl": {
    "shadowColor": "#e2557f",
    "shadowOffset": {
      "width": 0,
      "height": 6
    },
    "shadowOpacity": 0.28,
    "shadowRadius": 12.0,
    "elevation": 4
  },
  "shadowCard": {
    "shadowColor": "#1c1a33",
    "shadowOffset": {
      "width": 0,
      "height": 8
    },
    "shadowOpacity": 0.07,
    "shadowRadius": 12.0,
    "elevation": 2
  },
  "shadowRaised": {
    "shadowColor": "#1c1a33",
    "shadowOffset": {
      "width": 0,
      "height": 12
    },
    "shadowOpacity": 0.1,
    "shadowRadius": 16.0,
    "elevation": 6
  },
  "shadowSheet": {
    "shadowColor": "#1c1a33",
    "shadowOffset": {
      "width": 0,
      "height": -8
    },
    "shadowOpacity": 0.14,
    "shadowRadius": 16.0,
    "elevation": 12
  }
} as const;

export const gradient = {
  "nacreDiagonal": {
    "type": "linear",
    "colors": [
      "#ffd6e0",
      "#e3d4ff",
      "#cff3ee"
    ],
    "locations": [
      0,
      0.5,
      1
    ]
  },
  "nacreHorizontal": {
    "type": "linear",
    "colors": [
      "#ffc2d4",
      "#d9c6ff",
      "#b8ede6"
    ],
    "locations": [
      0,
      0.5,
      1
    ]
  },
  "roseShell": {
    "type": "linear",
    "colors": [
      "#ff8fb1",
      "#e2557f"
    ],
    "locations": [
      0,
      1
    ]
  },
  "pearlOrb": {
    "type": "radial",
    "colors": [
      "#ffffff",
      "#fce8f0",
      "#dccbff"
    ],
    "locations": [
      0,
      0.55,
      1
    ]
  }
} as const;
