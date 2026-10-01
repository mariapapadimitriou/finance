import { useCallback, useEffect, useRef, useState } from 'react';
import { Card, ErrorNote, Notice } from '../components/ui.jsx';
import { ask, getAskStatus } from '../api.js';

/**
 * Ask about your own spending.
 *
 * The rule engine below finds what it was written to find. This is for the
 * rest — the questions nobody could enumerate in advance, and the follow-up
 * to the answer.
 *
 * It reads; it never writes. No budget, category or transaction can be
 * changed from here, and every figure on every other tab is computed locally
 * whether this is switched on or not. Which tools it consulted are listed
 * under each answer, because an answer you cannot audit is worth less than
 * one you can.
 */
const SUGGESTIONS = [
  'What changed most between my last two months?',
  'Which subscriptions am I getting the least out of?',
  'Where is my "Other" spending actually going?',
  'Is my spending plan realistic given what I actually spend?',
];

export default function AskPanel() {
  const [state, setState] = useState(null);
  const [turns, setTurns] = useState([]);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const endRef = useRef(null);

  const load = useCallback(async () => {
    try {
      setState(await getAskStatus());
    } catch {
      setState({ available: false, detail: '' });
    }
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (turns.length) endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [turns]);

  async function send(question) {
    const text = (question ?? draft).trim();
    if (!text || busy) return;
    setBusy(true);
    setError(null);
    setDraft('');

    const asked = [...turns, { role: 'user', content: text }];
    setTurns(asked);

    try {
      // Only the completed turns are context; the question itself is sent
      // separately so the server can bound what it forwards.
      const r = await ask(text, turns.map(
        ({ role, content }) => ({ role, content })));
      if (r.error) {
        setError(new Error(r.error));
        setTurns(asked);
      } else {
        setTurns([...asked, {
          role: 'assistant', content: r.answer,
          consulted: r.consulted, truncated: r.truncated,
        }]);
      }
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  if (!state) return null;

  return (
    <Card title="Ask about your spending"
          hint={state.available
            ? 'Reads your ledger to answer; it can\'t change anything'
            : 'Optional — everything below is computed locally without it'}
          actions={turns.length > 0 && (
            <button className="btn quiet" onClick={() => setTurns([])}>
              Clear
            </button>
          )}>
      {!state.available ? (
        <Notice>{state.detail}</Notice>
      ) : (
        <>
          {turns.length === 0 && (
            <div className="controls" style={{ marginBottom: 14 }}>
              {SUGGESTIONS.map((q) => (
                <button key={q} className="btn quiet" disabled={busy}
                        onClick={() => send(q)}>
                  {q}
                </button>
              ))}
            </div>
          )}

          {turns.map((t, i) => (
            <div key={i} className={`turn ${t.role}`}>
              <div className="tile-label">
                {t.role === 'user' ? 'You' : 'Spendie'}
              </div>
              <div className="turn-body">
                {t.content.split('\n').filter(Boolean).map((para, j) => (
                  <p key={j}>{para}</p>
                ))}
                {t.truncated && (
                  <p className="small muted">
                    (cut off before it finished — ask for less at a time)
                  </p>
                )}
                {t.consulted?.length > 0 && (
                  <p className="small muted" style={{ marginBottom: 0 }}>
                    Looked at: {t.consulted.join(', ').replace(/_/g, ' ')}
                  </p>
                )}
              </div>
            </div>
          ))}

          {busy && (
            <div className="turn assistant">
              <div className="tile-label">Spendie</div>
              <div className="turn-body"><p className="muted">Looking…</p></div>
            </div>
          )}

          <div ref={endRef} />
          <ErrorNote error={error} />

          <form className="controls" style={{ marginTop: 14 }}
                onSubmit={(e) => { e.preventDefault(); send(); }}>
            <input type="text" value={draft} disabled={busy}
                   placeholder="Ask about a month, a merchant, a category…"
                   aria-label="Your question" style={{ flex: '1 1 260px' }}
                   onChange={(e) => setDraft(e.target.value)} />
            <button className="btn primary" type="submit"
                    disabled={busy || !draft.trim()}>
              {busy ? 'Asking…' : 'Ask'}
            </button>
          </form>

          <p className="assumption" style={{ marginBottom: 0 }}>
            It can read your categories, merchants, charges, budgets,
            subscriptions and plan — and change none of them. Aggregates and
            the fields of a charge are what reach Anthropic; there are no
            account numbers in this ledger to send. Treat the answers as a
            second opinion: the figures on every other tab are computed here,
            in code, and do not depend on this.
          </p>
        </>
      )}
    </Card>
  );
}
