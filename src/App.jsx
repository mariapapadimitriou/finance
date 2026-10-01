import { useCallback, useEffect, useRef, useState } from 'react';
import OverviewPanel from './panels/OverviewPanel.jsx';
import TodayPanel from './panels/TodayPanel.jsx';
import ProgressPanel from './panels/ProgressPanel.jsx';
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
const HIDDEN_TABS = [
  { key: 'import', label: 'Import',
    hint: 'Statements from a file, for a card that can\'t be connected',
    icon: 'M12 3v12M7 10l5 5 5-5M4 21h16' },
];

const TABS = [
  { key: 'plan', label: 'Plan', hint: 'Income, commitments, and what is left to spend',
    icon: 'M3 3v18h18M7 15l4-4 3 3 5-6' },
  { key: 'today', label: 'Today', hint: 'What you can spend today, and why that number',
    icon: 'M12 8v4l3 2M12 22a10 10 0 1 1 0-20 10 10 0 0 1 0 20z' },
  { key: 'overview', label: 'Overview', hint: 'Spending across every card',
    icon: 'M4 20V10M10 20V4M16 20v-7M22 20H2' },
  { key: 'savings', label: 'Savings', hint: 'What to cut, ranked by what it saves',
    icon: 'M12 3v18M17 7H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6' },
  { key: 'projections', label: 'Projections', hint: 'Where this lands, at this pace and with the cuts',
    icon: 'M3 17l6-6 4 4 8-8M21 7h-5M21 7v5' },
  { key: 'progress', label: 'Progress', hint: 'Streaks and badges, all earned by spending less',
    icon: 'M8 21h8M12 17v4M12 17a5 5 0 0 0 5-5V3H7v9a5 5 0 0 0 5 5zM17 5h3v3a3 3 0 0 1-3 3M7 5H4v3a3 3 0 0 0 3 3' },
  { key: 'subscriptions', label: 'Subscriptions', hint: 'Recurring charges found in your history',
    icon: 'M21 12a9 9 0 0 1-15.5 6.2M3 12a9 9 0 0 1 15.5-6.2M18 2v4h-4M6 22v-4h4' },
  { key: 'transactions', label: 'Transactions', hint: 'Every charge, searchable and correctable',
    icon: 'M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01' },
  { key: 'budgets', label: 'Budgets', hint: 'Spent against budget, projected to month end',
    icon: 'M12 22a10 10 0 1 1 0-20 10 10 0 0 1 0 20zM12 16a4 4 0 1 1 0-8 4 4 0 0 1 0 8z' },
  { key: 'trips', label: 'Trips', hint: 'Date ranges whose spending counts as Travel',
    icon: 'M3 11l18-6-6 18-2.5-7.5L5 13z' },
  { key: 'accounts', label: 'Accounts', hint: 'Every account, what syncs, and anything counted twice',
    icon: 'M3 10h18M3 10a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2M3 10v8a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-8M7 15h4' },
  { key: 'banks', label: 'Banks', hint: 'Connect a card through Plaid and let it sync itself',
    icon: 'M3 21h18M4 10h16M5 10V7l7-4 7 4v3M7 10v11M12 10v11M17 10v11' },
];

// Panels worth opening with nothing in the ledger: the two that bring data
// in, and the one that decides what keeps arriving — which is also where the
// ledger gets emptied, so it is reachable immediately afterwards.
const WORKS_WHEN_EMPTY = ['banks', 'import', 'accounts', 'plan'];

// Everywhere that needs to name a tab rather than offer it.
const ALL_TABS = [...TABS, ...HIDDEN_TABS];

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
  // Progress, Projections — refetch after an import instead of showing what
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
          <code>python app.py</code>), then{' '}
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
  if (summary.empty && !WORKS_WHEN_EMPTY.includes(tab)) {
    return (
      <Shell theme={theme} setTheme={setTheme} tab={tab} onTab={setTab}
             findingCount={findingCount}>
        <Empty title="Let's see where the money goes">
          <p>
            Connect a card and this fills in by itself: spending by category,
            subscriptions you&apos;ve forgotten about, and a ranked list of what
            to cut. The connection keeps itself up to date, so this is the last
            time you have to think about where the data comes from.
          </p>
          <button className="btn primary" onClick={() => setTab('banks')}
                  style={{ marginTop: 14 }}>
            Connect a card
          </button>
          <p className="small muted" style={{ marginTop: 16, marginBottom: 0 }}>
            For a card that can&apos;t be connected — a closed account, or a bank
            Plaid doesn&apos;t reach —{' '}
            <button className="link" onClick={() => setTab('import')}>
              import statements from a file
            </button>.
          </p>
        </Empty>
      </Shell>
    );
  }

  return (
    <Shell
      theme={theme} setTheme={setTheme} tab={tab} onTab={setTab}
      findingCount={findingCount}
      months={summary.months} month={shownMonth} onMonth={setMonth}
      showMonth={['overview', 'budgets'].includes(tab)}
      onSignOut={async () => { await logout(); setSignedIn(false); }}
    >
      {tab === 'plan' && <PlanPanel onChanged={load} />}
      {tab === 'today' && (
        <TodayPanel month={shownPlanMonth} onMonth={setPlanMonth} version={version} />
      )}
      {tab === 'overview' && (
        <OverviewPanel summary={summary} insights={insights} theme={theme}
                       month={shownMonth} onMonth={setMonth} version={version} />
      )}
      {tab === 'savings' && <SavingsPanel insights={insights} onRefresh={load} />}
      {tab === 'projections' && (
        <ProjectionsPanel insights={insights} version={version} />
      )}
      {tab === 'progress' && <ProgressPanel month={shownPlanMonth} version={version} />}
      {tab === 'subscriptions' && <SubscriptionsPanel recurring={recurring} />}
      {tab === 'transactions' && (
        <TransactionsPanel summary={summary} categories={categories}
                           accounts={accounts} onChanged={load} />
      )}
      {tab === 'budgets' && (
        <BudgetsPanel month={shownMonth} summary={summary} version={version} />
      )}
      {tab === 'trips' && <TripsPanel onChanged={load} />}
      {tab === 'accounts' && <AccountsPanel onChanged={load} />}
      {tab === 'banks' && <BanksPanel onChanged={load} onTab={setTab} />}
      {tab === 'import' && (
        <ImportPanel accounts={accounts} onImported={load} onTab={setTab} />
      )}
    </Shell>
  );
}

function Shell({ theme, setTheme, tab, onTab, findingCount = 0,
                 months = [], month, onMonth, showMonth = false, onSignOut,
                 children }) {
  const current = ALL_TABS.find((t) => t.key === tab);
  const navRef = useRef(null);

  // On a phone the nav is a scrolling strip, and eleven destinations don't
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
            {TABS.map((t) => (
              <button
                key={t.key}
                role="tab"
                aria-selected={tab === t.key}
                onClick={() => onTab(t.key)}
              >
                <Icon d={t.icon} />
                {t.label}
                {t.key === 'savings' && findingCount > 0 && (
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
        </div>
        <main>{children}</main>
      </div>
    </div>
  );
}
