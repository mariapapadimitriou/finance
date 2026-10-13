import { useCallback, useEffect, useState } from 'react';
import { ErrorNote } from '../components/ui.jsx';
import { getAuthStatus, getProfileSummary, undoInvesting } from '../api.js';
import { StatusPill } from '../pearl/kit.jsx';
import PIcon from '../pearl/icons.jsx';
import './home.css';
import './profile.css';

/**
 * Profile (Pearl "Accounts & settings", S-01): the hub at the foot of the
 * sidebar. Grouped rows — Money, You, Privacy, Help — each opening a page
 * with a breadcrumb back here; the Profile group has no sub-tab strip.
 *
 * Accounts (AM-01, AccountsPanel.jsx), Categories and rules (S-03,
 * RulesPanel.jsx) and Sign-in and security (SecurityPanel.jsx, with S-02)
 * are built, and Income and bills (THL-45, THL-127, IncomeBillsPanel.jsx)
 * under Money. The rest are drawn but marked "Coming soon" until their pages
 * exist; each names its panel key in `SOON` so a later PR only wires it.
 */

/** The breadcrumb over every Profile page: "Profile › Accounts › TD Visa". */
export function Crumbs({ trail, onTab }) {
  return (
    <nav className="pf-crumbs" aria-label="Breadcrumb">
      <ol>
        {trail.map((c, i) => (
          <li key={`${c.label}-${i}`}>
            {i < trail.length - 1 ? (
              <button type="button" onClick={c.onClick ?? (() => onTab?.(c.to))}>{c.label}</button>
            ) : <span aria-current="page">{c.label}</span>}
          </li>
        ))}
      </ol>
    </nav>
  );
}

/** A Profile page's heading: the breadcrumb, then the title. */
export function PageHead({ trail, title, onTab, children }) {
  return (
    <header className="pf-head">
      <Crumbs trail={trail} onTab={onTab} />
      <h1 className="pk-h1">{title}</h1>
      {children}
    </header>
  );
}

/** One row of a grouped list. `soon` draws it muted, and not a button. */
export function ListRow({ name, sub, end, onOpen, soon = false, chevron = true }) {
  const inner = (
    <>
      <span className="pf-row-text">
        <span className="pf-row-name">{name}</span>
        {sub && <span className="pf-row-sub">{sub}</span>}
      </span>
      <span className="pf-row-end">
        {soon ? <span className="pf-soon">Coming soon</span> : end}
        {!soon && chevron && onOpen && <PIcon name="chevronRight" size={18} />}
      </span>
    </>
  );
  return (
    <li className={`pf-row${soon ? ' soon' : ''}${!soon && !onOpen ? ' static' : ''}`}>
      {soon || !onOpen
        ? <div className="pf-row-main" aria-disabled={soon ? 'true' : undefined}>{inner}</div>
        : <button type="button" className="pf-row-main" onClick={onOpen}>{inner}</button>}
    </li>
  );
}

const plural = (n, one, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

/** What each row of S-01 says, from the hub's counts and who is signed in. */
export function hubRows(summary, user) {
  const s = summary ?? {};
  const passkeys = user?.passkeys ?? 0;
  return [
    { title: 'Money', rows: [
      { key: 'accounts', name: 'Accounts',
        sub: s.accounts ? plural(s.accounts, 'account') : 'Link a bank or add a balance',
        needs: s.needs_you || 0 },
      { key: 'rules', name: 'Categories and rules',
        sub: s.rules ? plural(s.rules, 'saved rule') : 'No saved rules yet' },
      { key: 'income', name: 'Income and bills',
        sub: 'Your pay, and the regular bills set aside' },
      // Unveil's self-report (THL-195 GR-37), undone here.
      ...(s.investing ? [{ key: 'investing', name: 'Investing account', undo: true,
                           sub: `You told Pearl you opened one: ${s.investing.label}` }] : []),
    ] },
    { title: 'You', rows: [
      { key: 'security', name: 'Sign-in and security',
        sub: [user?.email, passkeys > 0 ? plural(passkeys, 'passkey') : 'email codes']
          .filter(Boolean).join(' · ') },
      { key: 'notifications', name: 'Notifications',
        sub: 'Payday, weekly check-in, progress, milestones', soon: true },
    ] },
    { title: 'Privacy', rows: [
      { key: 'consent', name: 'Privacy and consent',
        sub: 'What you’ve agreed to, and how to change it', soon: true },
      { key: 'data', name: 'Your data', sub: 'Download a copy or delete your account', soon: true },
      { key: 'protect', name: 'How we protect you', sub: 'What Pearl can and can’t do', soon: true },
    ] },
    { title: 'Help', rows: [
      { key: 'help', name: 'Help and support', soon: true },
      { key: 'legal', name: 'Privacy policy and terms', soon: true },
    ] },
  ];
}

export function ProfileHub({ summary, user, onTab, onUndoInvesting }) {
  const who = [user?.first_name || user?.username, user?.email].filter(Boolean).join(' · ');
  return (
    <div className="pk hm-page pf-page">
      <header className="pf-head">
        <p className="pk-overline">Profile</p>
        <h1 className="pk-h1">Profile</h1>
        {who && <p className="pk-muted">{who}</p>}
      </header>
      {hubRows(summary, user).map((group) => (
        <section className="pf-section" key={group.title} aria-labelledby={`pf-${group.title}`}>
          <h2 className="pk-h3" id={`pf-${group.title}`}>{group.title}</h2>
          <ul className="pf-list">
            {group.rows.map((r) => (
              <ListRow key={r.key} name={r.name} sub={r.sub} soon={r.soon}
                       onOpen={r.undo ? null : () => onTab?.(r.key)}
                       end={r.undo ? (
                         <button type="button" className="gl-more" onClick={onUndoInvesting}>Undo</button>
                       ) : r.needs > 0 && (
                         <StatusPill icon="alert" tone="caution">
                           <span className="pf-needs">{`${r.needs} needs you`}</span>
                         </StatusPill>
                       )} />
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

export default function ProfilePanel({ onTab, version }) {
  const [summary, setSummary] = useState(null);
  const [user, setUser] = useState(null);
  const [error, setError] = useState(null);
  const load = useCallback(() => {
    setError(null);
    return Promise.all([getProfileSummary(), getAuthStatus()])
      .then(([s, a]) => { setSummary(s); setUser(a.user ?? null); })
      .catch(setError);
  }, []);
  useEffect(() => { load(); }, [load, version]);
  if (error) return <div className="pk hm-page pf-page"><ErrorNote error={error} onRetry={load} /></div>;
  return (
    <ProfileHub summary={summary} user={user} onTab={onTab}
                onUndoInvesting={() => undoInvesting().then(load).catch(setError)} />
  );
}
