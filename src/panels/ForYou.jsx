import { DetailPanel, PButton } from '../pearl/kit.jsx';
import PIcon from '../pearl/icons.jsx';
import { shown } from './HomePanel.jsx';

/**
 * "For you" (THL-12 E08, designed in THL-133): RC-01 up to two cards under
 * the snapshot, RC-02 the four types, RC-03 "Why you're seeing this".
 *
 * Every card carries her numbers and says why it's there (THL-60, THL-61).
 * Its action is secondary everywhere, the RC-03 panel included (R1), so
 * Home's one primary stays the path's next step. "Not for me" hides the type
 * for 30 days, with Undo on the toast (THL-62). The rules and their
 * thresholds are in finance/recommendations.py.
 */

/** What the toast calls each type: "We won't show spending trend tips". */
export const TYPE_WORDS = { trend: 'spending trend', subscriptions: 'subscription',
                            pace: 'Anchor pace', idle: 'idle cash' };

export const dismissedWords = (type) => `Got it. We won’t show ${TYPE_WORDS[type] ?? 'these'} tips for 30 days.`;

export function ForYou({ cards, onAction, onWhy, onNotForMe }) {
  if (!cards?.length) return null;
  return (
    <section className="rc-section" aria-labelledby="rc-title">
      <h2 className="pk-h3" id="rc-title">For you</h2>
      {cards.map((c) => (
        <article key={c.type} className="hm-card rc-card" aria-labelledby={`rc-${c.type}`}>
          <p className="pk-overline">{c.label}</p>
          <h3 className="pk-h3" id={`rc-${c.type}`}>{c.title}</h3>
          <p className="pk-muted">{c.body}</p>
          <button type="button" className="hm-link rc-why" onClick={() => onWhy(c)}>
            Why you’re seeing this <PIcon name="chevronRight" size={14} />
          </button>
          <div className="rc-actions">
            <PButton variant="secondary" onClick={() => onAction(c)}>{c.action.label}</PButton>
            <button type="button" className="hm-link rc-not" onClick={() => onNotForMe(c)}>Not for me</button>
          </div>
        </article>
      ))}
    </section>
  );
}

/** RC-03: the numbers behind a card and the rule that showed it. */
export function WhyPanel({ card, onClose, onAction, onNotForMe }) {
  const w = card.why;
  return (
    <DetailPanel label="Why you’re seeing this" overline="Why you’re seeing this" onClose={onClose}>
      <div className="hm-form rc-why-panel">
        <h1 className="pk-h2">{w.title}</h1>
        <p>{w.text}</p>
        {w.lines.length > 0 && (
          <dl className="hm-facts rc-lines">
            {w.lines.map((l) => (
              <div key={l.label}>
                <dt>{l.label}</dt>
                <dd>{`${shown(l.monthly, true)} a month · ${shown(l.yearly)} a year`}</dd>
              </div>
            ))}
          </dl>
        )}
        <p className="pk-muted pk-label">{w.rule}</p>
        <div className="hm-sheet-foot rc-panel-foot">
          <PButton variant="secondary" onClick={() => onAction(card)}>{card.action.label}</PButton>
          <PButton variant="secondary" onClick={() => onNotForMe(card)}>Not for me</PButton>
        </div>
      </div>
    </DetailPanel>
  );
}
