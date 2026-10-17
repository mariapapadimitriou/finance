import { useEffect, useState } from 'react';
import { Choice, DetailPanel, PButton } from '../pearl/kit.jsx';
import PIcon from '../pearl/icons.jsx';
import { getTxList, money } from '../api.js';

/**
 * Filters (VF-02, THL-231): a panel over the list with every filter the
 * toolbar doesn't show — months (this month, the last three, all), one
 * account, a category (ALT-04), what kind (Essentials · Lifestyle · Fixed ·
 * Variable), a tag
 * with its total, an amount range, and "show only": pending, needs a look,
 * doesn't count. The primary action says how many rows match before it's
 * applied.
 */

const KINDS = [['essentials', 'Essentials'], ['lifestyle', 'Lifestyle'], ['fixed', 'Fixed'],
               ['variable', 'Variable']];

function Chip({ on, children, onClick }) {
  return (
    <button type="button" className={`pk-filter tx-toggle${on ? ' active' : ''}`} aria-pressed={on}
            onClick={onClick}>
      {children}
    </button>
  );
}

/** The Category select's value ("g:lifestyle", "c:Coffee", "x:excluded")
 *  as the list's filters; a kind (Fixed, Variable) survives it. */
export function catFilters(cat, group = '') {
  const kind = ['fixed', 'variable'].includes(group) ? group : '';
  return {
    group: cat?.startsWith('g:') ? cat.slice(2) : kind,
    category: cat?.startsWith('c:') ? cat.slice(2) : '',
    excluded: cat === 'x:excluded' ? '1' : '',
    joint: cat === 'x:joint' ? '1' : '',
    recurring: cat === 'x:recurring' ? '1' : '',
  };
}

/** `filters` → the request the list makes (amount split into min and max). */
export function requestFor(f, thisMonth) {
  const { from, amount, by, cat, ...rest } = f;
  const out = { ...rest, by: by || '' };
  if (amount) {
    const [lo, hi] = amount.split('-');
    if (lo) out.amount_min = lo;
    if (hi) out.amount_max = hi;
  }
  if (out.month === thisMonth) out.month = thisMonth;
  return out;
}

export function TxFiltersPanel({ filters, thisMonth, accounts = [], tags = [], categoryOptions = [],
                                onApply, onClose }) {
  const [f, setF] = useState(filters);
  const [count, setCount] = useState(null);
  const [lo, setLo] = useState((filters.amount || '').split('-')[0] || '');
  const [hi, setHi] = useState((filters.amount || '').split('-')[1] || '');
  const set = (patch) => setF((x) => ({ ...x, ...patch }));
  const amount = lo || hi ? `${lo || ''}-${hi || ''}` : '';
  const current = { ...f, amount, ...(categoryOptions.length ? catFilters(f.cat, f.group) : {}) };

  useEffect(() => {
    let live = true;
    getTxList({ ...requestFor(current, thisMonth), limit: 1, offset: 0 })
      .then((r) => { if (live) setCount(r.total); }).catch(() => { if (live) setCount(null); });
    return () => { live = false; };
  }, [JSON.stringify(current)]);

  const kind = f.group && KINDS.some(([k]) => k === f.group) ? f.group : '';
  const clear = () => {
    setF((x) => ({ ...x, month: thisMonth, account: '', group: '', tag: '', counts: '', pending: '',
                   look: '', owed: '', cat: '' }));
    setLo(''); setHi('');
  };
  return (
    <DetailPanel label="Filters" overline="Filters" onClose={onClose}>
      <div className="txf">
        <section className="txf-group" aria-label="Months">
          <p className="pk-label">Months</p>
          <div className="txf-chips">
            <Chip on={f.month === thisMonth} onClick={() => set({ month: thisMonth })}>This month</Chip>
            <Chip on={f.month === 'last3'} onClick={() => set({ month: 'last3' })}>Last 3 months</Chip>
            <Chip on={f.month === 'all'} onClick={() => set({ month: 'all' })}>All months</Chip>
          </div>
        </section>
        <section className="txf-group" aria-label="Accounts">
          <p className="pk-label">Accounts</p>
          <div className="txf-chips">
            <Chip on={!f.account} onClick={() => set({ account: '' })}>All</Chip>
            {accounts.map((a) => (
              <Chip key={a.value} on={f.account === a.value} onClick={() => set({ account: a.value })}>
                {a.label}
              </Chip>
            ))}
          </div>
        </section>
        {categoryOptions.length > 0 && (
          <section className="txf-group" aria-label="Category">
            <label className="pk-label" htmlFor="txf-cat">Category</label>
            <select id="txf-cat" className="txf-select" value={f.cat || ''}
                    onChange={(e) => set({ cat: e.target.value, ...(e.target.value ? { group: KINDS.slice(2).some(([k]) => k === f.group) ? f.group : '' } : {}) })}>
              {categoryOptions.map((o) => (
                o.group
                  ? <optgroup key={o.group} label={o.group}>
                      {o.options.map((x) => <option key={x.value} value={x.value}>{x.label}</option>)}
                    </optgroup>
                  : <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </section>
        )}
        <section className="txf-group" aria-label="What kind">
          <p className="pk-label">What kind</p>
          <div className="txf-chips">
            {KINDS.map(([k, label]) => (
              <Chip key={k} on={kind === k} onClick={() => set({ group: kind === k ? '' : k, category: '' })}>
                {label}
              </Chip>
            ))}
          </div>
        </section>
        {tags.length > 0 && (
          <section className="txf-group" aria-label="Tags">
            <p className="pk-label">Tags</p>
            <div className="txf-chips">
              {tags.map((t) => (
                <Chip key={t.tag ?? t} on={f.tag === (t.tag ?? t)}
                      onClick={() => set({ tag: f.tag === (t.tag ?? t) ? '' : (t.tag ?? t) })}>
                  {t.tag ?? t}{t.spent != null ? ` · ${money(t.spent, { cents: true })}` : ''}
                </Chip>
              ))}
            </div>
          </section>
        )}
        <section className="txf-group" aria-label="Amount">
          <p className="pk-label">Amount</p>
          <div className="rg-dates">
            <div className="txd-field">
              <label className="pk-label pk-muted" htmlFor="txf-lo">From</label>
              <input id="txf-lo" inputMode="decimal" placeholder="$0" value={lo}
                     onChange={(e) => setLo(e.target.value.replace(/[^\d.]/g, ''))} />
            </div>
            <div className="txd-field">
              <label className="pk-label pk-muted" htmlFor="txf-hi">To</label>
              <input id="txf-hi" inputMode="decimal" placeholder="$500" value={hi}
                     onChange={(e) => setHi(e.target.value.replace(/[^\d.]/g, ''))} />
            </div>
          </div>
        </section>
        <section className="txf-group" aria-label="Show only">
          <p className="pk-label">Show only</p>
          <div className="pk-choices">
            <Choice type="checkbox" checked={!!f.pending} onChange={(on) => set({ pending: on ? '1' : '' })}
                    label="Pending" />
            <Choice type="checkbox" checked={!!f.look} onChange={(on) => set({ look: on ? '1' : '' })}
                    label="Needs a look" />
            <Choice type="checkbox" checked={!!f.owed} onChange={(on) => set({ owed: on ? '1' : '', ...(on ? { month: 'all' } : {}) })}
                    label="Owed to you" />
            <Choice type="checkbox" checked={f.counts === 'none'}
                    onChange={(on) => set({ counts: on ? 'none' : '' })}
                    label="Doesn’t count (transfers, left out)" />
          </div>
        </section>
      </div>
      <div className="txd-actions">
        <PButton onClick={() => onApply(current)}>
          {count == null ? 'Show transactions' : `Show ${count} transaction${count === 1 ? '' : 's'}`}
        </PButton>
        <PButton variant="secondary" onClick={clear}>
          <PIcon name="x" size={14} /> Clear filters
        </PButton>
      </div>
    </DetailPanel>
  );
}
