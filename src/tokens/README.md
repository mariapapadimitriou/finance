# Pearl design tokens

Exported from the Figma file **Pearl Design System** (`3fdfPDKIjhiluGHtXWSF32`)
and attached to THL-106 (v3, 2026-10-11). The three files hold the same tokens:

| File          | Used by                                                       |
| ------------- | ------------------------------------------------------------- |
| `tokens.css`  | This web app. `src/main.jsx` loads it before `styles.css`.    |
| `tokens.ts`   | The React Native app (THL-147). Not imported here.            |
| `tokens.json` | Tooling (W3C design-token format).                            |

**Do not edit these by hand.** When the Figma variables change, re-export all
three and replace the files whole.

`tokens.css` defines its semantic tokens on `:root`. The app shell
(`src/styles.css`) still defines its own `--ink`, `--border` and `--display`
there and wins, so the screens not yet rebuilt look as they did. The Pearl kit
(`src/pearl/tokens.css`, scoped to `.pk`) puts the Design System's `--border`
back for the screens built from the Handoff file.
