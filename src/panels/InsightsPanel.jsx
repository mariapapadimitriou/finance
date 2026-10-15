import { useCallback, useEffect, useState } from 'react';
import { ErrorNote } from '../components/ui.jsx';
import {
  dismissSuggestion, getInsightsMonth, setMonthUnusual, setSubscriptionChoice,
  undoDismissSuggestion,
} from '../api.js';
import { onInsightsUrl, readInsightsUrl, setGoalsIntent, writeInsightsUrl, writeTxUrl } from '../router.js';
import { ActionToast } from '../pearl/kit.jsx';
import { SnapshotBar } from '../pearl/viz.jsx';
import { ForYou, WhyPanel, dismissedWords } from './ForYou.jsx';
import { CashFlowTabs, CatDot, MonthSwitcher, More } from './InsightsParts.jsx';
import { InsightsFilters } from './InsightsFilters.jsx';
import { LENSES, lensLegend, readLens, trendForLens, whereForLens, writeLens } from './Lens.jsx';
import { Donut, InOutBars, Legend, SavingsArea, TrendBars } from './InsightsCharts.jsx';
import {
  CategoryView, MoneyView, ReviewMonth, SavingsView, SubscriptionsView, TrendView, WhereView,
} from './InsightsViews.jsx';
import {
  addMonths, cash, count, monthFull, savingsWords, tileRows, topCategory, topRows, usualBar,
  whereTitle,
} from './insightsMath.js';
import './home.css';
import './insights.css';

/**
 * Growth › Insights (Pearl THL-186 GR-24 to GR-27, THL-196 GR-28 to GR-32),
 * at /growth/insights. It replaced the prototype Insights page.
 *
 * GR-28 is the page: the four tiles (Income, Essentials, Lifestyle, Set
 * aside), four chart cards (spending trend, where the month went, money in
 * and out, savings), Essentials and Lifestyle against her usual month
 * (GR-24, the snapshot bar), subscriptions by the year, and "For you" — the
 * recommendation cards Home shows, at most two. Each card opens its detail
 * view at its own address: GR-29 trend, GR-30 where it went, GR-31 money in
 * and out, GR-32 savings, GR-26 a category against usual, GR-27
 * subscriptions, and GR-25 a past month, which the month switcher reviews.
 *
 * Every chart has its figures as a table for a screen reader, and empty or
 * thin months are said in words; nothing is red and no amount is signed.
 * Learn, the fourth Growth pill, opens Growth › Learn (THL-134).
 */

const VIEWS = { month: ReviewMonth, category: CategoryView, subscriptions: SubscriptionsView,
                trend: TrendView, where: WhereView, money: MoneyView, savings: SavingsView };

/** Which month a view asks the server for: GR-25 and GR-30 pick one. */
const fetchMonth = (route) => (['month', 'where'].includes(route.view) ? route.month : '');
const FILTER_KEYS = ['account', 'span', 'one_offs', 'show'];
const pickFilters = (route) => Object.fromEntries(FILTER_KEYS.map((k) => [k, route[k] || '']));
const fetchKey = (route) => JSON.stringify({ month: fetchMonth(route), ...pickFilters(route) });

export default function InsightsPanel({ onTab, version }) {
  const [route, setRoute] = useState(() => readInsightsUrl() ?? { view: '', month: '', category: '' });
  const [loaded, setLoaded] = useState(null);           // { key, data }
  const [error, setError] = useState(null);
  const [why, setWhy] = useState(null);
  const [hidden, setHidden] = useState(null);
  const [lens, setLensState] = useState(readLens);
  const setLens = (l) => { setLensState(l); writeLens(l); };
  const key = fetchKey(route);

  useEffect(() => onInsightsUrl(() => {
    const next = readInsightsUrl();
    if (next) setRoute(next);
  }), []);

  const load = useCallback(() => {
    setError(null);
    return getInsightsMonth(JSON.parse(key))
      .then((data) => setLoaded({ key, data }))
      .catch(setError);
  }, [key]);
  useEffect(() => { load(); }, [load, version]);

  // The filters carry from view to view; a card's link keeps them.
  const show = (view = '', extra = {}) => {
    writeInsightsUrl({ view, ...pickFilters(route), ...extra });
    window.scrollTo?.({ top: 0 });
  };
  const setFilter = (patch) => writeInsightsUrl({ ...route, ...patch }, { push: false });
  const toTransactions = (filters) => {
    writeTxUrl({ filters, from: 'insights' }, { push: true });
    onTab?.('transactions');
  };

  if (error) return <div className="pk hm-page"><ErrorNote error={error} onRetry={load} /></div>;
  if (!loaded || loaded.key !== key) {
    return <div className="pk hm-page"><p className="pk-muted" role="status">Loading your insights…</p></div>;
  }
  const d = loaded.data;
  const setData = (data) => setLoaded({ key, data });
  const nav = {
    show, onTab, toTransactions, lens, setLens, filters: pickFilters(route), setFilter,
    onUnusual: (month, on) => setMonthUnusual(month, on).then(setData),
    onChoice: (merchant, choice) => setSubscriptionChoice(merchant, choice).then(setData),
  };

  const View = VIEWS[route.view];
  if (View) return <View d={d} route={route} nav={nav} />;

  // A card's action (THL-12 R3): her own view of it here, else where Home sends it.
  const act = (card) => {
    setWhy(null);
    if (card.type === 'trend' && card.numbers?.category) return show('category', { category: card.numbers.category });
    if (card.type === 'subscriptions') return show('subscriptions');
    if (card.action.to === 'transactions') return toTransactions(card.action.filters);
    if (card.action.goals) setGoalsIntent(card.action.goals);
    return onTab?.(card.action.to);
  };
  const notForMe = (card) => {
    setWhy(null);
    setData({ ...d, recommendations: d.recommendations.filter((c) => c.type !== card.type) });
    setHidden(card.type);
    dismissSuggestion(card.type).catch(() => load());
  };
  const undo = () => {
    const type = hidden;
    setHidden(null);
    undoDismissSuggestion(type).then(load).catch(() => load());
  };
  return (
    <>
      <InsightsPage d={d} show={show} onTab={onTab} cards={d.recommendations ?? []}
                    onCard={act} onWhy={setWhy} onNotForMe={notForMe}
                    lens={lens} onLens={setLens} filters={pickFilters(route)} onFilter={setFilter} />
      {why && <WhyPanel card={why} onClose={() => setWhy(null)} onAction={act} onNotForMe={notForMe} />}
      {hidden && <ActionToast title={dismissedWords(hidden)} onUndo={undo} onDone={() => setHidden(null)} />}
    </>
  );
}

function CardHead({ title, link, onLink, label, id }) {
  return (
    <div className="in-card-head">
      <h2 className="pk-h3" id={id}>{title}</h2>
      {link && <More onClick={onLink} label={label}>{link}</More>}
    </div>
  );
}

/** FV-02: what the filters show, in a line — "Showing Lifestyle on TD Visa
 * ••1203 over 3 months, with one-offs left out. Income and money put away
 * aren't filtered." Nothing when nothing is filtered. */
export function filtersWords(d, filters = {}) {
  const parts = [];
  const names = { essentials: 'Essentials', lifestyle: 'Lifestyle', fixed: 'Fixed', variable: 'Variable' };
  if (filters.show && names[filters.show]) parts.push(names[filters.show]);
  const account = (d.accounts ?? []).find((a) => a.id === filters.account);
  if (account) parts.push(`on ${account.name}`);
  if (filters.span) parts.push(`over ${filters.span} months`);
  if (!parts.length && !filters.one_offs) return '';
  let out = parts.length ? `Showing ${parts.join(' ')}` : 'Showing everything';
  if (filters.one_offs === 'out') out += ', with one-offs left out';
  return `${out}. Income and money put away aren’t filtered.`;
}

/** GR-28: the page. */
export function InsightsPage({ d, show, onTab, cards = [], onCard, onWhy, onNotForMe,
                               lens = 'need', onLens, filters = {}, onFilter }) {
  const prev = d.months.length > 1 ? addMonths(d.month, -1) : null;
  // This month, as everywhere in the app; last month only until this one
  // has any spending to show.
  const shownWhere = whereForLens(d.where.total > 0 || !(d.where_last && d.where_last.total > 0)
    ? d.where : d.where_last, lens);
  const whereRunning = shownWhere.month === d.month && d.running;
  const trend = trendForLens(d.trend.months.slice(-6), lens);
  const money = d.money.slice(-6);
  const anySpend = trend.some((m) => m.total > 0);
  const anyMoney = money.some((r) => r.income > 0 || r.spent > 0);
  const subs = d.subscriptions;
  const topCat = topCategory(d.categories);
  return (
    <div className="pk hm-page in-page">
      <header className="in-top">
        <div className="hm-head">
          <p className="pk-overline accent">Insights</p>
          <h1 className="pk-h1">Cash flow</h1>
        </div>
        <MonthSwitcher label={`${monthFull(d.month)} so far`} prev={prev}
                       onPrev={() => show('month', { month: prev })} />
      </header>
      <CashFlowTabs current="insights" onTab={onTab} />
      <InsightsFilters d={d} lens={lens} onLens={onLens} filters={filters} onFilter={onFilter} />
      {filtersWords(d, filters) && (
        <Alert action="Clear filters"
               onAction={() => onFilter({ account: '', span: '', show: '', one_offs: '' })}>
          {filtersWords(d, filters)}
        </Alert>
      )}

      <ul className="in-tiles" aria-label={`${monthFull(d.month)} so far`}>
        {tileRows(d, lens).map((t) => (
          <li key={t.key} className="in-tile">
            <span className="pk-overline">{t.label}</span>
            <span className="in-tile-figure">{t.value}</span>
            <span className="pk-label pk-muted">{t.note}</span>
          </li>
        ))}
      </ul>

      <div className="in-grid">
        <section className="hm-card in-card" aria-labelledby="in-trend-title">
          <CardHead id="in-trend-title" title={`Your spending, last ${count(trend.length, 'month')}`}
                    link="See the trend" onLink={() => show('trend')} label="See the trend" />
          {anySpend ? (
            <>
              <TrendBars months={trend} band={d.trend.band} names={LENSES[lens].labels}
                         caption={`${LENSES[lens].caption} each month`} />
              <Legend items={[...lensLegend(lens),
                              ...(d.trend.band ? [{ label: 'Your usual', tone: 'in-band' }] : [])]} />
            </>
          ) : <p className="pk-muted">No spending yet. Your months show here as they come in.</p>}
        </section>

        <section className="hm-card in-card" aria-labelledby="in-where-title">
          <CardHead id="in-where-title" title={whereTitle(shownWhere.month, whereRunning)}
                    link={shownWhere.total > 0 ? 'See all' : null}
                    onLink={() => show('where', { month: shownWhere.month })}
                    label={`See all of ${monthFull(shownWhere.month)}`} />
          {shownWhere.total > 0 ? <WhereSummary where={shownWhere} running={whereRunning} />
            : <p className="pk-muted">Nothing spent yet this month.</p>}
        </section>

        <section className="hm-card in-card" aria-labelledby="in-money-title">
          <CardHead id="in-money-title" title="Money in and out" link="See more" onLink={() => show('money')}
                    label="See more of money in and out" />
          {anyMoney ? (
            <>
              <InOutBars rows={money} caption="Money in, spent and put away each month" />
              <Legend items={[{ label: 'Money in', tone: 'in-in' }, { label: 'Spent', tone: 'in-spent' },
                              { label: 'Put away', tone: 'in-set-aside' }]} />
            </>
          ) : <p className="pk-muted">Nothing has come in or gone out yet.</p>}
        </section>

        <section className="hm-card in-card" aria-labelledby="in-savings-title">
          <CardHead id="in-savings-title" title="Your savings" link="See more" onLink={() => show('savings')}
                    label="See more of your savings" />
          <SavingsSummary savings={d.savings} onGoals={() => onTab?.('goals')} />
        </section>
      </div>

      <div className="in-bottom">
        <div className="in-col">
          <section className="hm-card in-card in-usual" aria-labelledby="in-usual-title">
            <div className="in-card-head">
              <h2 className="pk-h2" id="in-usual-title">Compared with your usual</h2>
              {topCat && <More onClick={() => show('category', { category: topCat })}>By category</More>}
            </div>
            <VsUsual d={d} />
          </section>
          <section className="hm-card in-card in-subs" aria-labelledby="in-subs-title">
            <div className="in-card-head">
              <div className="in-stack">
                <p className="pk-overline">Subscriptions</p>
                <h2 className="pk-h3" id="in-subs-title">
                  {subs.count > 0 ? `${count(subs.count, 'subscription')} · about ${cash(subs.yearly)} a year`
                    : 'No subscriptions spotted yet'}
                </h2>
                {subs.reminders.length > 0 && (
                  <p className="pk-label pk-muted">{`You said you’d review ${subs.reminders.join(', ')} this month.`}</p>
                )}
              </div>
              {subs.count > 0 && <More onClick={() => show('subscriptions')}>See them all</More>}
            </div>
          </section>
        </div>
        <div className="in-col in-for-you">
          {cards.length > 0
            ? <ForYou cards={cards} onAction={onCard} onWhy={onWhy} onNotForMe={onNotForMe} />
            : null}
        </div>
      </div>
    </div>
  );
}

/** GR-24: Essentials and Lifestyle against her usual, by today. */
function VsUsual({ d }) {
  const rows = d.vs_usual.filter((r) => r.usual);
  if (!rows.length) {
    return (
      <p className="pk-muted">
        Your usual month appears once a full month is in. Until then there’s nothing to compare with.
      </p>
    );
  }
  return rows.map((r) => <SnapshotBar key={r.key} {...usualBar(r, d)} />);
}

function WhereSummary({ where, running }) {
  const rows = topRows(where);
  const segments = where.groups.flatMap((g) => g.categories.map((c) => ({
    key: c.category, amount: c.amount, group: g.key })));
  return (
    <div className="in-where-row">
      <Donut segments={segments} size={160} thickness={32}>
        <span className="in-donut-figure">{cash(where.total)}</span>
        <span className="pk-label pk-muted">{running ? 'so far' : 'spent'}</span>
      </Donut>
      <ul className="in-cat-list" aria-label={whereTitle(where.month, running)}>
        {rows.map((r) => (
          <li key={r.name}>
            <CatDot group={r.group} unsure={r.unsure > 0 && !r.other} />
            <span className="in-grow">{r.name}</span>
            <span className="in-num">{cash(r.amount)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function SavingsSummary({ savings, onGoals }) {
  if (!(savings.total > 0)) {
    return (
      <>
        <p className="pk-muted">Nothing in your Anchor or a treasure chest yet. Once there is, it grows here month by month.</p>
        <More onClick={onGoals}>Go to Goals</More>
      </>
    );
  }
  return (
    <>
      <p className="pk-amount in-figure-big">{cash(savings.total)}</p>
      <p className="pk-label pk-muted">{savingsWords(savings)}</p>
      {savings.series.length > 1 && <SavingsArea savings={savings} height={110} axis="ends" labels={false} />}
    </>
  );
}
