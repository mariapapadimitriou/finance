import { useEffect, useRef, useState } from 'react';
import { answerApproval, getApprovals } from '../api.js';
import PIcon from './icons.jsx';
import { Dialog, PButton } from './kit.jsx';

/**
 * Keeping a signed-in session private (Pearl THL-114).
 *
 * A-14: after 14 minutes with nothing touched, "Still there?" counts down the
 * last minute; at 15 she is signed out and lands on A-15 (SignedOut.jsx),
 * which returns her to the page she was on once she signs in again. Activity
 * in any of her open tabs counts, so a second tab isn't signed out under her.
 *
 * And the other half of A-07/A-08: when someone signs in on a new browser by
 * email code, her signed-in devices are asked whether it's her.
 */

export const WARN_AFTER = 14 * 60;
export const SIGN_OUT_AFTER = 15 * 60;
const ACTIVE_KEY = 'pearl-active';
const ACTIVITY = ['pointerdown', 'keydown', 'wheel', 'touchstart', 'scroll'];

/** Where idle time puts her: active, warned with seconds left, or out. */
export function idlePhase(idleSeconds) {
  if (idleSeconds >= SIGN_OUT_AFTER) return { phase: 'out', left: 0 };
  if (idleSeconds >= WARN_AFTER) {
    return { phase: 'warn', left: Math.ceil(SIGN_OUT_AFTER - idleSeconds) };
  }
  return { phase: 'active', left: null };
}

/** "0:58". */
export const clockWords = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;

/** What a screen reader hears: the time at 30 and at 10 seconds, no more. */
export function spokenLeft(left) {
  if (left == null || left > 30) return '';
  return left > 10 ? '30 seconds left' : '10 seconds left';
}

function sharedActive() {
  try { return Number(localStorage.getItem(ACTIVE_KEY)) || 0; } catch { return 0; }
}

/** A-14 Session timeout warning. `onTimeout` signs out and shows A-15. */
export function SessionTimeout({ onTimeout, onSignOut }) {
  const last = useRef(Date.now());
  const warned = useRef(false);
  const [left, setLeft] = useState(null);
  const timeout = useRef(onTimeout);
  timeout.current = onTimeout;

  const markActive = () => {
    const t = Date.now();
    // Written at most every few seconds; other tabs read it on their tick.
    if (t - last.current > 5000 || warned.current) {
      try { localStorage.setItem(ACTIVE_KEY, String(t)); } catch { /* this tab only */ }
    }
    last.current = t;
  };

  useEffect(() => {
    markActive();
    // While the warning is up only "Stay signed in" keeps her signed in.
    const onActivity = () => { if (!warned.current) markActive(); };
    ACTIVITY.forEach((e) => window.addEventListener(e, onActivity, { passive: true }));
    const tick = () => {
      const idle = (Date.now() - Math.max(last.current, sharedActive())) / 1000;
      const { phase, left: secs } = idlePhase(idle);
      if (phase === 'out') { timeout.current?.(); return; }
      warned.current = phase === 'warn';
      setLeft(phase === 'warn' ? secs : null);
    };
    const timer = setInterval(tick, 1000);
    document.addEventListener('visibilitychange', tick);
    return () => {
      ACTIVITY.forEach((e) => window.removeEventListener(e, onActivity));
      clearInterval(timer);
      document.removeEventListener('visibilitychange', tick);
    };
  }, []);

  if (left == null) return null;
  return (
    <TimeoutWarning left={left} onSignOut={onSignOut}
                    onStay={() => { warned.current = false; markActive(); setLeft(null); }} />
  );
}

/** The dialog itself, drawn from the seconds left. */
export function TimeoutWarning({ left, onStay, onSignOut }) {
  return (
    <Dialog role="alertdialog" labelledBy="pk-timeout-title" describedBy="pk-timeout-text"
            onClose={onStay} className="centered">
      <span className="pk-bubble" aria-hidden="true"><PIcon name="clock" /></span>
      <h2 className="pk-h2" id="pk-timeout-title">Still there?</h2>
      <p className="pk-muted" id="pk-timeout-text">
        You’ve been inactive for a while, so we’ll sign you out soon to keep your money private.
      </p>
      <p className="pk-amount pk-countdown" aria-hidden="true">{clockWords(left)}</p>
      <span className="pk-sr" aria-live="assertive">{spokenLeft(left)}</span>
      <div className="pk-dialog-stack">
        <PButton onClick={onStay}>Stay signed in</PButton>
        <PButton variant="text" onClick={onSignOut}>Sign out now</PButton>
      </div>
    </Dialog>
  );
}

// How often her signed-in devices look for a sign-in to approve (A-08 waits
// five minutes, so this is well inside it), and again whenever she comes back.
const APPROVALS_EVERY = 15000;

/** On her signed-in devices: "Is this you signing in?" (A-07, A-08). */
export function DeviceApprovals() {
  const [asking, setAsking] = useState(null);
  const [refused, setRefused] = useState(false);
  const [busy, setBusy] = useState(false);
  const seen = useRef(new Set());

  useEffect(() => {
    let live = true;
    const look = async () => {
      if (document.visibilityState === 'hidden') return;
      try {
        const { approvals } = await getApprovals();
        const next = approvals.find((a) => !seen.current.has(a.id)) ?? null;
        if (live && next) setAsking((now) => now ?? next);
      } catch { /* asked again on the next look */ }
    };
    look();
    const timer = setInterval(look, APPROVALS_EVERY);
    document.addEventListener('visibilitychange', look);
    return () => {
      live = false;
      clearInterval(timer);
      document.removeEventListener('visibilitychange', look);
    };
  }, []);

  if (!asking && !refused) return null;
  const close = () => {
    if (asking) seen.current.add(asking.id);
    setAsking(null);
    setRefused(false);
  };
  const reply = async (approve) => {
    setBusy(true);
    try {
      await answerApproval(asking.id, approve);
    } catch { /* expired: nothing left to answer */ }
    seen.current.add(asking.id);
    setBusy(false);
    setAsking(null);
    setRefused(!approve);
  };
  return refused ? <Refused onDone={close} />
    : <ApprovalPrompt approval={asking} busy={busy} onAnswer={reply} onClose={close} />;
}

/** The question, for one sign-in. */
export function ApprovalPrompt({ approval, busy = false, onAnswer, onClose }) {
  const where = approval.near ? `${approval.label}, near ${approval.near}` : approval.label;
  return (
    <Dialog labelledBy="pk-approve-title" onClose={onClose} className="centered">
      <span className="pk-bubble" aria-hidden="true"><PIcon name="phone" /></span>
      <p className="pk-overline accent">New device</p>
      <h2 className="pk-h2" id="pk-approve-title">Is this you signing in?</h2>
      <p className="pk-muted">{`${where}, just now. Only approve it if you’re signing in yourself.`}</p>
      <div className="pk-dialog-stack">
        <PButton disabled={busy} onClick={() => onAnswer(true)}>Approve</PButton>
        <PButton variant="text" disabled={busy} onClick={() => onAnswer(false)}>
          This wasn’t me
        </PButton>
      </div>
    </Dialog>
  );
}

/** After "This wasn't me". */
export function Refused({ onDone }) {
  return (
    <Dialog labelledBy="pk-refused-title" onClose={onDone} className="centered">
      <span className="pk-bubble" aria-hidden="true"><PIcon name="shield" /></span>
      <h2 className="pk-h2" id="pk-refused-title">We stopped that sign-in</h2>
      <p className="pk-muted">We’ve emailed you about it. Whoever it was had a code sent to your
        email, so change your email password.</p>
      <div className="pk-dialog-stack">
        <PButton variant="secondary" onClick={onDone}>Done</PButton>
      </div>
    </Dialog>
  );
}
