/**
 * Keyboard review on desktop (Pearl THL-83, K-01 to K-04): which key does
 * what, and what it does to the list's focus and selection. No React here,
 * so every rule can be tested on its own.
 *
 * Keys, only while the list has focus and never in a text field:
 *   ↑/↓ or K/J move · X select · Shift+↑/↓ select a range · Y confirm
 *   Pearl's suggestion · C change category · U one-off · Enter open ·
 *   / search · Esc close or clear · Ctrl/⌘+Z undo · ? this list.
 *
 * Single-key shortcuts (letters and symbols) can be turned off (WCAG 2.1.4)
 * when they clash with a screen reader or voice control. Arrows, Enter, Esc
 * and Ctrl/⌘ combinations always work: none of them is a character key.
 */

// K-01's bar under the toolbar.
// `single` marks a character key, which goes when she turns them off.
export const HINTS = [
  { keys: ['↑', '↓'], label: 'Move' },
  { keys: ['Y'], label: 'Confirm', single: true },
  { keys: ['C'], label: 'Change category', single: true },
  { keys: ['X'], label: 'Select', single: true },
  { keys: ['Enter'], label: 'Open' },
  { keys: ['?'], label: 'All shortcuts', single: true },
];

// K-04's list, in its order.
export const SHORTCUTS = [
  { keys: ['↑', '↓'], label: 'Move between transactions' },
  { keys: ['X'], label: 'Select' },
  { keys: ['Shift', '↑', '↓'], label: 'Select a range' },
  { keys: ['Y'], label: 'Confirm Pearl’s suggestion' },
  { keys: ['C'], label: 'Change category' },
  { keys: ['U'], label: 'Mark as a one-off' },
  { keys: ['Enter'], label: 'Open details' },
  { keys: ['/'], label: 'Search' },
  { keys: ['Esc'], label: 'Close or clear selection' },
  { keys: ['Ctrl / ⌘', 'Z'], label: 'Undo' },
  { keys: ['?'], label: 'Show this list' },
];

const LETTERS = {
  j: 'down', k: 'up', x: 'select', y: 'confirm', c: 'change', u: 'oneoff',
  '/': 'search', '?': 'help',
};

/**
 * The action a key press asks for, or null. `e` is a KeyboardEvent or
 * anything shaped like one: { key, shiftKey, ctrlKey, metaKey, altKey }.
 * `singleKey` is her preference; `inText` is true when the key was typed
 * into a text field, where only the field gets it.
 */
export function keyAction(e, { singleKey = true, inText = false } = {}) {
  if (!e || inText) return null;
  const key = e.key ?? '';
  if ((e.ctrlKey || e.metaKey) && !e.altKey) {
    return key.toLowerCase() === 'z' && !e.shiftKey ? 'undo' : null;
  }
  if (e.altKey) return null;
  if (key === 'ArrowDown') return e.shiftKey ? 'extendDown' : 'down';
  if (key === 'ArrowUp') return e.shiftKey ? 'extendUp' : 'up';
  if (key === 'Enter') return 'open';
  if (key === 'Escape' || key === 'Esc') return 'clear';
  if (!singleKey) return null;
  return LETTERS[key.toLowerCase()] ?? null;
}

/** Whether a key press landed in somewhere typing goes. A checkbox in the
 * list is part of the list, so its keys are the list's. */
export function isTextTarget(target) {
  if (!target) return false;
  const tag = (target.tagName || '').toLowerCase();
  if (tag === 'textarea' || tag === 'select') return true;
  if (tag === 'input') {
    return !['checkbox', 'radio', 'button'].includes((target.type || '').toLowerCase());
  }
  return !!target.isContentEditable;
}

export const initialState = () => ({ focus: 0, selected: [], anchor: null });

const clamp = (n, count) => Math.max(0, Math.min(n, Math.max(count - 1, 0)));

/**
 * What a list action does to focus and selection. `ids` are the rows in
 * the order they are shown. Returns the new state; actions that act on the
 * rows (confirm, change, one-off, open, undo…) leave it as it is.
 */
export function reduce(state, action, ids) {
  const count = ids.length;
  if (!count) return { ...state, focus: 0, selected: [], anchor: null };
  const focus = clamp(state.focus, count);
  const keep = state.selected.filter((id) => ids.includes(id));
  switch (action) {
    case 'down':
      return { ...state, focus: clamp(focus + 1, count), selected: keep, anchor: null };
    case 'up':
      return { ...state, focus: clamp(focus - 1, count), selected: keep, anchor: null };
    case 'extendDown':
    case 'extendUp': {
      const anchor = state.anchor ?? focus;
      const next = clamp(focus + (action === 'extendDown' ? 1 : -1), count);
      return { ...state, focus: next, anchor, selected: withRange(keep, ids, anchor, next) };
    }
    case 'select': {
      const id = ids[focus];
      const on = keep.includes(id);
      return { ...state, focus, anchor: focus,
               selected: on ? keep.filter((x) => x !== id) : [...keep, id] };
    }
    case 'clear':
      return { ...state, focus, selected: [], anchor: null };
    default:
      return { ...state, focus, selected: keep };
  }
}

/** Shift-click: everything from the anchor to `index`, added. */
export function selectRange(state, ids, index) {
  const anchor = state.anchor ?? clamp(state.focus, ids.length);
  return { ...state, focus: index, anchor,
           selected: withRange(state.selected.filter((id) => ids.includes(id)), ids, anchor, index) };
}

function withRange(selected, ids, from, to) {
  const [lo, hi] = from <= to ? [from, to] : [to, from];
  const out = [...selected];
  ids.slice(lo, hi + 1).forEach((id) => { if (!out.includes(id)) out.push(id); });
  return out;
}

/** The rows an action applies to: the selection, or the focused row. */
export function targets(state, ids) {
  const keep = state.selected.filter((id) => ids.includes(id));
  if (keep.length) return ids.filter((id) => keep.includes(id));
  const id = ids[clamp(state.focus, ids.length)];
  return id ? [id] : [];
}

// ── Words ────────────────────────────────────────────────────────────────

export const selectedLabel = (n) => `${n} selected`;
export const pickerTitle = (n) => (n === 1 ? 'Change 1 transaction to'
  : `Change ${n} transactions to`);

const GROUP_TITLES = { essentials: 'Essentials', lifestyle: 'Lifestyle', savings: 'Savings',
                       income: 'Income', transfer: 'Not spending' };
export const groupTitle = (g) => GROUP_TITLES[g] ?? '';

/** K-02's filter: typing matches a category or its group. */
export function filterCategories(categories, q) {
  const needle = (q || '').trim().toLowerCase();
  const usable = categories.filter((c) => c.name !== 'Unsorted transfers');
  if (!needle) return usable;
  const starts = [];
  const rest = [];
  usable.forEach((c) => {
    const name = c.name.toLowerCase();
    const group = groupTitle(c.group).toLowerCase().split(/\s+/);
    if (name.startsWith(needle)) starts.push(c);
    else if (name.includes(needle) || group.some((w) => w.startsWith(needle))) rest.push(c);
  });
  return [...starts, ...rest];
}

/** What a row says to a screen reader: merchant, amount, category and
 * "suggested" — and whether it's selected. */
export function rowName(r, amountText) {
  const chip = r.chip?.label ? `, ${r.chip.label}${r.chip.suggested ? ', suggested' : ''}` : '';
  return `${r.merchant}, ${amountText}${chip}`;
}
