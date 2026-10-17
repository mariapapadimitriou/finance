import { useEffect, useState } from 'react';
import { answerNotifyPrompt, getNotifications } from '../api.js';
import { DetailPanel, PButton, Toast } from '../pearl/kit.jsx';
import { PRIME_FOOT, PRIME_ROWS, Rows, milestoneKey, shouldPrime } from '../pearl/privacy.jsx';
import { Lockup } from '../pearl/ui.jsx';

/**
 * N-01 Want a heads-up at the right moments? (THL-139): asked on Home once
 * Allowance first has a number, and once more after a "Not now" when she
 * reaches a milestone on her path — then only in Profile › Notifications.
 *
 * The design draws it for the iOS app. On the web it is a sheet over Home,
 * and turning notifications on saves the choice for that app; the note
 * afterwards says so, since nothing arrives in a browser.
 */

export function PrimeSheet({ onOn, onNotNow, busy = false }) {
  return (
    <DetailPanel label="Notifications" overline="" onClose={onNotNow} className="pf-dialog nt-prime" sheet>
      <Lockup />
      <h1 className="pk-h2">Want a heads-up at the right moments?</h1>
      <Rows rows={PRIME_ROWS} label="What you’d hear about" />
      <p className="pf-foot">{PRIME_FOOT}</p>
      <PButton onClick={onOn} disabled={busy}>Turn on notifications</PButton>
      <PButton variant="text" onClick={onNotNow} disabled={busy}>Not now</PButton>
    </DetailPanel>
  );
}

export default function NotifyPrime({ sts, path }) {
  const [prompt, setPrompt] = useState(undefined);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState(null);
  const [gone, setGone] = useState(false);
  useEffect(() => {
    let live = true;
    getNotifications().then((r) => { if (live) setPrompt(r.prefs?.prompt ?? null); })
      .catch(() => { if (live) setPrompt(null); });
    return () => { live = false; };
  }, []);

  const answer = (a) => {
    setBusy(true);
    answerNotifyPrompt(a, milestoneKey(path))
      .then(() => {
        if (a === 'on') setNote('Saved. Notifications come from Pearl’s iPhone app once it’s out.');
      })
      .catch(() => {})
      .finally(() => { setBusy(false); setGone(true); });
  };

  const show = !gone && prompt !== undefined && prompt !== null && shouldPrime(prompt, sts, path);
  return (
    <>
      {show && <PrimeSheet busy={busy} onOn={() => answer('on')} onNotNow={() => answer('not_now')} />}
      {note && <Toast onDone={() => setNote(null)} ms={4000}>{note}</Toast>}
    </>
  );
}
