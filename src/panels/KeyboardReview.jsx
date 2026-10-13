import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { Choice, DetailPanel, PButton } from '../pearl/kit.jsx';
import PIcon from '../pearl/icons.jsx';
import { previewBatchCategory } from '../api.js';
import { categoryLabel } from './CategoryPicker.jsx';
import {
  HINTS, SHORTCUTS, filterCategories, groupTitle, pickerTitle, selectedLabel,
} from './keyboardKeys.js';
import './txextras.css';

/**
 * Keyboard review on desktop (Pearl THL-83): the pieces the transactions
 * list draws around its rows.
 *
 *   K-01  KeyHints        the keys under the toolbar
 *   K-02  SelectedBar     "4 selected" in place of the toolbar, with its keys
 *         BatchPicker     C: type to filter, Enter applies to all selected,
 *                         Esc closes; the line underneath says what it'll do
 *   K-04  ShortcutsPanel  every key, and "Use single-key shortcuts" (WCAG
 *                         2.1.4), saved for her account
 *
 * Bulk changes never write a merchant rule; "Apply to all from this
 * merchant" stays a one-at-a-time choice in Change category (R-02).
 */

export function Keys({ keys }) {
  return (
    <span className="kr-keys">
      {keys.map((k) => <kbd key={k} className="kr-key">{k}</kbd>)}
    </span>
  );
}

/** K-01: what the keys do, in a line under the toolbar. */
export function KeyHints({ singleKey = true }) {
  const shown = singleKey ? HINTS : HINTS.filter((h) => !h.single);
  return (
    <div className="kr-hints" role="note" aria-label="Keyboard shortcuts for the list">
      {shown.map((h) => (
        <span key={h.label} className="kr-hint">
          <Keys keys={h.keys} />
          <span>{h.label}</span>
        </span>
      ))}
    </div>
  );
}

/** K-02: the selection, and what can be done to all of it. */
export function SelectedBar({ count, singleKey = true, onChange, onConfirm, onClear }) {
  const key = (k) => (singleKey ? k : undefined);
  return (
    <div className="kr-selected" role="region" aria-label="Selected transactions">
      <p className="kr-selected-count" aria-live="polite">{selectedLabel(count)}</p>
      <button type="button" className="kr-action" onClick={onChange} aria-keyshortcuts={key('C')}>
        Change category {singleKey && <Keys keys={['C']} />}
      </button>
      <button type="button" className="kr-action" onClick={onConfirm} aria-keyshortcuts={key('Y')}>
        Confirm suggestions {singleKey && <Keys keys={['Y']} />}
      </button>
      <button type="button" className="kr-action" onClick={onClear} aria-keyshortcuts="Escape">
        Clear <Keys keys={['Esc']} />
      </button>
    </div>
  );
}

/**
 * K-02: change the category of every selected row. Typing filters by
 * category and group; ↑/↓ move between matches; Enter applies; Esc closes.
 */
export function BatchPicker({ ids, categories, busy = false, onApply, onClose, initialQuery = '' }) {
  const [q, setQ] = useState(initialQuery);
  const [active, setActive] = useState(0);
  const [line, setLine] = useState('');
  const listId = useId();
  const input = useRef(null);
  const options = useMemo(() => filterCategories(categories, q).slice(0, 8), [categories, q]);
  const at = Math.min(active, options.length - 1);
  const current = options[at];
  const count = ids.length;

  useEffect(() => { input.current?.focus(); }, []);
  useEffect(() => { setActive(0); }, [q]);
  // What it would do, said before it is done.
  useEffect(() => {
    if (!current) { setLine(''); return undefined; }
    let live = true;
    const t = setTimeout(() => {
      previewBatchCategory(ids, current.name)
        .then((r) => { if (live) setLine(r.line || ''); }).catch(() => { if (live) setLine(''); });
    }, 120);
    return () => { live = false; clearTimeout(t); };
  }, [current?.name, ids.join(',')]);

  const onKey = (e) => {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      const step = e.key === 'ArrowDown' ? 1 : -1;
      setActive((a) => Math.max(0, Math.min(a + step, options.length - 1)));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (current && !busy) onApply(current.name);
    } else if (e.key === 'Escape') {
      e.preventDefault();
      e.stopPropagation();
      onClose();
    }
  };

  return (
    <section className="kr-picker" aria-label={pickerTitle(count)}>
      <p className="pk-overline" id={`${listId}-title`}>{pickerTitle(count)}</p>
      <label className="kr-filter">
        <PIcon name="search" size={18} />
        <span className="pk-sr">Category</span>
        <input ref={input} type="text" value={q} placeholder="Type a category"
               role="combobox" aria-expanded="true" aria-controls={listId}
               aria-activedescendant={current ? `${listId}-o${at}` : undefined}
               aria-describedby={`${listId}-line`} autoComplete="off"
               onChange={(e) => setQ(e.target.value)} onKeyDown={onKey} />
      </label>
      <ul className="kr-options" role="listbox" id={listId} aria-labelledby={`${listId}-title`}>
        {options.map((c, i) => {
          const on = i === at;
          return (
            <li key={c.name} id={`${listId}-o${i}`} role="option" aria-selected={on}
                className={`kr-option${on ? ' on' : ''}`}
                onMouseDown={(e) => { e.preventDefault(); if (!busy) onApply(c.name); }}>
              <span className="kr-option-name">{categoryLabel(c.name)}</span>
              <span className="kr-option-group">{groupTitle(c.group)}</span>
              {on && <Keys keys={['Enter']} />}
            </li>
          );
        })}
        {options.length === 0 && (
          <li className="kr-none" role="presentation">No category matches “{q}”.</li>
        )}
      </ul>
      <p className="kr-line" id={`${listId}-line`} role="status" aria-live="polite">{line}</p>
    </section>
  );
}

/** K-04: every key, and the switch for single-key shortcuts. */
export function ShortcutsPanel({ singleKey = true, onToggle, onClose }) {
  return (
    <DetailPanel label="Keyboard shortcuts" overline="Desktop" onClose={onClose}
                 className="kr-panel">
      <h2 className="pk-h2">Keyboard shortcuts</h2>
      <dl className="kr-list">
        {SHORTCUTS.map((s) => (
          <div className="kr-list-row" key={s.label}>
            <dt>{s.label}</dt>
            <dd><Keys keys={s.keys} /></dd>
          </div>
        ))}
      </dl>
      <Choice type="checkbox" checked={singleKey} onChange={onToggle}
              label="Use single-key shortcuts"
              description="Turn these off if they clash with your screen reader or voice control. Ctrl / ⌘ shortcuts always work." />
      <div className="txd-actions">
        <PButton onClick={onClose}>Done</PButton>
      </div>
    </DetailPanel>
  );
}
