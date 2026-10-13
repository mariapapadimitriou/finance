import { useCallback, useEffect, useState } from 'react';
import { ErrorNote } from '../components/ui.jsx';
import { getNotifications, saveNotifications } from '../api.js';
import { Choice } from '../pearl/kit.jsx';
import { NOTIFY_TYPES } from '../pearl/privacy.jsx';
import { Field } from './GoalsParts.jsx';
import { PageHead } from './ProfilePanel.jsx';
import './home.css';
import './profile.css';

/**
 * Profile › Notifications (THL-139 N-02): which moments, by phone and by
 * email, quiet hours, and amounts on the lock screen. Saved on the server as
 * soon as she changes one (`users.set_notifications`).
 *
 * Push is the iOS app's (no web push, per E12), and that app isn't out yet,
 * so the page says the Phone choices are kept for it. Email is only for
 * someone who said yes to email from Pearl (CN-03); until then the Email
 * boxes are off and the page points to Privacy and consent.
 */

const TRAIL = [{ label: 'Profile', to: 'profile' }, { label: 'Notifications' }];

/** Every half hour, as "9:00 pm". */
export const TIMES = Array.from({ length: 48 }, (_, i) => {
  const h = Math.floor(i / 2);
  const m = i % 2 ? '30' : '00';
  const value = `${String(h).padStart(2, '0')}:${m}`;
  const label = `${h % 12 === 0 ? 12 : h % 12}:${m} ${h < 12 ? 'am' : 'pm'}`;
  return { value, label };
});

export function NotificationsPage({ data, onTab, onChange }) {
  const prefs = data?.prefs;
  const emailOk = !!data?.email_ok;
  if (!prefs) return null;
  const set = (key, channel) => (on) => onChange({ types: { [key]: { [channel]: on } } });
  return (
    <div className="pk hm-page pf-page pv-page">
      <PageHead trail={TRAIL} title="Notifications" onTab={onTab}>
        <p className="pf-intro">
          We only nudge you at useful moments: at most 3 a week, never about overspending.
        </p>
      </PageHead>
      <section className="pf-section" aria-labelledby="nt-get">
        <h2 className="pk-h3" id="nt-get">What you get</h2>
        <ul className="pf-list">
          {NOTIFY_TYPES.map((t) => (
            <li className="pf-row static nt-row" key={t.key}>
              <div className="pf-row-main">
                <span className="pf-row-text">
                  <span className="pf-row-name">{t.title}</span>
                  <span className="pf-row-sub">{t.sub}</span>
                </span>
                <span className="nt-channels" role="group" aria-label={`${t.title}: how`}>
                  <Choice type="checkbox" label="Phone" checked={prefs.types[t.key].phone}
                          onChange={set(t.key, 'phone')} />
                  <Choice type="checkbox" label="Email" disabled={!emailOk}
                          checked={emailOk && prefs.types[t.key].email}
                          onChange={set(t.key, 'email')} />
                </span>
              </div>
            </li>
          ))}
        </ul>
        <p className="pf-foot">
          Phone notifications come from Pearl’s iPhone app, which isn’t out yet. Your choices are
          kept for when it is.
        </p>
        {!emailOk && (
          <p className="pf-foot">
            {'Email is for people who said yes to email from Pearl. '}
            <button type="button" className="pf-text-link" onClick={() => onTab?.('consent')}>
              Turn it on in Privacy and consent
            </button>
          </p>
        )}
      </section>
      <section className="pf-section" aria-labelledby="nt-quiet">
        <h2 className="pk-h3" id="nt-quiet">Quiet hours</h2>
        <div className="nt-quiet">
          {[['from', 'From'], ['to', 'To']].map(([end, label]) => (
            <Field key={end} label={label} id={`nt-quiet-${end}`}>
              <select id={`nt-quiet-${end}`} value={prefs.quiet[end]}
                      onChange={(e) => onChange({ quiet: { [end]: e.target.value } })}>
                {TIMES.map((x) => <option key={x.value} value={x.value}>{x.label}</option>)}
              </select>
            </Field>
          ))}
        </div>
      </section>
      <section className="pf-section" aria-labelledby="nt-lock">
        <h2 className="pk-h3" id="nt-lock">Lock screen</h2>
        <div className="pk-choices pv-choices">
          <Choice type="checkbox" checked={prefs.lock_amounts}
                  onChange={(on) => onChange({ lock_amounts: on })}
                  label="Show amounts on my lock screen"
                  description="Off: “Your pay arrived.” On: “Your pay of $2,140 arrived.”" />
        </div>
      </section>
    </div>
  );
}

/** Deep-merge a change into the preferences, for showing it before it saves. */
export function applyChange(prefs, change) {
  const next = { ...prefs, types: { ...prefs.types }, quiet: { ...prefs.quiet, ...(change.quiet ?? {}) } };
  Object.entries(change.types ?? {}).forEach(([k, v]) => { next.types[k] = { ...next.types[k], ...v }; });
  if ('lock_amounts' in change) next.lock_amounts = change.lock_amounts;
  return next;
}

export default function NotificationsPanel({ onTab, version }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const load = useCallback(() => {
    setError(null);
    return getNotifications().then(setData).catch(setError);
  }, []);
  useEffect(() => { load(); }, [load, version]);

  const change = (c) => {
    setError(null);
    setData((d) => ({ ...d, prefs: applyChange(d.prefs, c) }));
    saveNotifications(c).then(setData).catch((e) => { setError(e); load(); });
  };

  if (!data && error) return <div className="pk hm-page pf-page"><ErrorNote error={error} onRetry={load} /></div>;
  if (!data) return <div className="pk hm-page pf-page"><p className="pk-muted" role="status">Loading…</p></div>;
  return (
    <>
      {error && <div className="pk"><ErrorNote error={error} /></div>}
      <NotificationsPage data={data} onTab={onTab} onChange={change} />
    </>
  );
}
