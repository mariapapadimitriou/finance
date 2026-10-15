import { useState } from 'react';
import { LENSES, LensToggle, lensLegend, trendForLens, whereForLens } from './Lens.jsx';
import { Choice, FilterChip, PButton } from '../pearl/kit.jsx';
import PIcon from '../pearl/icons.jsx';
import {
  CategoryBars, Donut, IncomeBar, InOutBars, Legend, SavingsArea, TrendBars,
} from './InsightsCharts.jsx';
import { CatDot, MonthSwitcher } from './InsightsParts.jsx';
import {
  addMonths, bandWords, cash, cashCents, compareText, count, dayLong, groupRows, keptSentence,
  keptWords, lastFullMonth, listWords, monthFull, monthShort, monthYear, savingsWords, topCategory,
  trendSentence, unsureWords, whereTitle,
} from './insightsMath.js';

/**
 * The detail views behind Growth › Insights (InsightsPanel.jsx), each at its
 * own address under /growth/insights:
 *
 * GR-25 (THL-81) /month      Review a past month: where the income went as
 *                            one bar, categories against usual in words, and
 *                            "Leave September out of my usual" (THL-59).
 * GR-26 (THL-186) /category  One category, six months, the usual month as a
 *                            dashed line and months above it in champagne.
 * GR-27 (THL-63) /subscriptions  Each subscription by the year; Keep or
 *                            Review, which only reminds her next month.
 * GR-29 (THL-188) /trend     6 or 12 months of Essentials and Lifestyle over
 *                            her usual month as a band.
 * GR-30 (THL-189) /where     A month's categories round a ring, by group,
 *                            each one opening its transactions; categories
 *                            Pearl isn't sure of are dashed (AI).
 * GR-31 (THL-190) /money     Money in beside spent and set aside, and what
 *                            she kept once each month ended.
 * GR-32 (THL-193) /savings   The Anchor and each chest stacked over time,
 *                            and when a chest paid for something.
 */

/** "‹ Insights", the overline and the title every detail view opens with. */
function DetailHead({ nav, overline = 'Insights', title, aside = null, corner = null }) {
  return (
    <header className="in-detail-head">
      <div className="in-back-row">
        <button type="button" className="in-back" onClick={() => nav.show('')}>
          <PIcon name="chevronRight" size={12} className="in-flip" /> Insights
        </button>
        {corner}
      </div>
      <div className="in-top">
        <div className="hm-head">
          {overline && <p className="pk-overline accent">{overline}</p>}
          <h1 className="pk-h1">{title}</h1>
        </div>
        {aside}
      </div>
    </header>
  );
}

/** The months either side of `month` for a past-month switcher. */
function neighbours(d, month) {
  const first = d.months[0];
  const prev = month > first ? addMonths(month, -1) : null;
  const after = addMonths(month, 1);
  const now = d.months[d.months.length - 1];
  return { prev, next: after <= now ? { month: after, current: after === now } : null };
}

// ── GR-25 Review a past month ─────────────────────────────────────────────

export function ReviewMonth({ d, nav }) {
  const [all, setAll] = useState(false);
  const [saving, setSaving] = useState(false);
  const month = d.month;
  const name = monthFull(month);
  const { prev, next } = neighbours(d, month);
  const went = d.income_went;
  const rows = d.categories.filter((c) => c.spent > 0 || c.usual);
  const shown = all ? rows : rows.slice(0, 5);
  const leftOut = d.usual.unusual.length;
  const toggle = (on) => {
    setSaving(true);
    nav.onUnusual(month, on).finally(() => setSaving(false));
  };
  return (
    <div className="pk hm-page in-page">
      <DetailHead nav={nav} overline={null} title={d.running ? `${name} so far` : `Your ${name}`}
                  corner={(
                    <MonthSwitcher label={d.running ? `${name} so far` : monthYear(month)} prev={prev} next={next}
                                   onPrev={() => nav.show('month', { month: prev })}
                                   onNext={() => (next.current ? nav.show('') : nav.show('month', { month: next.month }))} />
                  )} />

      <section className="hm-card in-card" aria-labelledby="in-went-title">
        <div className="in-card-head">
          <h2 className="pk-h2" id="in-went-title">
            {went.income > 0 ? `Income ${cash(went.income)}` : `No income arrived in ${name}`}
          </h2>
          <span className="pk-label pk-muted">Where it went</span>
        </div>
        {went.essentials + went.lifestyle + went.set_aside + went.left_over > 0
          ? <IncomeBar went={went} month={month} />
          : <p className="pk-muted">{`Nothing came in or went out in ${name}.`}</p>}
        {went.short > 0 && (
          <p className="pk-label pk-muted">{`${cash(went.short)} more went out than came in as income.`}</p>
        )}
      </section>

      <section className="hm-card in-card" aria-labelledby="in-cats-title">
        <h2 className="pk-sr" id="in-cats-title">{`${name} by category, against your usual`}</h2>
        {rows.length === 0 ? <p className="pk-muted">{`Nothing spent in ${name}.`}</p> : (
          <table className="in-table">
            <thead>
              <tr>
                <th scope="col">Category</th>
                <th scope="col" className="in-num">{name}</th>
                <th scope="col" className="in-num">Usual</th>
                <th scope="col" className="in-words"><span className="pk-sr">Against usual</span></th>
              </tr>
            </thead>
            <tbody>
              {shown.map((c) => (
                <tr key={c.category}>
                  <th scope="row">
                    {c.category}
                    <span className="in-words-inline pk-label pk-muted">
                      {c.spent > 0 ? compareText(c.words) : 'None this month'}
                    </span>
                  </th>
                  <td className="in-num">{c.spent > 0 ? cash(c.spent) : 'Nothing'}</td>
                  <td className="in-num pk-muted">{c.usual ? cash(c.usual) : '—'}</td>
                  <td className="pk-label pk-muted in-words">{c.spent > 0 ? compareText(c.words) : 'None this month'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {rows.length > 5 && (
          <button type="button" className="in-more" aria-expanded={all} onClick={() => setAll(!all)}>
            {all ? 'Show the largest 5' : `All ${count(rows.length, 'category', 'categories')}`}
            <span aria-hidden="true">  ›</span>
          </button>
        )}
      </section>

      {!d.running && (
        <div className="in-leave">
          <Choice type="checkbox" checked={d.usual.month_unusual} disabled={saving}
                  onChange={toggle} label={`Leave ${name} out of my usual`}
                  description={leftOut === 1 ? '1 month left out of your usual right now'
                    : `${leftOut} months left out of your usual right now`} />
        </div>
      )}
    </div>
  );
}

// ── GR-26 A category against usual ────────────────────────────────────────

export function CategoryView({ d, route, nav }) {
  const live = d.categories.filter((c) => c.history.some((h) => h.amount > 0));
  const name = route.category && live.some((c) => c.category === route.category)
    ? route.category : topCategory(live);
  const c = live.find((x) => x.category === name);
  if (!c) {
    return (
      <div className="pk hm-page in-page">
        <DetailHead nav={nav} title="By category" />
        <section className="hm-card in-card"><p className="pk-muted">No spending in the last six months yet.</p></section>
      </div>
    );
  }
  const lower = c.category.toLowerCase();
  const month = monthFull(d.month);
  const usualMonths = d.usual.months.map(monthFull);
  const sentence = [
    c.spent > 0 ? `${cash(c.spent)} so far in ${month}.` : `Nothing on ${lower} so far in ${month}.`,
    c.by_today > 0 ? `By ${dayLong(d.today)} you usually spend ${cash(c.by_today)}.`
      : c.usual ? `You usually spend ${cash(c.usual)} in a month.` : '',
  ].filter(Boolean).join(' ');
  return (
    <div className="pk hm-page in-page">
      <DetailHead nav={nav} overline={c.group === 'essentials' ? 'Essentials' : 'Lifestyle'} title={c.category} />
      <FilterChip label="Category" value={c.category} onChange={(v) => nav.show('category', { category: v })}
                  options={live.map((x) => ({ value: x.category, label: x.category }))} />
      <section className="hm-card in-card in-wide" aria-label={`${c.category} against your usual`}>
        <p>{sentence}</p>
        <CategoryBars history={c.history} usual={c.usual} name={c.category} />
        <p className="pk-label pk-muted">
          {c.usual
            ? `Usual month: ${cash(c.usual)} (average of ${listWords(usualMonths)}${
              d.usual.left_out.length ? '; unusual months left out' : ''})`
            : 'Your usual month for this appears once a full month is in.'}
        </p>
      </section>
      <div className="in-actions">
        <PButton variant="secondary" onClick={() => nav.toTransactions({ month: d.month, category: c.category })}>
          See the transactions
        </PButton>
        <button type="button" className="in-text-btn" onClick={() => nav.onTab?.('budgets')}>
          {`Set a budget for ${lower}`}
        </button>
      </div>
    </div>
  );
}

// ── GR-27 Subscriptions per year ─────────────────────────────────────────

export function SubscriptionsView({ d, nav }) {
  const s = d.subscriptions;
  const [busy, setBusy] = useState(null);
  const choose = (merchant, choice) => {
    setBusy(merchant);
    nav.onChoice(merchant, choice).finally(() => setBusy(null));
  };
  const next = monthFull(addMonths(d.month, 1));
  return (
    <div className="pk hm-page in-page">
      <DetailHead nav={nav} title="Your subscriptions"
                  aside={s.count > 0 && (
                    <div className="in-subs-total">
                      <p className="pk-h2">{`${cash(s.yearly)} a year`}</p>
                      <p className="pk-label pk-muted">
                        {`${count(s.count, 'subscription')} · about ${cash(s.monthly)} a month`}
                      </p>
                    </div>
                  )} />
      {s.count === 0 ? (
        <section className="hm-card in-card">
          <p className="pk-muted">
            No subscriptions spotted yet. Pearl looks for streaming, news, software and gym charges that come back every month or year.
          </p>
        </section>
      ) : (
        <section className="hm-card in-card in-subs-list" aria-label="Your subscriptions by the year">
          <ul>
            {s.rows.map((r) => (
              <li key={r.merchant} className="in-sub">
                <span className="in-sub-name pk-h3">{r.merchant}</span>
                <span className="pk-label pk-muted in-sub-month">{`${cashCents(r.monthly)} a month`}</span>
                <span className="in-sub-year">{`${cash(r.yearly)} a year`}</span>
                <span className="in-sub-choice">
                  <span className="in-seg" role="radiogroup" aria-label={`Keep or review ${r.merchant}`}>
                    {['keep', 'review'].map((choice) => (
                      <button key={choice} type="button" role="radio" aria-checked={r.choice === choice}
                              disabled={busy === r.merchant}
                              onClick={() => choose(r.merchant, r.choice === choice ? null : choice)}>
                        {choice === 'keep' ? 'Keep' : 'Review'}
                      </button>
                    ))}
                  </span>
                  {r.choice === 'review' && (
                    <span className="pk-label pk-muted">{`We’ll remind you in ${monthFull(r.remind) || next}`}</span>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
      <p className="pk-label pk-muted">
        Pearl never cancels anything for you. Marking “Review” just reminds you next month.
      </p>
    </div>
  );
}

// ── GR-29 Spending trend ─────────────────────────────────────────────────

export function TrendView({ d, nav }) {
  const lens = nav.lens ?? 'need';
  const span = Number(nav.filters?.span) || 12;
  const setSpan = (n) => nav.setFilter?.({ span: n === 12 ? '' : String(n) });
  const months = trendForLens(d.trend.months.slice(-span), lens);
  const last = lastFullMonth(d);
  const any = months.some((m) => m.total > 0);
  return (
    <div className="pk hm-page in-page">
      <DetailHead nav={nav} title="Your spending trend" />
      <div className="in-filters">
        <LensToggle lens={lens} onChange={(l) => nav.setLens?.(l)} />
        <div className="in-pills" role="radiogroup" aria-label="How many months">
          {[3, 6, 12].map((n) => (
            <button key={n} type="button" role="radio" aria-checked={span === n} className="in-tab"
                    onClick={() => setSpan(n)}>{`${n} months`}</button>
          ))}
        </div>
      </div>
      <section className="hm-card in-card in-wide" aria-label="Spending trend">
        {any ? (
          <>
            {lens === 'need' && <p>{trendSentence(d.trend, span)}</p>}
            <TrendBars months={months} band={d.trend.band} height={340} labels names={LENSES[lens].labels}
                       caption={`${LENSES[lens].caption}, last ${count(months.length, 'month')}`} />
            <Legend items={[...lensLegend(lens),
                            ...(d.trend.band ? [{ label: 'Your usual', tone: 'in-band' }] : [])]} />
            <p className="pk-label pk-muted">{bandWords(d.trend, span)}</p>
            {months.length < span && (
              <p className="pk-label pk-muted">
                {`Pearl has ${count(months.length, 'month')} of your spending so far; the rest fill in as they pass.`}
              </p>
            )}
          </>
        ) : <p className="pk-muted">No spending yet. Your months show here as they come in.</p>}
      </section>
      {last && (
        <div className="in-actions">
          <PButton variant="secondary" onClick={() => nav.show('month', { month: last })}>
            {`Review ${monthFull(last)}`}
          </PButton>
          <button type="button" className="in-text-btn" onClick={() => nav.show('month', { month: last })}>
            Mark a month as unusual
          </button>
        </div>
      )}
    </div>
  );
}

// ── GR-30 Where the month went ───────────────────────────────────────────

export function WhereView({ d, route, nav }) {
  const lens = nav.lens ?? 'need';
  const where = whereForLens(!route.month && d.where.total === 0 && d.where_last && d.where_last.total > 0
    ? d.where_last : d.where, lens);
  const month = where.month;
  const running = month === d.months[d.months.length - 1] && d.running;
  const { prev, next } = neighbours(d, month);
  const note = unsureWords(where);
  const segments = where.groups.flatMap((g) => g.categories.map((c) => ({
    key: c.category, amount: c.amount, group: g.key })));
  const open = (r) => nav.toTransactions(r.other ? { month, group: r.group } : { month, category: r.category });
  return (
    <div className="pk hm-page in-page">
      <DetailHead nav={nav} title={whereTitle(month, running)} />
      <MonthSwitcher small label={running ? `${monthFull(month)} so far` : monthYear(month)}
                     prev={prev} next={next && { month: next.month, current: false }}
                     onPrev={() => nav.show('where', { month: prev })}
                     onNext={() => nav.show('where', { month: next.month })} />
      <section className="hm-card in-card in-wide" aria-label={whereTitle(month, running)}>
        {where.total > 0 ? (
          <>
            <div className="in-where-detail">
              <Donut segments={segments} size={256} thickness={44}>
                <span className="in-donut-figure big">{cash(where.total)}</span>
                <span className="pk-label pk-muted">{running ? 'spent so far' : `spent in ${monthFull(month)}`}</span>
              </Donut>
              <div className="in-groups">
                {where.groups.filter((g) => g.total > 0).map((g) => (
                  <div key={g.key} className="in-group">
                    <h2 className="pk-overline accent">{`${g.label} · ${cash(g.total)}`}</h2>
                    <ul className="in-cat-list">
                      {groupRows(g).map((r) => (
                        <li key={r.name}>
                          <button type="button" className="in-cat-row" onClick={() => open(r)}
                                  aria-label={`${r.name}, ${cash(r.amount)}, ${r.share} percent${
                                    r.unsure && !r.other ? ', needs a look' : ''}. See the transactions`}>
                            <CatDot group={g.key} unsure={r.unsure > 0 && !r.other} />
                            <span className="in-grow">
                              {r.name}
                              {r.unsure > 0 && !r.other && <span className="pk-muted"> · needs a look</span>}
                            </span>
                            <span className="in-num">{cash(r.amount)}</span>
                            <span className="in-share pk-label pk-muted">{`${r.share}%`}</span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            </div>
            {note && <p className="pk-label pk-muted">{note}</p>}
          </>
        ) : <p className="pk-muted">{`Nothing spent in ${monthFull(month)}${running ? ' yet' : ''}.`}</p>}
      </section>
      <div className="in-actions">
        {where.unsure > 0 && (
          <PButton variant="secondary" onClick={() => nav.onTab?.('review')}>
            {`Confirm ${count(where.unsure, 'purchase')}`}
          </PButton>
        )}
        <button type="button" className="in-text-btn" onClick={() => nav.toTransactions({ month })}>
          See all transactions
        </button>
      </div>
    </div>
  );
}

// ── GR-31 Money in and out ───────────────────────────────────────────────

export function MoneyView({ d, nav }) {
  const rows = d.money.slice(-6);
  const any = rows.some((r) => r.income > 0 || r.spent > 0);
  const running = rows.find((r) => r.kept === null);
  return (
    <div className="pk hm-page in-page">
      <DetailHead nav={nav} title="Money in and out" />
      <section className="hm-card in-card in-wide" aria-label="Money in and out">
        {any ? (
          <>
            <p>{keptSentence(rows)}</p>
            <InOutBars rows={rows} height={300} caption="Money in, spent and set aside each month" />
            <Legend items={[{ label: 'Money in', tone: 'in-in' }, { label: 'Spent', tone: 'in-spent' },
                            { label: 'Put away', tone: 'in-set-aside' }]} />
          </>
        ) : <p className="pk-muted">Nothing has come in or gone out yet.</p>}
      </section>
      {any && (
        <section className="hm-card in-card in-wide" aria-labelledby="in-kept-title">
          <h2 className="pk-h3" id="in-kept-title">What you kept</h2>
          <dl className="in-kept">
            {rows.map((r) => {
              const k = keptWords(r);
              return (
                <div key={r.month}>
                  <dt className="pk-label pk-muted">{r.kept === null ? `${monthShort(r.month)} so far` : monthShort(r.month)}</dt>
                  <dd className="pk-h3">
                    <span aria-hidden="true">{k.value}</span><span className="pk-sr">{k.sr}</span>
                  </dd>
                  {k.more && <dd className="pk-label pk-muted" aria-hidden="true">{`${k.more} more out`}</dd>}
                </div>
              );
            })}
          </dl>
          {running && (
            <p className="pk-label pk-muted">
              {`${monthFull(running.month)} is still going, so it shows once the month ends.`}
            </p>
          )}
        </section>
      )}
    </div>
  );
}

// ── GR-32 Your savings ───────────────────────────────────────────────────

export function SavingsView({ d, nav }) {
  const s = d.savings;
  const tones = s.anchor_started ? ['in-essentials', 'in-lifestyle', 'in-set-aside', 'in-in', 'in-above']
    : ['in-lifestyle', 'in-set-aside', 'in-in', 'in-above'];
  return (
    <div className="pk hm-page in-page">
      <DetailHead nav={nav} title="Your savings" />
      <section className="hm-card in-card in-wide" aria-label="Your savings">
        {s.total > 0 ? (
          <>
            <p className="pk-amount">{cash(s.total)}</p>
            <p className="pk-label pk-muted">{savingsWords(s, { long: true })}</p>
            {s.series.length > 1
              ? <SavingsArea savings={s} />
              : <p className="pk-muted">Next month this starts to show how it has grown.</p>}
            <ul className="in-cat-list in-parts">
              {s.parts.map((p, i) => (
                <li key={p.key}>
                  <span className={`in-cat-dot ${tones[i] ?? 'in-set-aside'}`} aria-hidden="true" />
                  <span className="in-grow">{p.label}</span>
                  <span className="in-num">{p.amount > 0 ? cash(p.amount) : 'Nothing yet'}</span>
                </li>
              ))}
            </ul>
          </>
        ) : (
          <p className="pk-muted">
            Nothing in your Anchor or a treasure chest yet. Once there is, it grows here month by month.
          </p>
        )}
      </section>
      <div className="in-actions">
        <PButton variant="secondary" onClick={() => nav.onTab?.('projections')}>Look ahead</PButton>
        <button type="button" className="in-text-btn" onClick={() => nav.onTab?.('goals')}>Go to Goals</button>
      </div>
    </div>
  );
}

