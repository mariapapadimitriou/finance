import { Dialog, PButton } from '../pearl/kit.jsx';
import { Mark } from './GoalsParts.jsx';
import { More } from './InsightsParts.jsx';

/**
 * The partner handoff, with its disclosure (Pearl THL-136, post-MVP). Built
 * behind configuration: a partner is PEARL_PARTNER_NAME and PEARL_PARTNER_URL
 * on the server, and without one GR-22 is what GR-16 shows.
 *
 * GR-16's right-hand card is where the handoff starts, and which card it is
 * depends on where she is:
 *   GR-23 Before Protect is done  "Opens after Protect", and Learn is open now.
 *   GR-22 No partner yet          "We're choosing a partner": a sign-up, and
 *                                 "I opened an account elsewhere" → GR-37.
 *   Partner configured            "Open your first account" with the partner:
 *                                 "See how it works" → GR-19, and "I've opened
 *                                 one" → GR-37 for an account opened anywhere.
 *   Already told Pearl            What she said, and a way to change it.
 * GR-19 Before you go   What happens next in three steps, and the affiliate
 *                       disclosure (THL-118) above the button, every time.
 * GR-20 Welcome back    On her return (?from=partner), or the next app open
 *                       up to 14 days after she went: did she open one?
 * GR-21 I opened one    Confirms, and records the same self-report as GR-37
 *                       (`via: partner`), then GR-10.
 *
 * The link out carries a tracking ID only: no transaction, balance or name
 * of hers goes to the partner (THL-13).
 */

/** GR-19 Before you go. */
export function BeforeYouGo({ name, busy = false, error = '', onGo, onClose }) {
  const steps = [
    { title: `You’ll leave Pearl for ${name}’s site`, text: 'A registered investment provider in Canada.' },
    { title: `${name} does the rest`,
      text: 'They check your ID, ask about your goals and suggest what fits. Pearl doesn’t recommend investments.' },
    { title: 'Come back and tell us', text: 'We’ll mark Unveil done.' },
  ];
  return (
    <Dialog labelledBy="gr-go-title" onClose={onClose}>
      <p className="pk-overline accent">Before you go</p>
      <h2 className="pk-h1 gr-dialog-title" id="gr-go-title">{`Open an account with ${name}`}</h2>
      <ol className="gr-go-steps">
        {steps.map((s, i) => (
          <li key={s.title}>
            <span className="gr-go-num" aria-hidden="true">{i + 1}</span>
            <span className="hm-row-text">
              <span className="pk-h3">{s.title}</span>
              <span className="pk-label pk-muted">{s.text}</span>
            </span>
          </li>
        ))}
      </ol>
      <div className="gr-disclosure">
        <p className="pk-h3">Pearl may be paid if you open an account.</p>
        <p className="pk-label">{`That’s how Pearl stays free. We never share your transactions or balances with ${name}.`}</p>
      </div>
      {error && <p className="pj-field-note" role="alert">{error}</p>}
      <div className="gr-dialog-actions">
        <button type="button" className="in-text-btn" onClick={onClose}>Not now</button>
        <PButton onClick={onGo} disabled={busy}>{busy ? 'Opening…' : `Continue to ${name}`}</PButton>
      </div>
    </Dialog>
  );
}

/** GR-20 Welcome back: the banner above Ready to invest. */
export function WelcomeBack({ name, onNotYet, onYes, busy = false }) {
  return (
    <section className="gr-welcome" aria-labelledby="gr-welcome-title">
      <div className="in-stack">
        <p className="pk-overline accent">Welcome back</p>
        <h2 className="pk-h2" id="gr-welcome-title">{`Did you open an account with ${name}?`}</h2>
      </div>
      <div className="gr-welcome-actions">
        <PButton variant="secondary" onClick={onNotYet} disabled={busy}>Not yet</PButton>
        <PButton onClick={onYes} disabled={busy}>Yes, I opened one</PButton>
      </div>
    </section>
  );
}

/** GR-21 I opened an account. */
export function OpenedOne({ busy = false, error = '', onConfirm, onClose }) {
  return (
    <Dialog labelledBy="gr-opened-title" onClose={onClose}>
      <Mark phase="unveil" width={77} />
      <h2 className="pk-h1 gr-dialog-title" id="gr-opened-title">You opened your first investment account</h2>
      <p className="pk-muted">We’ll mark Unveil done. We don’t see what you invest in or how much, and we won’t ask.</p>
      {error && <p className="pj-field-note" role="alert">{error}</p>}
      <div className="gr-dialog-actions">
        <button type="button" className="in-text-btn" onClick={onClose}>Go back</button>
        <PButton onClick={onConfirm} disabled={busy}>{busy ? 'Saving…' : 'Mark Unveil done'}</PButton>
      </div>
    </Dialog>
  );
}

/**
 * GR-16's right-hand card: GR-23 before Protect, GR-22 with no partner, the
 * partner's card when there is one. `primary` is false while GR-20's banner
 * holds the page's one primary action.
 */
export function PartnerCard({ partner, protectDone, primary = true, busy = false, onHow, onReport,
                              onNotify, onLearn }) {
  if (!protectDone) {
    return (
      <section className="hm-card in-card" aria-labelledby="gr-partner-title">
        <p className="pk-overline">Opens after Protect</p>
        <h2 className="pk-h2" id="gr-partner-title">Open your first account</h2>
        <p className="pk-label pk-muted">Once your income covers your Essentials for a month, this opens.
          Learning is open now.</p>
        <PButton variant="secondary" onClick={onLearn}>Start learning</PButton>
      </section>
    );
  }
  if (!partner?.configured) {
    return (
      <section className="hm-card in-card" aria-labelledby="gr-partner-title">
        <p className="pk-overline accent">Coming soon</p>
        <h2 className="pk-h2" id="gr-partner-title">We’re choosing a partner</h2>
        <p className="pk-label pk-muted">Pearl will only work with a provider registered in Canada. We’ll
          tell you when there’s one to suggest.</p>
        {partner?.notify ? (
          <p className="pk-label" role="status">You’re on the list. We’ll tell you when there’s a provider to
            suggest.</p>
        ) : (
          <PButton variant={primary ? 'primary' : 'secondary'} onClick={onNotify} disabled={busy}>
            Tell me when Pearl partners with a provider
          </PButton>
        )}
        <More onClick={onReport}>I opened an account elsewhere</More>
      </section>
    );
  }
  return (
    <section className="hm-card in-card" aria-labelledby="gr-partner-title">
      <p className="pk-overline accent">When you’re ready</p>
      <h2 className="pk-h2" id="gr-partner-title">Open your first account</h2>
      <p className="pk-label pk-muted">{`With ${partner.name}, a registered investment provider. They handle the account and any advice.`}</p>
      <p className="pk-label">Pearl may be paid if you open an account.</p>
      <PButton variant={primary ? 'primary' : 'secondary'} onClick={onHow}>See how it works</PButton>
      <More onClick={onReport}>I’ve opened one elsewhere</More>
    </section>
  );
}
