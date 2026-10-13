import { useCallback, useEffect, useState } from 'react';
import { ErrorNote } from '../components/ui.jsx';
import { getPrivacy, setConsent } from '../api.js';
import { DocSheet } from '../pearl/docs.jsx';
import { Alert, Choice, DetailPanel, PButton, Toast } from '../pearl/kit.jsx';
import { AI_OFF, Rows, agreedWords } from '../pearl/privacy.jsx';
import { openDataAt } from './DataPanel.jsx';
import { ListRow, PageHead } from './ProfilePanel.jsx';
import './home.css';
import './profile.css';

/**
 * Profile › Privacy and consent (THL-117 CN-04), and CN-05 Turn off AI
 * sorting.
 *
 * What she agreed to, each with its date. The two Pearl needs offer "Manage
 * accounts" and "Withdraw" — withdrawing is deleting the account (THL-116
 * D-03). The optional ones untick at once and every change is logged with
 * its time on the server (`users.record_consents`); turning AI sorting off
 * asks first (CN-05). These choices moved here from Sign-in and security.
 *
 * The design's "Version 1.0" of the privacy policy isn't true yet: the policy
 * is a plain-language draft, and the row says so.
 */

const TRAIL = [{ label: 'Profile', to: 'profile' }, { label: 'Privacy and consent' }];
const LINK = (words) => <span className="pf-end-link">{words}</span>;

export function ConsentPage({ privacy, onTab, onToggle, onDoc, onWithdraw, busy = null }) {
  const c = privacy?.consents ?? {};
  const ai = c.ai_sort ?? {};
  return (
    <div className="pk hm-page pf-page pv-page">
      <PageHead trail={TRAIL} title="Privacy and consent" onTab={onTab}>
        <p className="pf-intro">What you’ve agreed to. Change your mind any time.</p>
      </PageHead>
      <section className="pf-section" aria-labelledby="cn-need">
        <h2 className="pk-h3" id="cn-need">Needed for Pearl to work</h2>
        <ul className="pf-list">
          <ListRow name="Reading your linked accounts" sub={agreedWords(c.read_data)}
                   end={LINK('Manage accounts')} onOpen={() => onTab?.('accounts')} />
          <ListRow name="Working out your numbers" sub={agreedWords(c.insights)}
                   end={LINK('Withdraw')} onOpen={onWithdraw} />
        </ul>
      </section>
      <section className="pf-section" aria-labelledby="cn-choice">
        <h2 className="pk-h3" id="cn-choice">Your choice</h2>
        <div className="pk-choices pv-choices">
          <Choice type="checkbox" checked={!!ai.value} disabled={busy === 'ai_sort'}
                  onChange={(on) => onToggle?.('ai_sort', on)}
                  label="Sorting transactions with AI"
                  description={`${agreedWords(ai)} · merchant, amount and date only`} />
          <Choice type="checkbox" checked={!!c.tips?.value} disabled={busy === 'tips'}
                  onChange={(on) => onToggle?.('tips', on)}
                  label="Tips and news by email" description={agreedWords(c.tips)} />
          <Choice type="checkbox" checked={c.analytics?.value !== false}
                  disabled={busy === 'analytics'}
                  onChange={(on) => onToggle?.('analytics', on)}
                  label="Help improve Pearl"
                  description="Anonymous usage data. Never amounts, merchants or account details." />
        </div>
      </section>
      <section className="pf-section" aria-labelledby="cn-rights">
        <h2 className="pk-h3" id="cn-rights">Your rights</h2>
        <ul className="pf-list">
          {privacy?.contact && (
            <ListRow name="See or correct what we hold" sub="Our privacy officer replies within 30 days"
                     end={LINK('Ask')}
                     onOpen={() => { window.location.href = `mailto:${privacy.contact}`; }} />
          )}
          <ListRow name="Privacy policy" sub="Plain-language draft · October 2026"
                   end={LINK('Read')} onOpen={() => onDoc?.('privacy')} />
        </ul>
      </section>
    </div>
  );
}

/** CN-05: before AI sorting goes off. */
export function AiOffDialog({ onClose, onConfirm, busy = false, error = null }) {
  return (
    <DetailPanel label={AI_OFF.title} overline="" onClose={onClose} className="pf-dialog" sheet>
      <h1 className="pk-h2">{AI_OFF.title}</h1>
      <p className="pk-muted">{AI_OFF.body}</p>
      <Rows rows={AI_OFF.rows} />
      {error && <Alert tone="caution">{error}</Alert>}
      <PButton onClick={onConfirm} disabled={busy}>{busy ? 'Turning it off…' : 'Turn it off'}</PButton>
      <PButton variant="text" onClick={onClose}>Keep it on</PButton>
    </DetailPanel>
  );
}

const NAMES = { ai_sort: 'AI sorting', tips: 'Tips and news by email', analytics: 'Usage data' };

export default function ConsentPanel({ onTab, version }) {
  const [privacy, setPrivacy] = useState(null);
  const [error, setError] = useState(null);
  const [doc, setDoc] = useState(null);
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(null);
  const [note, setNote] = useState(null);
  const load = useCallback(() => {
    setError(null);
    return getPrivacy().then(setPrivacy).catch(setError);
  }, []);
  useEffect(() => { load(); }, [load, version]);

  async function change(key, value) {
    setBusy(key);
    setError(null);
    try {
      setPrivacy(await setConsent(key, value));
      setNote(`${NAMES[key]} turned ${value ? 'on' : 'off'}.`);
      setAsking(false);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(null);
    }
  }
  const toggle = (key, value) => {
    if (key === 'ai_sort' && !value) setAsking(true);
    else change(key, value);
  };

  if (!privacy && error) return <div className="pk hm-page pf-page"><ErrorNote error={error} onRetry={load} /></div>;
  if (!privacy) return <div className="pk hm-page pf-page"><p className="pk-muted" role="status">Loading…</p></div>;
  return (
    <>
      {error && !asking && <div className="pk"><ErrorNote error={error} /></div>}
      <ConsentPage privacy={privacy} onTab={onTab} onToggle={toggle} onDoc={setDoc} busy={busy}
                   onWithdraw={() => { openDataAt('delete'); onTab?.('data'); }} />
      {asking && (
        <div className="pk">
          <AiOffDialog onClose={() => setAsking(false)} busy={busy === 'ai_sort'}
                       error={error?.message} onConfirm={() => change('ai_sort', false)} />
        </div>
      )}
      {doc && <DocSheet name={doc} onClose={() => setDoc(null)} />}
      {note && <div className="pk"><Toast onDone={() => setNote(null)}>{note}</Toast></div>}
    </>
  );
}
