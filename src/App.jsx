import { useCallback, useEffect, useRef, useState } from 'react';
import OverviewPanel from './panels/OverviewPanel.jsx';
import TodayPanel from './panels/TodayPanel.jsx';
import PiggyPanel from './panels/PiggyPanel.jsx';
import ProjectionsPanel from './panels/ProjectionsPanel.jsx';
import SavingsPanel from './panels/SavingsPanel.jsx';
import SubscriptionsPanel from './panels/SubscriptionsPanel.jsx';
import TransactionsPanel from './panels/TransactionsPanel.jsx';
import BudgetsPanel from './panels/BudgetsPanel.jsx';
import TripsPanel from './panels/TripsPanel.jsx';
import ImportPanel from './panels/ImportPanel.jsx';
import PlanPanel from './panels/PlanPanel.jsx';
import BanksPanel from './panels/BanksPanel.jsx';
import AccountsPanel from './panels/AccountsPanel.jsx';
import Login from './Login.jsx';
import { Empty, ErrorNote, Loading } from './components/ui.jsx';
import Logo from './components/Logo.jsx';
import {
  getAccounts, getAuthStatus, getCategories, getInsights, getRecurring,
  getSummary, logout, monthLabel, setLedgerCurrency, setUnauthorizedHandler,
} from './api.js';

// Icons are 24×24 stroke paths, drawn in currentColor.
/**
 * The month to open on.
 *
 * Not simply the latest month in range: a ledger can end with a month that
 * holds only a closing credit, or a gap, and landing there shows an empty
 * dashboard that looks broken. Open on the most recent month that has
 * spending in it.
 */
function defaultMonth(summary) {
  const withSpending = (summary.monthly ?? []).filter((m) => m.transactions > 0);
  return withSpending.at(-1)?.month ?? summary.latest_month ?? '';
}

// The Import panel is deliberately absent from this list. Connecting a bank
// is how data arrives; uploading a file is the exception, for a card that
// cannot be connected at all. It stays reachable at the 'import' key, linked
// from the Banks tab, so hiding it costs nothing but prominence.
// Every panel the app can show, keyed the way it always was.
//
// These used to be twelve top-level destinations plus a hidden one, which on a
// phone was a scrolling strip nobody could hold in their head, and which put
// the four surfaces you touch once at setup beside the two you open daily.
// They are grouped below instead. The keys are unchanged, so every
// `onTab('piggy')` in a panel still works — `resolve` turns a panel key into
// the group that now contains it.
const PANELS = {
  today:         { label: 'Today',
                   hint: 'What you can spend today, and why that number' },
  plan:          { label: 'Income & commitments',
                   hint: 'What comes in, what is spoken for, and what is left' },
  budgets:       { label: 'Budgets',
                   hint: 'Spent against budget, projected to month end' },
  overview:      { label: 'This month',
                   hint: 'Spending across every card' },
  projections:   { label: 'Looking ahead',
                   hint: 'Where this lands, at this pace and with the cuts' },
  savings:       { label: 'What to cut',
                   hint: 'Ranked by what it saves, with the charges behind it' },
  subscriptions: { label: 'Subscriptions',
                   hint: 'Every recurring charge found in your history' },
  transactions:  { label: 'Every charge',
                   hint: 'Searchable, correctable, chargeable to a piggy bank' },
  trips:         { label: 'Trips',
                   hint: 'Date ranges whose spending counts as Travel' },
  banks:         { label: 'Connections',
                   hint: 'Connect a card through Plaid and let it sync itself' },
  accounts:      { label: 'Accounts',
                   hint: 'Every account, what syncs, and anything counted twice' },
  import:        { label: 'From a file',
                   hint: "Statements for a card that can't be connected" },
};

// The six destinations. A group holding one panel shows no sub-navigation.
const GROUPS = [
  { key: 'today', label: 'Today', panels: ['today'],
    hint: 'What you can spend today, and why that number',
    icon: 'M12 8v4l3 2M12 22a10 10 0 1 1 0-20 10 10 0 0 1 0 20z' },
  // Looking ahead sits with the plan, not with the history: it is the plan
  // run forward, and the savings figure it offers to move is the plan's.
  { key: 'plan', label: 'Plan', panels: ['plan', 'budgets', 'projections'],
    hint: 'What you earn, what it is promised to, how the rest divides, and where that leads',
    icon: 'M3 3v18h18M7 15l4-4 3 3 5-6' },
  { key: 'overview', label: 'Overview', panels: ['overview'],
    hint: 'Where the money went',
    icon: 'M4 20V10M10 20V4M16 20v-7M22 20H2' },
  { key: 'savings', label: 'Savings', panels: ['savings', 'subscriptions'],
    hint: 'What to cut, and the renewals worth a second look',
    icon: 'M12 3v18M17 7H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6' },
  { key: 'transactions', label: 'Transactions', panels: ['transactions', 'trips'],
    hint: 'Every charge, and the date ranges that reclassify them',
    icon: 'M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01' },
  { key: 'cards', label: 'Cards & data', panels: ['banks', 'accounts', 'import'],
    hint: 'Where the transactions come from, and what counts',
    icon: 'M3 10h18M3 10a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2M3 10v8a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-8M7 15h4' },
];

// Keys that are no longer panels of their own but are still linked to from
// across the app and from the insights, which carry a tab name in their data.
// Piggy banks are a card on the Plan page now — they are already a term in its
// arithmetic — so a link to them is a link there.
const ALIASES = { piggy: 'plan' };

// Where on that page the aliased thing actually is. Without this a link to a
// piggy bank lands at the top of a long page with no sign of one, which is
// indistinguishable from a button that did nothing.
const ANCHORS = { piggy: 'piggy-banks' };

/**
 * Turn a group key or a panel key into both.
 *
 * Panels link to each other by panel key and should not have to know about the
 * grouping, so this accepts either: 'cards' opens the group at its first panel,
 * 'import' opens the same group at that panel.
 */
function resolve(key) {
  const target = ALIASES[key] ?? key;
  const group = GROUPS.find((g) => g.key === target);
  if (group) return [group.key, group.panels[0]];
  const owner = GROUPS.find((g) => g.panels.includes(target));
  if (owner) return [owner.key, target];
  return ['today', 'today'];
}

// Panels worth opening with nothing in the ledger: the two that bring data in,
// and the one that decides what keeps arriving — which is also where the ledger
// gets emptied, so it is reachable immediately afterwards.
const WORKS_WHEN_EMPTY = ['banks', 'import', 'accounts', 'plan'];

function Icon({ d }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
         strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={d} />
    </svg>
  );
}

export default function App() {
  const [theme, setTheme] = useState(
    () => localStorage.getItem('spendie-theme') || 'dark'
  );
  const [tab, setTab] = useState('today');
  const [panel, setPanel] = useState('today');

  /**
   * Go to a destination named either way.
   *
   * Panels link to each other by panel key — `onTab('piggy')` — and must not
   * have to know which group now owns it, so every one of those calls still
   * works unchanged.
   */
  const go = useCallback((key) => {
    const [group, target] = resolve(key);
    setTab(group);
    setPanel(target);
    const anchor = ANCHORS[key];
    if (anchor) {
      // After the panel has rendered and its data has had a moment to land,
      // since what is being scrolled to is below a card that grows on load.
      setTimeout(() => {
        document.getElementById(anchor)
          ?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }, 350);
    }
  }, []);
  // Both month values hold *your* choice, and empty means "follow the data".
  // They are deliberately not seeded from the first load: a seeded value would
  // survive an import that added newer months, leaving the dashboard pinned to
  // a month you never picked and the Today tab insisting nothing was imported
  // for this month when it just was. Derived at render instead, so new data
  // moves them and an explicit pick still sticks.
  const [month, setMonth] = useState('');
  const [planMonth, setPlanMonth] = useState('');
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  // null while we're still asking; the app renders nothing rather than
  // flashing a dashboard at someone who then gets bounced to a login.
  const [signedIn, setSignedIn] = useState(null);
  // Bumped on every reload so panels that fetch their own data — Today,
  // Projections, Piggy banks — refetch after an import instead of showing what
  // they loaded when they mounted.
  const [version, setVersion] = useState(0);

  // Applied during render rather than in an effect, on purpose. Charts read
  // their colours from CSS custom properties when they build, and React runs
  // child effects before parent ones — so an effect here would set the theme
  // attribute *after* the charts had already sampled the outgoing theme,
  // leaving every chart one toggle behind.
  if (typeof document !== 'undefined') {
    document.documentElement.setAttribute('data-theme', theme);
  }

  useEffect(() => { localStorage.setItem('spendie-theme', theme); }, [theme]);

  // A 401 from any request means the session went away — a password change,
  // or a cookie that expired while the tab sat open. Returning to the login
  // screen is better than every panel failing with its own error.
  useEffect(() => {
    setUnauthorizedHandler(() => setSignedIn(false));
  }, []);

  const checkAuth = useCallback(async () => {
    try {
      const s = await getAuthStatus();
      setSignedIn(s.signed_in);
      return s.signed_in;
    } catch (e) {
      setError(e);
      setSignedIn(false);
      return false;
    }
  }, []);

  useEffect(() => { checkAuth(); }, [checkAuth]);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [summary, insights, recurring, accounts, categories] = await Promise.all([
        getSummary(), getInsights(), getRecurring(), getAccounts(), getCategories(),
      ]);
      // Before anything is drawn: every figure in the app is formatted with
      // this, and a wrong default is how the whole ledger came to read as
      // US dollars.
      setLedgerCurrency(summary.currency);
      setData({
        summary, insights, recurring,
        accounts: accounts.accounts ?? [],
        categories: categories.categories ?? [],
      });
      setVersion((v) => v + 1);
    } catch (e) {
      setError(e);
    }
  }, []);

  useEffect(() => { if (signedIn) load(); }, [load, signedIn]);

  if (signedIn === null) {
    return <Shell theme={theme} setTheme={setTheme}><Loading what="Spendie" /></Shell>;
  }

  if (!signedIn) {
    return <Login onSignedIn={() => { setSignedIn(true); setError(null); }} />;
  }

  if (error) {
    return (
      <Shell theme={theme} setTheme={setTheme}>
        <div className="notice error" style={{ marginTop: 24 }}>
          <strong>Can&apos;t reach the Spendie API.</strong> {String(error.message)}
          <br />
          Start it with <code>python app.py</code> (or{' '}
          <code>flask --app app run</code>), then{' '}
          <button className="btn quiet" onClick={load}>retry</button>.
        </div>
      </Shell>
    );
  }

  if (!data) {
    return <Shell theme={theme} setTheme={setTheme}><Loading what="your spending" /></Shell>;
  }

  const { summary, insights, recurring, accounts, categories } = data;
  const findingCount = insights?.findings?.length ?? 0;

  // Your pick wins while the month still exists — clearing a card or an account
  // can remove it — and otherwise both fall back to the data, so an import that
  // brings in newer months moves them without a reload.
  const autoMonth = defaultMonth(summary);
  const shownMonth = (month && summary.months?.includes(month)) ? month : autoMonth;

  const thisMonth = new Date().toISOString().slice(0, 7);
  const thisMonthHasData = (summary.monthly ?? [])
    .some((m) => m.month === thisMonth && m.transactions > 0);
  // Empty means "whatever month it actually is", which is what the plan wants
  // as soon as there is anything to measure this month against. Until then it
  // falls back to the last month with spending, because a safe-to-spend figure
  // for a month holding no transactions is a budget nobody has spent against.
  const shownPlanMonth = planMonth || (thisMonthHasData ? '' : autoMonth);

  // An empty ledger hides the panels that have nothing to show — but not the
  // ones that exist to fix that, or this is a dead end: the Connect button
  // would set the tab and the same empty state would render over it, which
  // looks exactly like a button that does nothing.
  if (summary.empty && !WORKS_WHEN_EMPTY.includes(panel)) {
    return (
      <Shell theme={theme} setTheme={setTheme} tab={tab} panel={panel} onTab={go}
             findingCount={findingCount}>
        <Empty title="Let's see where the money goes">
          <p>
            Connect a card and this fills in by itself: spending by category,
            subscriptions you&apos;ve forgotten about, and a ranked list of what
            to cut. The connection keeps itself up to date, so this is the last
            time you have to think about where the data comes from.
          </p>
          <button className="btn primary" onClick={() => go('banks')}
                  style={{ marginTop: 14 }}>
            Connect a card
          </button>
          <p className="small muted" style={{ marginTop: 16, marginBottom: 0 }}>
            For a card that can&apos;t be connected — a closed account, or a bank
            Plaid doesn&apos;t reach —{' '}
            <button className="link" onClick={() => go('import')}>
              import statements from a file
            </button>.
          </p>
        </Empty>
      </Shell>
    );
  }

  return (
    <Shell
      theme={theme} setTheme={setTheme} tab={tab} panel={panel} onTab={go}
      findingCount={findingCount}
      months={summary.months} month={shownMonth} onMonth={setMonth}
      showMonth={['overview', 'budgets'].includes(panel)}
      onSignOut={async () => { await logout(); setSignedIn(false); }}
    >
      {panel === 'plan' && (
        <div className="stack">
          <PlanPanel onChanged={load} onTab={go} />
          {/* Not a section of its own any more. A piggy bank is a commitment
              like rent — it is the `− Piggy banks` term in the sum above — and
              splitting it off put a third page in a group that was already
              saying the same thing twice. */}
          <div id="piggy-banks"><PiggyPanel version={version} /></div>
        </div>
      )}
      {panel === 'today' && (
        <TodayPanel month={shownPlanMonth} onMonth={setPlanMonth}
                    onTab={go} version={version} />
      )}
      {panel === 'overview' && (
        <OverviewPanel summary={summary} insights={insights} theme={theme}
                       month={shownMonth} onMonth={setMonth} onTab={go}
                       version={version} />
      )}
      {panel === 'savings' && <SavingsPanel insights={insights} onRefresh={load}
                                          onTab={go} />}
      {panel === 'projections' && (
        <ProjectionsPanel insights={insights} onTab={go} onChanged={load}
                         version={version} />
      )}
      {panel === 'subscriptions' && <SubscriptionsPanel recurring={recurring} />}
      {panel === 'transactions' && (
        <TransactionsPanel summary={summary} categories={categories}
                           accounts={accounts} onChanged={load} />
      )}
      {panel === 'budgets' && (
        <BudgetsPanel onTab={go} month={shownMonth} summary={summary} version={version} />
      )}
      {panel === 'trips' && <TripsPanel onChanged={load} />}
      {panel === 'accounts' && <AccountsPanel onChanged={load} />}
      {panel === 'banks' && <BanksPanel onChanged={load} onTab={go} />}
      {panel === 'import' && (
        <ImportPanel accounts={accounts} onImported={load} onTab={go} />
      )}
    </Shell>
  );
}

function Shell({ theme, setTheme, tab, panel, onTab, findingCount = 0,
                 months = [], month, onMonth, showMonth = false, onSignOut,
                 children }) {
  const group = GROUPS.find((g) => g.key === tab);
  // The heading names the panel you are actually looking at; the group label is
  // already on the selected button in the sidebar, so repeating it here would
  // say the same word twice and name the narrower thing nowhere.
  const current = PANELS[panel] ?? group;
  const navRef = useRef(null);

  // On a phone the nav is a scrolling strip, and twelve destinations don't
  // fit. Without this, opening the app on a tab that sits off the right edge
  // shows a bar with nothing selected in it.
  useEffect(() => {
    const selected = navRef.current?.querySelector('[aria-selected="true"]');
    // A hidden tab has no button in the strip; leaving it where it is beats
    // scrolling to a destination the reader did not choose.
    selected?.scrollIntoView({ inline: 'center', block: 'nearest',
                               behavior: 'smooth' });
  }, [tab]);

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <Logo size={34} />
          <div className="name">Spendie</div>
        </div>

        {onTab && (
          <nav className="nav" role="tablist" aria-orientation="vertical"
               ref={navRef}>
            {GROUPS.map((g) => (
              <button
                key={g.key}
                role="tab"
                aria-selected={tab === g.key}
                onClick={() => onTab(g.key)}
              >
                <Icon d={g.icon} />
                {g.label}
                {g.key === 'savings' && findingCount > 0 && (
                  <span className="count">{findingCount}</span>
                )}
              </button>
            ))}
          </nav>
        )}

        <div className="sidebar-foot">
          {onSignOut && (
            <button className="btn quiet" onClick={onSignOut}>
              <span aria-hidden="true">⎋</span>
              <span className="label">Sign out</span>
            </button>
          )}
          <button
            className="btn quiet"
            onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
            aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
          >
            <span aria-hidden="true">{theme === 'dark' ? '☀' : '☾'}</span>
            <span className="label">{theme === 'dark' ? 'Light mode' : 'Dark mode'}</span>
          </button>
        </div>
      </aside>

      <div className="content">
        <div className="topbar">
          <div className="topbar-inner">
            <div className="title">
              <h1>{current?.label ?? 'Spendie'}</h1>
              {current && <div className="hint">{current.hint}</div>}
            </div>

            {showMonth && months.length > 0 && (
              <>
                <label htmlFor="month-select" className="sr-only">Month</label>
                <select id="month-select" value={month}
                        onChange={(e) => onMonth(e.target.value)}>
                  {[...months].reverse().map((m) => (
                    <option key={m} value={m}>{monthLabel(m, { long: true })}</option>
                  ))}
                </select>
              </>
            )}
          </div>

          {group && group.panels.length > 1 && (
            <nav className="sections" role="tablist"
                 aria-label={`${group.label} sections`}>
              {group.panels.map((key) => (
                <button
                  key={key}
                  role="tab"
                  aria-selected={panel === key}
                  onClick={() => onTab(key)}
                >
                  {PANELS[key].label}
                </button>
              ))}
            </nav>
          )}
        </div>
        <main>{children}</main>
      </div>
    </div>
  );
}
