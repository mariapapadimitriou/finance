import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import {
  HINTS, SHORTCUTS, filterCategories, initialState, isTextTarget, keyAction, pickerTitle,
  reduce, rowName, selectRange, selectedLabel, targets,
} from './keyboardKeys.js';
import { BatchPicker, KeyHints, SelectedBar, ShortcutsPanel } from './KeyboardReview.jsx';
import { CopyCard, DuplicateQuestion, copyPhrase, duplicateAlert } from './Duplicates.jsx';
import { OneOffCard } from './TransactionDetail.jsx';

const html = (el) => renderToStaticMarkup(el);
const calm = (text) => {
  expect(text).not.toMatch(/[−-]\s?\$/);
  expect(text).not.toMatch(/\$0(?![.,\d])|\$0\.00/);
  expect(text).not.toMatch(/NaN|undefined|null/);
};
const primaries = (out) => (out.match(/pk-btn primary/g) || []).length;
const key = (k, mods = {}) => ({ key: k, shiftKey: false, ctrlKey: false, metaKey: false,
                                 altKey: false, ...mods });
const IDS = ['a', 'b', 'c', 'd', 'e', 'f', 'g'];

describe('keys (THL-83 K-01)', () => {
  it('arrows or J/K move; Shift+arrows select a range', () => {
    expect(keyAction(key('ArrowDown'))).toBe('down');
    expect(keyAction(key('ArrowUp'))).toBe('up');
    expect(keyAction(key('j'))).toBe('down');
    expect(keyAction(key('K'))).toBe('up');
    expect(keyAction(key('ArrowDown', { shiftKey: true }))).toBe('extendDown');
    expect(keyAction(key('ArrowUp', { shiftKey: true }))).toBe('extendUp');
  });

  it('X select, Y confirm, C change, U one-off, Enter open, / search, Esc clear, ? list', () => {
    expect(['x', 'y', 'c', 'u', 'Enter', '/', 'Escape', '?'].map((k) => keyAction(key(k))))
      .toEqual(['select', 'confirm', 'change', 'oneoff', 'open', 'search', 'clear', 'help']);
  });

  it('Ctrl or ⌘ + Z undo, and no other combination is taken', () => {
    expect(keyAction(key('z', { ctrlKey: true }))).toBe('undo');
    expect(keyAction(key('Z', { metaKey: true }))).toBe('undo');
    expect(keyAction(key('z', { ctrlKey: true, shiftKey: true }))).toBe(null);
    expect(keyAction(key('c', { metaKey: true }))).toBe(null);
    expect(keyAction(key('x', { altKey: true }))).toBe(null);
  });

  it('never in a text field', () => {
    expect(keyAction(key('j'), { inText: true })).toBe(null);
    expect(keyAction(key('ArrowDown'), { inText: true })).toBe(null);
    expect(isTextTarget({ tagName: 'INPUT', type: 'search' })).toBe(true);
    expect(isTextTarget({ tagName: 'TEXTAREA' })).toBe(true);
    expect(isTextTarget({ tagName: 'INPUT', type: 'checkbox' })).toBe(false);
    expect(isTextTarget({ tagName: 'BUTTON' })).toBe(false);
  });

  it('single-key shortcuts off (WCAG 2.1.4): only arrows, Enter, Esc and Ctrl/⌘ work', () => {
    const off = { singleKey: false };
    for (const k of ['j', 'k', 'x', 'y', 'c', 'u', '/', '?']) expect(keyAction(key(k), off)).toBe(null);
    expect(keyAction(key('ArrowDown'), off)).toBe('down');
    expect(keyAction(key('ArrowUp', { shiftKey: true }), off)).toBe('extendUp');
    expect(keyAction(key('Enter'), off)).toBe('open');
    expect(keyAction(key('Escape'), off)).toBe('clear');
    expect(keyAction(key('z', { ctrlKey: true }), off)).toBe('undo');
  });
});

describe('focus and selection (K-01, K-02)', () => {
  it('moves, and stops at either end', () => {
    let s = initialState();
    s = reduce(s, 'down', IDS);
    s = reduce(s, 'down', IDS);
    expect(s.focus).toBe(2);
    s = reduce(s, 'up', IDS);
    expect(s.focus).toBe(1);
    expect(reduce({ ...s, focus: 0 }, 'up', IDS).focus).toBe(0);
    expect(reduce({ ...s, focus: 6 }, 'down', IDS).focus).toBe(6);
  });

  it('X selects and deselects the focused row', () => {
    let s = reduce({ ...initialState(), focus: 2 }, 'select', IDS);
    expect(s.selected).toEqual(['c']);
    s = reduce(s, 'select', IDS);
    expect(s.selected).toEqual([]);
  });

  it('Shift+arrows select a range from where it started', () => {
    let s = reduce({ ...initialState(), focus: 1 }, 'extendDown', IDS);
    s = reduce(s, 'extendDown', IDS);
    expect(s.focus).toBe(3);
    expect(s.selected).toEqual(['b', 'c', 'd']);
  });

  it('Shift-click selects a range too', () => {
    const s = selectRange({ ...initialState(), focus: 4, anchor: 4, selected: ['e'] }, IDS, 6);
    expect(s.selected).toEqual(['e', 'f', 'g']);
  });

  it('Esc clears the selection and keeps the focus', () => {
    const s = reduce({ focus: 3, selected: ['a', 'd'], anchor: 0 }, 'clear', IDS);
    expect(s).toEqual({ focus: 3, selected: [], anchor: null });
  });

  it('an action applies to the selection, or to the focused row', () => {
    expect(targets({ focus: 1, selected: ['d', 'a'] }, IDS)).toEqual(['a', 'd']);
    expect(targets({ focus: 1, selected: [] }, IDS)).toEqual(['b']);
    expect(targets({ focus: 0, selected: [] }, [])).toEqual([]);
  });

  it('rows that went away are dropped from the selection', () => {
    expect(reduce({ focus: 9, selected: ['z', 'a'] }, 'confirm', IDS))
      .toEqual({ focus: 6, selected: ['a'], anchor: undefined });
  });

  it('a screen reader hears merchant, amount, category and suggested', () => {
    const r = { merchant: 'Uber Eats', chip: { label: 'Food Delivery', suggested: true } };
    expect(rowName(r, '$24.80')).toBe('Uber Eats, $24.80, Food Delivery, suggested');
  });
});

describe('the screens (K-01 to K-04)', () => {
  const categories = [
    { name: 'Dining', group: 'lifestyle' }, { name: 'Food Delivery', group: 'lifestyle' },
    { name: 'Groceries', group: 'essentials' }, { name: 'Transfers', group: 'transfer' },
    { name: 'Unsorted transfers', group: 'transfer' },
  ];

  it('K-01: the hints say what the keys do', () => {
    const out = html(<KeyHints />);
    for (const h of HINTS) expect(out).toContain(`>${h.label}<`);
    expect(out).toContain('<kbd class="kr-key">?</kbd>');
    // Off, the letters go and the arrows and Enter stay.
    const off = html(<KeyHints singleKey={false} />);
    expect(off).not.toContain('>Y<');
    expect(off).toContain('Move');
    expect(off).toContain('Open');
  });

  it('K-02: the selected bar and the picker', () => {
    expect(selectedLabel(4)).toBe('4 selected');
    const bar = html(<SelectedBar count={4} />);
    expect(bar).toContain('4 selected');
    expect(bar).toContain('Change category');
    expect(bar).toContain('Confirm suggestions');
    expect(bar).toContain('aria-keyshortcuts="C"');
    expect(bar).toContain('aria-keyshortcuts="Escape"');
    const picker = html(<BatchPicker ids={['a', 'b', 'c', 'd']} categories={categories}
                                     initialQuery="din" onApply={() => {}} onClose={() => {}} />);
    expect(picker).toContain('Change 4 transactions to');
    expect(picker).toContain('Dining');
    expect(picker).toContain('Lifestyle');
    expect(picker).toContain('>Enter<');
    expect(pickerTitle(1)).toBe('Change 1 transaction to');
    calm(picker);
  });

  it('K-02: typing filters on category and on group', () => {
    expect(filterCategories(categories, 'din').map((c) => c.name)).toEqual(['Dining']);
    expect(filterCategories(categories, 'essent').map((c) => c.name)).toEqual(['Groceries']);
    expect(filterCategories(categories, '').map((c) => c.name)).not.toContain('Unsorted transfers');
  });

  it('K-04: every key, the switch, and one primary', () => {
    const out = html(<ShortcutsPanel singleKey onToggle={() => {}} onClose={() => {}} />);
    expect(out).toContain('Keyboard shortcuts');
    expect(out).toContain('Desktop');
    for (const s of SHORTCUTS) expect(out).toContain(s.label.replace('’', '’'));
    expect(out).toContain('Use single-key shortcuts');
    expect(out).toContain('Ctrl / ⌘ shortcuts always work.');
    expect(out).toContain('role="dialog"');
    expect(primaries(out)).toBe(1);
    calm(out);
  });
});

describe('one-offs (THL-71 U-01, U-03)', () => {
  const tx = { id: 'i', date: '2026-10-03', one_off: false, can_one_off: true };

  it('U-01: asks, and says what it is for', () => {
    const out = html(<OneOffCard tx={tx} onToggle={() => {}} />);
    expect(out).toContain('This was a one-off');
    expect(out).toContain('Leave it out of my usual month. It still counts in October.');
    expect(out).toContain('Good for tax refunds, moving costs or a big one-time purchase.');
    expect(out).not.toContain('checked=""');
    calm(out);
  });

  it('U-03: ticked, with since when and the usual month', () => {
    const out = html(<OneOffCard tx={{ ...tx, one_off: true, one_off_line: {
      line: 'Left out since October 9. A usual month of Lifestyle: $1,150.' } }}
                                 onToggle={() => {}} />);
    expect(out).toContain('checked=""');
    expect(out).toContain('Left out since October 9. A usual month of Lifestyle: $1,150.');
    calm(out);
  });
});

describe('possible duplicates (THL-165 D-01, D-02)', () => {
  const it2 = {
    key: 'dup:c',
    txn: { id: 'c', date: '2026-10-07', merchant: 'Loblaws', amount: 96.32, account: 'Visa ··4421',
           description: 'LOBLAWS 1032 TORONTO', source_label: 'from a statement file',
           source_verb: 'uploaded', found_on: '2026-10-09' },
    twin: { id: 't', date: '2026-10-07', merchant: 'Loblaws', amount: 96.32, account: 'Visa ··4421',
            description: 'LOBLAWS #1032 TORONTO ON', source_label: 'from your bank connection',
            source_verb: 'synced' },
  };

  it('D-01: the alert counts them once', () => {
    expect(duplicateAlert(1)).toBe('1 possible duplicate needs a look. We’re counting it once for now.');
    expect(duplicateAlert(2)).toBe('2 possible duplicates need a look. We’re counting each once for now.');
    expect(duplicateAlert(0)).toBe('');
  });

  it('D-02: both copies side by side, and the two answers', () => {
    const out = html(<DuplicateQuestion it={it2} onAnswer={() => {}} onSkip={() => {}} />);
    expect(out).toContain('Is this the same purchase?');
    expect(out).toContain('from your bank connection');
    expect(out).toContain('from a statement file');
    expect(out).toContain('LOBLAWS 1032 TORONTO · uploaded Oct 9');
    expect(out).toContain('LOBLAWS #1032 TORONTO ON · synced');
    expect(out).toContain('$96.32');
    expect(out).toContain('Same purchase');
    expect(out).toContain('Keep one. We’ll hide the copy from the statement file.');
    expect(out).toContain('Two different purchases');
    expect(out).toContain('Keep both. Both count as spending.');
    expect(out).toContain('Skip for now');
    expect(primaries(out)).toBe(1);
    calm(out);
  });

  it('says where a copy came from in words', () => {
    expect(copyPhrase('added by hand')).toBe('you added by hand');
    const card = html(<CopyCard side={it2.twin} />);
    expect(card).toContain('Wednesday, October 7 · Visa ··4421');
  });
});
