import { useCallback, useEffect, useState } from 'react';
import { ErrorNote } from '../components/ui.jsx';
import { getAuthStatus, getProfileSummary } from '../api.js';
import { DocSheet } from '../pearl/docs.jsx';
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
 * RulesPanel.jsx) and Income and bills (THL-45, THL-127,
 * IncomeBillsPanel.jsx) under Money; Sign-in and security
 * (SecurityPanel.jsx, with S-02) and Notifications (THL-139 N-02,
 * NotificationsPanel.jsx) under You; Privacy and consent (THL-117 CN-04,
 * ConsentPanel.jsx), Your data (THL-116 D-01 to D-04, DataPanel.jsx) and How
 * we protect you (THL-115 T-04, ProtectPanel.jsx) under Privacy. Help has no
 * pages of its own in the design: its two rows open the existing drafts
 * (pearl/docs.jsx) as a sheet.
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
    ] },
    { title: 'You', rows: [
      { key: 'security', name: 'Sign-in and security',
        sub: [user?.email, passkeys > 0 ? plural(passkeys, 'passkey') : 'email codes']
          .filter(Boolean).join(' · ') },
      { key: 'notifications', name: 'Notifications',
        sub: 'Payday, weekly check-in, progress, milestones' },
      // The sidebar's theme and sign-out moved here (2026-10-21): the Pearl
      // Handoff File's sidebar has neither.
      { key: 'theme', name: 'Appearance', theme: true, sub: 'Light or dark' },
      { key: 'signout', name: 'Sign out', signout: true, sub: 'On this device' },
    ] },
    { title: 'Privacy', rows: [
      { key: 'consent', name: 'Privacy and consent',
        sub: 'What you’ve agreed to, and how to change it' },
      { key: 'data', name: 'Your data', sub: 'Download a copy or delete your account' },
      { key: 'protect', name: 'How we protect you', sub: 'What Pearl can and can’t do' },
    ] },
    // No pages of their own: the drafts the sign-in screens already show.
    { title: 'Help', rows: [
      { key: 'help', name: 'Help and support', doc: 'help', sub: 'Signing in, and new devices' },
      { key: 'legal', name: 'Privacy policy and terms', doc: 'legal',
        sub: 'Plain-language drafts' },
    ] },
  ];
}

export function ProfileHub({ summary, user, onTab, onDoc, theme, setTheme, onSignOut }) {
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
                       onOpen={r.theme ? () => setTheme?.(theme === 'dark' ? 'light' : 'dark')
                         : r.signout ? () => onSignOut?.()
                           : r.doc ? () => onDoc?.(r.doc) : () => onTab?.(r.key)}
                       chevron={!r.theme && !r.signout}
                       end={r.theme ? (
                         <span className="pf-row-sub">{theme === 'dark' ? 'Dark' : 'Light'}</span>
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

export default function ProfilePanel({ onTab, version, theme, setTheme, onSignOut }) {
  const [summary, setSummary] = useState(null);
  const [user, setUser] = useState(null);
  const [error, setError] = useState(null);
  const [doc, setDoc] = useState(null);
  const load = useCallback(() => {
    setError(null);
    return Promise.all([getProfileSummary(), getAuthStatus()])
      .then(([s, a]) => { setSummary(s); setUser(a.user ?? null); })
      .catch(setError);
  }, []);
  useEffect(() => { load(); }, [load, version]);
  if (error) return <div className="pk hm-page pf-page"><ErrorNote error={error} onRetry={load} /></div>;
  return (
    <>
      <ProfileHub summary={summary} user={user} onTab={onTab} onDoc={setDoc}
                  theme={theme} setTheme={setTheme} onSignOut={onSignOut} />
      {doc && <DocSheet name={doc} onClose={() => setDoc(null)} />}
    </>
  );
}
