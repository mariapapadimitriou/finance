import { useCallback, useEffect, useRef, useState } from 'react';
import OverviewPanel from './panels/OverviewPanel.jsx';
import TodayPanel from './panels/TodayPanel.jsx';
import PiggyPanel from './panels/PiggyPanel.jsx';
import MortgagePanel from './panels/MortgagePanel.jsx';
import RetirementPanel from './panels/RetirementPanel.jsx';
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
import CategoriesPanel from './panels/CategoriesPanel.jsx';
import Login from './Login.jsx';
import { Empty, ErrorNote, Loading } from './components/ui.jsx';
import Logo from './components/Logo.jsx';
import { ANCHORS, GROUPS, PANELS, resolve } from './nav.js';
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

// Panels worth opening with nothing in the ledger: the two that bring data in,
// and the one that decides what keeps arriving — which is also where the ledger
// gets emptied, so it is reachable immediately afterwards.
const WORKS_WHEN_EMPTY = ['banks', 'import', 'accounts', 'plan'];

/**
 * A navigation label with an optional phone-width form.
 *
 * Both are rendered and CSS picks one, so the accessible name is always the
 * full label — a screen reader on a phone should still hear "Transactions".
 */
function Label({ full, short }) {
  if (!short) return full;
  return (
    <>
      <span className="label-full">{full}</span>
      <span className="label-short" aria-hidden="true">{short}</span>
    </>
  );
}

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
    // A new key: the old one saved the old dark default on every visit, so
    // nobody would ever have seen the light default this introduced.
    () => localStorage.getItem('spendie-theme-2') || 'light'
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

  useEffect(() => { localStorage.setItem('spendie-theme-2', theme); }, [theme]);

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
        <Empty title="No spending yet">
          <div className="row" style={{ justifyContent: 'center', marginTop: 14 }}>
            <button className="btn primary" onClick={() => go('banks')}>
              Connect a card
            </button>
            <button className="btn" onClick={() => go('import')}>
              Import a file
            </button>
          </div>
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
          <div id="piggy-banks"><PiggyPanel onTab={go} version={version} /></div>
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
      {panel === 'mortgage' && <MortgagePanel onChanged={load} onTab={go} />}
      {panel === 'retirement' && <RetirementPanel onTab={go} />}
      {panel === 'subscriptions' && <SubscriptionsPanel recurring={recurring} />}
      {panel === 'transactions' && (
        <TransactionsPanel summary={summary} categories={categories}
                           accounts={accounts} onChanged={load} />
      )}
      {panel === 'budgets' && (
        <BudgetsPanel onTab={go} month={shownMonth} summary={summary} version={version} />
      )}
      {panel === 'trips' && <TripsPanel onChanged={load} />}
      {panel === 'accounts' && <AccountsPanel onChanged={load} onTab={go} />}
      {panel === 'banks' && <BanksPanel onChanged={load} onTab={go} />}
      {panel === 'categories' && <CategoriesPanel onChanged={load} />}
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
  const sectionsRef = useRef(null);

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

  // The section strip scrolls on a phone too, and opening Looking ahead used
  // to leave the strip reading "come & commitments | Budgets | Looking ahead":
  // the first tab sliced in half, and no hint that anything was there.
  // `nearest` moves it only as far as needed, and the strip's scroll-padding
  // keeps the chosen tab off the very edge.
  useEffect(() => {
    const selected = sectionsRef.current?.querySelector('[aria-selected="true"]');
    selected?.scrollIntoView({ inline: 'nearest', block: 'nearest' });
  }, [panel]);

  // Theme and sign-out, drawn twice: in the sidebar on a desktop and in the
  // top bar on a phone. On a phone they used to share the bottom bar with the
  // six destinations, which left no room for two of them.
  const accountActions = (
    <>
      {onSignOut && (
        <button className="btn quiet" onClick={onSignOut}
                aria-label="Sign out">
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
    </>
  );

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
                <Label full={g.label} short={g.short} />
                {g.key === 'savings' && findingCount > 0 && (
                  <span className="count">{findingCount}</span>
                )}
              </button>
            ))}
          </nav>
        )}

        <div className="sidebar-foot">{accountActions}</div>
      </aside>

      <div className="content">
        <div className="topbar">
          <div className="topbar-inner">
            <div className="title">
              <h1>{current?.label ?? 'Spendie'}</h1>
            </div>

            {showMonth && months.length > 0 && (
              <>
                <label htmlFor="month-select" className="sr-only">Month</label>
                <select id="month-select" value={month}
                        onChange={(e) => onMonth(e.target.value)}>
                  {[...months].reverse().map((m) => (
                    <option key={m} value={m}>{monthLabel(m, { full: true })}</option>
                  ))}
                </select>
              </>
            )}

            <div className="topbar-actions">{accountActions}</div>
          </div>

          {group && group.panels.length > 1 && (
            <div className="sections-wrap">
            <nav className="sections" role="tablist" ref={sectionsRef}
                 aria-label={`${group.label} sections`}>
              {group.panels.map((key) => (
                <button
                  key={key}
                  role="tab"
                  aria-selected={panel === key}
                  onClick={() => onTab(key)}
                >
                  <Label full={PANELS[key].label} short={PANELS[key].short} />
                </button>
              ))}
            </nav>
            </div>
          )}
        </div>
        <main>{children}</main>
      </div>
    </div>
  );
}
