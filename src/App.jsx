import { useCallback, useEffect, useState } from 'react';
import OverviewPanel from './panels/OverviewPanel.jsx';
import SavingsPanel from './panels/SavingsPanel.jsx';
import SubscriptionsPanel from './panels/SubscriptionsPanel.jsx';
import TransactionsPanel from './panels/TransactionsPanel.jsx';
import BudgetsPanel from './panels/BudgetsPanel.jsx';
import ImportPanel from './panels/ImportPanel.jsx';
import { Empty, ErrorNote, Loading } from './components/ui.jsx';
import Logo from './components/Logo.jsx';
import {
  getAccounts, getCategories, getInsights, getRecurring, getSummary, monthLabel,
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

const TABS = [
  { key: 'overview', label: 'Overview', hint: 'Spending across every card',
    icon: 'M4 20V10M10 20V4M16 20v-7M22 20H2' },
  { key: 'savings', label: 'Savings', hint: 'What to cut, ranked by what it saves',
    icon: 'M12 3v18M17 7H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6' },
  { key: 'subscriptions', label: 'Subscriptions', hint: 'Recurring charges found in your history',
    icon: 'M21 12a9 9 0 0 1-15.5 6.2M3 12a9 9 0 0 1 15.5-6.2M18 2v4h-4M6 22v-4h4' },
  { key: 'transactions', label: 'Transactions', hint: 'Every charge, searchable and correctable',
    icon: 'M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01' },
  { key: 'budgets', label: 'Budgets', hint: 'Spent against budget, projected to month end',
    icon: 'M12 22a10 10 0 1 1 0-20 10 10 0 0 1 0 20zM12 16a4 4 0 1 1 0-8 4 4 0 0 1 0 8z' },
  { key: 'import', label: 'Import', hint: 'Add statements from any card',
    icon: 'M12 3v12M7 10l5 5 5-5M4 21h16' },
];

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
  const [tab, setTab] = useState('overview');
  const [month, setMonth] = useState('');
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  // Applied during render rather than in an effect, on purpose. Charts read
  // their colours from CSS custom properties when they build, and React runs
  // child effects before parent ones — so an effect here would set the theme
  // attribute *after* the charts had already sampled the outgoing theme,
  // leaving every chart one toggle behind.
  if (typeof document !== 'undefined') {
    document.documentElement.setAttribute('data-theme', theme);
  }

  useEffect(() => { localStorage.setItem('spendie-theme', theme); }, [theme]);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [summary, insights, recurring, accounts, categories] = await Promise.all([
        getSummary(), getInsights(), getRecurring(), getAccounts(), getCategories(),
      ]);
      setData({
        summary, insights, recurring,
        accounts: accounts.accounts ?? [],
        categories: categories.categories ?? [],
      });
      setMonth((m) => m || defaultMonth(summary));
    } catch (e) {
      setError(e);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

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

  if (summary.empty && tab !== 'import') {
    return (
      <Shell theme={theme} setTheme={setTheme} tab={tab} onTab={setTab}
             findingCount={findingCount}>
        <Empty title="Let's see where the money goes">
          <p>
            Drop in your card statements — PDF or CSV — and this fills in:
            spending by category, subscriptions you&apos;ve forgotten about, and a
            ranked list of what to cut.
          </p>
          <button className="btn primary" onClick={() => setTab('import')}
                  style={{ marginTop: 14 }}>
            Import statements
          </button>
        </Empty>
      </Shell>
    );
  }

  return (
    <Shell
      theme={theme} setTheme={setTheme} tab={tab} onTab={setTab}
      findingCount={findingCount}
      months={summary.months} month={month} onMonth={setMonth}
      showMonth={['overview', 'budgets'].includes(tab)}
    >
      {tab === 'overview' && (
        <OverviewPanel summary={summary} insights={insights} theme={theme}
                       month={month} onMonth={setMonth} />
      )}
      {tab === 'savings' && <SavingsPanel insights={insights} onRefresh={load} />}
      {tab === 'subscriptions' && <SubscriptionsPanel recurring={recurring} />}
      {tab === 'transactions' && (
        <TransactionsPanel summary={summary} categories={categories}
                           accounts={accounts} onChanged={load} />
      )}
      {tab === 'budgets' && <BudgetsPanel month={month} summary={summary} />}
      {tab === 'import' && <ImportPanel accounts={accounts} onImported={load} />}
    </Shell>
  );
}

function Shell({ theme, setTheme, tab, onTab, findingCount = 0,
                 months = [], month, onMonth, showMonth = false, children }) {
  const current = TABS.find((t) => t.key === tab);

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <Logo size={34} />
          <div>
            <div className="name">Spendie</div>
            <div className="sub">every card, one picture</div>
          </div>
        </div>

        {onTab && (
          <nav className="nav" role="tablist" aria-orientation="vertical">
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
