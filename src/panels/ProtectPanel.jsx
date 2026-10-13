import { useCallback, useEffect, useState } from 'react';
import { ErrorNote } from '../components/ui.jsx';
import { getPrivacy } from '../api.js';
import { DocSheet } from '../pearl/docs.jsx';
import { StatusPill } from '../pearl/kit.jsx';
import { ProtectPoints } from '../pearl/privacy.jsx';
import { bankInitials, updatedWords } from './AccountsPanel.jsx';
import { PageHead } from './ProfilePanel.jsx';
import './home.css';
import './profile.css';

/**
 * Profile › How we protect you (THL-115 T-04): the trust points from
 * onboarding (T-01, shared in pearl/privacy.jsx), with "What we store" (T-02)
 * and "Who we share with" (T-03) as side sheets, her live bank connections,
 * and a way to reach a person.
 *
 * The design's breadcrumb reads "Profile › Security › How we protect you";
 * the hub lists this page under Privacy, so the crumb names the hub only.
 */

const TRAIL = [{ label: 'Profile', to: 'profile' }, { label: 'How we protect you' }];

const PILL = {
  healthy: { label: 'Healthy', tone: 'positive', icon: 'check' },
  needs_sign_in: { label: 'Sign in again', tone: 'caution', icon: 'alert' },
  bank_down: { label: 'We’re retrying', tone: 'info', icon: 'info' },
  disconnected: { label: 'Disconnected', tone: 'neutral', icon: null },
};

const plural = (n, one) => `${n} ${n === 1 ? one : `${one}s`}`;

/** "TD · 3 accounts" and "Read-only through Plaid · synced 5 minutes ago". */
export function connectionWords(c, now = Date.now()) {
  const synced = updatedWords(c.last_synced, now);
  return {
    name: c.accounts > 0 ? `${c.institution} · ${plural(c.accounts, 'account')}` : c.institution,
    sub: ['Read-only through Plaid', synced && `synced ${synced}`].filter(Boolean).join(' · '),
  };
}

export function ProtectPage({ privacy, onTab, onDoc, now = Date.now() }) {
  const connections = privacy?.connections ?? [];
  const contact = privacy?.contact;
  return (
    <div className="pk hm-page pf-page pv-page">
      <PageHead trail={TRAIL} title="How we protect you" onTab={onTab}>
        <p className="pf-intro">
          What Pearl can and can’t do with your bank, and what happens to your data.
        </p>
      </PageHead>
      <ProtectPoints onDoc={onDoc} />
      {privacy && (
        <section className="pf-section" aria-labelledby="pt-conn">
          <h2 className="pk-h3" id="pt-conn">Your connections</h2>
          {connections.length > 0 ? (
            <ul className="pf-list">
              {connections.map((c) => {
                const words = connectionWords(c, now);
                const pill = PILL[c.state] ?? PILL.healthy;
                return (
                  <li className="pf-row static" key={c.item_id}>
                    <div className="pf-row-main">
                      <span className="pk-avatar" aria-hidden="true">
                        {bankInitials({ institution: c.institution })}
                      </span>
                      <span className="pf-row-text">
                        <span className="pf-row-name">{words.name}</span>
                        <span className="pf-row-sub">{words.sub}</span>
                      </span>
                      <span className="pf-row-end">
                        <StatusPill icon={pill.icon} tone={pill.tone}>{pill.label}</StatusPill>
                      </span>
                    </div>
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="pk-muted">No banks are linked, so Pearl can’t see any.</p>
          )}
        </section>
      )}
      {contact && (
        <div className="pf-stack pv-wide">
          <a className="pk-btn secondary" href={`mailto:${contact}`}>Contact a person</a>
        </div>
      )}
    </div>
  );
}

export default function ProtectPanel({ onTab, version }) {
  const [privacy, setPrivacy] = useState(null);
  const [error, setError] = useState(null);
  const [doc, setDoc] = useState(null);
  const load = useCallback(() => {
    setError(null);
    return getPrivacy().then(setPrivacy).catch(setError);
  }, []);
  useEffect(() => { load(); }, [load, version]);
  return (
    <>
      {error && <div className="pk"><ErrorNote error={error} onRetry={load} /></div>}
      <ProtectPage privacy={privacy} onTab={onTab} onDoc={setDoc} />
      {doc && <DocSheet name={doc} onClose={() => setDoc(null)} backLabel="How we protect you" />}
    </>
  );
}
