import { useEffect, useRef } from 'react';
import PIcon from './icons.jsx';
import { initialsOf } from './ui.jsx';
import { money } from '../api.js';
import './kit.css';

// The components of the Pearl Handoff file (Components page), as the
// signed-in app uses them. Each one takes its colours, spacing and type from
// the tokens in kit.css; none of them knows about the API.

/** An amount as Pearl shows it: never a minus sign; money in gets a "+". */
export function txAmount(amount, { inflow = false } = {}) {
  const text = money(Math.abs(Number(amount) || 0), { cents: true });
  return inflow ? `+${text}` : text;
}

export function Avatar({ name, logo, large = false }) {
  return (
    <span className={`pk-avatar${large ? ' lg' : ''}`} aria-hidden="true">
      {logo ? <img src={logo} alt="" /> : initialsOf(name).slice(0, 2)}
    </span>
  );
}

/**
 * Category chip. Suggested (assigned by Pearl or the bank and not yet
 * confirmed) is a dashed outline with a question mark, so it reads without
 * colour; a screen reader hears "Food Delivery, suggested by Pearl".
 */
export function CategoryChip({ label, suggested = false }) {
  return (
    <span className={`pk-cat${suggested ? ' suggested' : ''}`}
          aria-label={suggested ? `${label}, suggested by Pearl` : label} role="img">
      {suggested && <PIcon name="help" size={12} />}
      <span aria-hidden="true">{label}</span>
    </span>
  );
}

/**
 * Filter chip over a native select: the chip is what you see, the select is
 * what you use, so it works with a keyboard, a screen reader and a phone.
 */
export function FilterChip({ label, value, options, onChange, active = false, shown }) {
  const flat = options.flatMap((o) => o.options ?? [o]);
  shown = shown ?? flat.find((o) => o.value === value)?.label ?? flat[0]?.label;
  return (
    <span className={`pk-filter${active ? ' active' : ''}`}>
      <span aria-hidden="true">{shown}</span>
      <PIcon name="chevronDown" size={14} />
      <select aria-label={label} value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map((o) => (
          o.group
            ? <optgroup key={o.group} label={o.group}>
                {o.options.map((x) => <option key={x.value} value={x.value}>{x.label}</option>)}
              </optgroup>
            : <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    </span>
  );
}

export function SearchField({ value, onChange, placeholder, label = 'Search' }) {
  return (
    <label className="pk-search">
      <PIcon name="search" size={18} />
      <span className="pk-sr">{label}</span>
      <input type="search" value={value} placeholder={placeholder}
             onChange={(e) => onChange(e.target.value)} />
      {value && (
        <button type="button" className="pk-clear" aria-label="Clear search"
                onClick={() => onChange('')}>
          <PIcon name="x" size={16} />
        </button>
      )}
    </label>
  );
}

export function StatTile({ label, value }) {
  return (
    <div className="pk-tile">
      <span className="pk-label">{label}</span>
      <span className="pk-figure">{value}</span>
    </div>
  );
}

const ALERT_ICONS = { info: 'info', caution: 'alert', positive: 'check' };

/** Alert: always an icon and words, never colour alone. */
export function Alert({ tone = 'info', children, action, onAction }) {
  return (
    <div className={`pk-alert ${tone}`} role="status">
      <PIcon name={ALERT_ICONS[tone]} size={20} />
      <p className="pk-alert-msg">{children}</p>
      {action && (
        <button type="button" className="pk-alert-action" onClick={onAction}>
          {action} <PIcon name="chevronRight" size={16} />
        </button>
      )}
    </div>
  );
}

export function StatusPill({ icon = 'info', children }) {
  return (
    <span className="pk-pill">
      <PIcon name={icon} size={14} /> {children}
    </span>
  );
}

export function PButton({ variant = 'primary', className = '', ...rest }) {
  return <button type="button" className={`pk-btn ${variant} ${className}`} {...rest} />;
}

export function DayHeader({ children }) {
  return <p className="pk-overline pk-day">{children}</p>;
}

/**
 * Transaction row. The whole row opens the transaction; nothing inside it is
 * separately clickable, so it is one button with one name.
 *
 *   muted   — Counts = No: not spending and not income
 *   inflow  — money in, shown with a "+"
 */
export function TxRow({ name, logo, meta, note, noteLink = false, chip, amount,
                        inflow = false, muted = false, onOpen }) {
  return (
    <button type="button" className={`pk-row${muted ? ' muted' : ''}`} onClick={onOpen}>
      <Avatar name={name} logo={logo} />
      <span className="pk-row-text">
        <span className="pk-row-name">{name}</span>
        {meta && <span className="pk-row-meta">{meta}</span>}
        {note && <span className={`pk-row-note${noteLink ? ' accent' : ''}`}>{note}</span>}
      </span>
      <span className="pk-row-cat">
        {chip && <CategoryChip label={chip.label} suggested={chip.suggested} />}
      </span>
      <span className={`pk-amt${muted ? ' muted' : inflow ? ' in' : ''}`}>
        {txAmount(amount, { inflow })}
      </span>
    </button>
  );
}

export function EmptyState({ icon = 'search', title, children, action, onAction, extra }) {
  return (
    <div className="pk-empty">
      <span className="pk-empty-icon"><PIcon name={icon} size={24} /></span>
      <h2 className="pk-h3">{title}</h2>
      <p>{children}</p>
      {action && <PButton variant="secondary" onClick={onAction}>{action}</PButton>}
      {extra}
    </div>
  );
}

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), '
  + 'textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * A 560px panel over the page (role=dialog). Focus moves in and stays in;
 * Esc and the scrim close it, and focus goes back to what opened it. On a
 * phone it is the whole page.
 */
export function DetailPanel({ label, overline, onClose, children }) {
  const ref = useRef(null);
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    const opener = document.activeElement;
    ref.current?.querySelector('.pk-close')?.focus();
    const onKey = (e) => {
      if (e.key === 'Escape') { e.stopPropagation(); close.current(); return; }
      if (e.key !== 'Tab' || !ref.current) return;
      const items = [...ref.current.querySelectorAll(FOCUSABLE)];
      if (!items.length) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    };
    document.addEventListener('keydown', onKey);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = overflow;
      if (opener && document.contains(opener)) opener.focus();
    };
  }, []);
  return (
    <div className="pk-scrim" onClick={onClose}>
      <div className="pk-panel" role="dialog" aria-modal="true" aria-label={label} ref={ref}
           onClick={(e) => e.stopPropagation()}>
        <div className="pk-panel-top">
          <p className="pk-overline accent">{overline}</p>
          <button type="button" className="pk-close" aria-label="Close" onClick={onClose}>
            <PIcon name="x" size={18} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function Toast({ children, onDone, ms = 2400 }) {
  useEffect(() => {
    const t = setTimeout(onDone, ms);
    return () => clearTimeout(t);
  }, [onDone, ms]);
  return (
    <div className="pk-toast" role="status" aria-live="polite">
      <PIcon name="check" size={18} /> {children}
    </div>
  );
}
