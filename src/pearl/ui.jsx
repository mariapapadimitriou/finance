import { useEffect, useId, useRef } from 'react';
import PIcon from './icons.jsx';
import logoMark from './assets/logo-mark.svg';
import shellClosed from './assets/shell-closed.svg';
import shellOpening from './assets/shell-opening.svg';
import './pearl.css';

export const MARKS = { pearl: logoMark, closed: shellClosed, opening: shellOpening };

// What the panel's footnote promises. The design also says "Hosted in Canada";
// Pearl's hosting isn't in Canada today, so that claim is left out until it is.
const FOOTNOTE = 'Read-only access  ·  Encrypted  ·  We never sell your data';

export const STEPS = ['Your account', 'Sign-in', 'Where you live', 'How we protect you',
  'Your choices', 'Link your bank'];

export function Lockup() {
  return (
    <span className="p-lockup" aria-label="Pearl">
      <img src={logoMark} alt="" width="58" height="48" />
      <span aria-hidden="true">pearl</span>
    </span>
  );
}

/**
 * Every signed-out and onboarding screen: the nacre panel on the left, the
 * form on the right, Back and the step count above it, the footer below.
 *
 * `step` is 1–6 inside onboarding (the panel shows the stepper and the top
 * bar "Step n of 6"), `'done'` when it has finished, and absent elsewhere,
 * where the panel shows its footnote instead.
 */
export function AuthLayout({
  headline, body, mark, step, topRight, onBack, onDoc, children, centered = false,
}) {
  const inOnboarding = step != null;
  const stepNo = step === 'done' ? STEPS.length + 1 : step;
  return (
    <div className="pearl">
      <aside className="p-panel">
        <Lockup />
        <div className="p-message">
          {mark && <img className="p-mark" src={MARKS[mark]} alt="" width="132" height="110" />}
          {headline && <h2>{headline}</h2>}
          {body && <p>{body}</p>}
        </div>
        <div className="p-panel-foot">
          {inOnboarding ? (
            <ol className="p-stepper" aria-label="Setup progress">
              {STEPS.map((label, i) => {
                const n = i + 1;
                const state = n < stepNo ? 'done' : n === stepNo ? 'current' : 'upcoming';
                return (
                  <li key={label} className={state}
                      aria-current={state === 'current' ? 'step' : undefined}>
                    <span className="p-dot" aria-hidden="true">
                      {state === 'done' && <PIcon name="check" size={16} />}
                    </span>
                    <span>{label}</span>
                  </li>
                );
              })}
            </ol>
          ) : (
            <p className="p-footnote">{FOOTNOTE}</p>
          )}
        </div>
      </aside>

      <div className="p-content">
        <div className="p-topbar">
          {onBack ? (
            <button type="button" className="p-back" onClick={onBack}>
              <PIcon name="arrowLeft" /> Back
            </button>
          ) : <span />}
          <span className="p-step">
            {topRight ?? (step === 'done' ? 'Done'
              : inOnboarding ? `Step ${step} of ${STEPS.length}` : null)}
          </span>
        </div>
        <main className="p-body">
          <div className={`p-form${centered ? ' centered' : ''}`}>{children}</div>
        </main>
        <footer className="p-footer">
          <span>© 2026 Pearl</span>
          <nav aria-label="About Pearl">
            <button type="button" onClick={() => onDoc?.('privacy')}>Privacy</button>
            <button type="button" onClick={() => onDoc?.('terms')}>Terms</button>
            <button type="button" onClick={() => onDoc?.('help')}>Help</button>
          </nav>
        </footer>
      </div>
    </div>
  );
}

export function Heading({ eyebrow, title, sub, level = 1, id }) {
  return (
    <div className="p-heading">
      {eyebrow && <p className="p-eyebrow">{eyebrow}</p>}
      {level === 1 ? <h1 className="p-h1" id={id}>{title}</h1>
        : <h2 className="p-h2" id={id}>{title}</h2>}
      {sub && <p className="p-sub">{sub}</p>}
    </div>
  );
}

export function Field({ label, hint, error, icon, children }) {
  const id = useId();
  const hintId = `${id}-hint`;
  const child = typeof children === 'function'
    ? children({ id, 'aria-describedby': hint || error ? hintId : undefined,
                 'aria-invalid': error ? true : undefined })
    : children;
  return (
    <div className="p-field">
      <label htmlFor={id}>{label}</label>
      <div className={`p-control${error ? ' error' : ''}`}>
        {icon && <PIcon name={icon} />}
        {child}
      </div>
      {(error || hint) && (
        <p id={hintId} className={`p-hint${error ? ' error' : ''}`}>{error || hint}</p>
      )}
    </div>
  );
}

/** Six boxes over one real input, so paste, autofill and SMS codes all work. */
export function CodeInput({ value, onChange, error, label = 'Six-digit code', autoFocus = true }) {
  const ref = useRef(null);
  useEffect(() => { if (autoFocus) ref.current?.focus(); }, [autoFocus]);
  const digits = value.padEnd(6, ' ').slice(0, 6).split('');
  const active = Math.min(value.length, 5);
  return (
    <div className="p-code" onClick={() => ref.current?.focus()}>
      <input ref={ref} type="text" inputMode="numeric" autoComplete="one-time-code"
             pattern="[0-9]*" maxLength={6} aria-label={label} value={value}
             aria-invalid={error ? true : undefined}
             onChange={(e) => onChange(e.target.value.replace(/\D/g, '').slice(0, 6))} />
      {digits.map((d, i) => {
        const filled = d.trim() !== '';
        const cls = error ? 'error' : (!filled && i === active && value.length < 6) ? 'active' : '';
        return <div key={i} className={`p-digit ${cls}`} aria-hidden="true">{filled ? d : ''}</div>;
      })}
    </div>
  );
}

export function Choice({ type = 'checkbox', checked, onChange, label, description, name }) {
  return (
    <label className={`p-choice ${type === 'radio' ? 'radio' : ''}${checked ? ' on' : ''}`}>
      <input type={type} name={name} checked={checked}
             onChange={(e) => onChange(e.target.checked)} />
      <span className="p-box" aria-hidden="true">
        {checked && <PIcon name="check" size={20} />}
      </span>
      <span className="p-choice-text">
        <span>{label}</span>
        {description && <small>{description}</small>}
      </span>
    </label>
  );
}

export function TrustPoint({ icon, title, children, link, onLink }) {
  return (
    <div className="p-point">
      <span className="p-bubble" aria-hidden="true"><PIcon name={icon} /></span>
      <div className="p-point-text">
        <h3 className="p-h3">{title}</h3>
        <p>{children}</p>
        {link && <button type="button" className="p-link small" onClick={onLink}>{link}</button>}
      </div>
    </div>
  );
}

const BANNER_ICON = { info: 'info', caution: 'alert', positive: 'check' };

export function Banner({ tone = 'info', children }) {
  return (
    <div className={`p-banner ${tone}`} role={tone === 'caution' ? 'alert' : 'status'}>
      <PIcon name={BANNER_ICON[tone]} />
      <span>{children}</span>
    </div>
  );
}

export function Callout({ icon = 'fingerprint', title, children }) {
  return (
    <div className="p-callout">
      <span className="p-icon-dot" aria-hidden="true"><PIcon name={icon} /></span>
      <div>
        <h3 className="p-h3">{title}</h3>
        <p>{children}</p>
      </div>
    </div>
  );
}

/** The large round icon over a centred message (waiting, expired, paused). */
export function BigIcon({ name }) {
  return <span className="p-bubble big" aria-hidden="true"><PIcon name={name} /></span>;
}

export function Initials({ name, logo, large = false }) {
  const text = initialsOf(name);
  return (
    <span className={`p-initials${large ? ' lg' : ''}`} aria-hidden="true">
      {logo ? <img src={logo} alt="" /> : text}
    </span>
  );
}

export function initialsOf(name) {
  const words = String(name || '').replace(/[^A-Za-z0-9 ]/g, ' ').split(/\s+/).filter(Boolean);
  if (!words.length) return '•';
  if (words.length === 1) return words[0].slice(0, words[0].length <= 4 ? 4 : 2).toUpperCase();
  return (words[0][0] + words[1][0]).toUpperCase();
}

/** A side sheet for the detail pages and the footer's Privacy, Terms and Help. */
export function Sheet({ backLabel, onBack, onClose, children, label }) {
  const ref = useRef(null);
  useEffect(() => {
    ref.current?.focus();
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);
  return (
    <div className="p-scrim" onClick={onClose}>
      <div className="p-sheet" role="dialog" aria-modal="true" aria-label={label}
           tabIndex={-1} ref={ref} onClick={(e) => e.stopPropagation()}>
        <div className="p-sheet-top">
          {onBack ? (
            <button type="button" className="p-back" onClick={onBack}>
              <PIcon name="arrowLeft" /> {backLabel}
            </button>
          ) : <span />}
          <button type="button" className="p-x" onClick={onClose} aria-label="Close">
            <PIcon name="x" />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
