import { useCallback, useEffect, useState } from 'react';
import OverviewPanel from './panels/OverviewPanel.jsx';
import SavingsPanel from './panels/SavingsPanel.jsx';
import SubscriptionsPanel from './panels/SubscriptionsPanel.jsx';
import TransactionsPanel from './panels/TransactionsPanel.jsx';
import BudgetsPanel from './panels/BudgetsPanel.jsx';
import ImportPanel from './panels/ImportPanel.jsx';
import { Empty, ErrorNote, Loading } from './components/ui.jsx';
import {
  getAccounts, getCategories, getInsights, getRecurring, getSummary, monthLabel,
} from './api.js';

const TABS = [
  { key: 'overview', label: 'Overview' },
  { key: 'savings', label: 'Savings' },
  { key: 'subscriptions', label: 'Subscriptions' },
  { key: 'transactions', label: 'Transactions' },
  { key: 'budgets', label: 'Budgets' },
  { key: 'import', label: 'Import' },
];

export default function App() {
  const [theme, setTheme] = useState(
    () => localStorage.getItem('ledger-theme') || 'dark'
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

  useEffect(() => { localStorage.setItem('ledger-theme', theme); }, [theme]);

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
      setMonth((m) => m || summary.latest_month || '');
    } catch (e) {
      setError(e);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (error) {
    return (
      <Shell theme={theme} setTheme={setTheme}>
        <div className="notice error" style={{ marginTop: 24 }}>
          <strong>Can&apos;t reach the Ledger API.</strong> {String(error.message)}
          <br />
          Start it with <code>python app.py</code> (or{' '}
          <code>python app.py --demo</code> to load sample data first), then{' '}
          <button className="btn quiet" onClick={load}>retry</button>.
        </div>
      </Shell>
    );
  }

  if (!data) {
    return <Shell theme={theme} setTheme={setTheme}><Loading what="your ledger" /></Shell>;
  }

  const { summary, insights, recurring, accounts, categories } = data;
  const findingCount = insights?.findings?.length ?? 0;

  if (summary.empty && tab !== 'import') {
    return (
      <Shell theme={theme} setTheme={setTheme} tab={tab} onTab={setTab}
             findingCount={findingCount}>
        <Empty title="No transactions yet">
          <p>
            Import CSV exports from your cards and this fills in — spending by
            category, subscriptions you&apos;ve forgotten about, and a ranked list
            of what to cut.
          </p>
          <button className="btn primary" onClick={() => setTab('import')}
                  style={{ marginTop: 12 }}>
            Import statements
          </button>
          <p className="small muted" style={{ marginTop: 20 }}>
            Just exploring? Run <code>python app.py --demo</code> to load 14 months
            of realistic sample data across three cards.
          </p>
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
  return (
    <>
      <header>
        <div className="header-inner">
          <div className="brand">
            <h1>Ledger</h1>
            <span className="sub">every card, one picture</span>
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

          <button
            className="btn quiet"
            onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
            aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
          >
            {theme === 'dark' ? '☀' : '☾'}
          </button>
        </div>

        {onTab && (
          <nav className="tabs" role="tablist">
            {TABS.map((t) => (
              <button
                key={t.key}
                role="tab"
                aria-selected={tab === t.key}
                onClick={() => onTab(t.key)}
              >
                {t.label}
                {t.key === 'savings' && findingCount > 0 && (
                  <span className="badge">{findingCount}</span>
                )}
              </button>
            ))}
          </nav>
        )}
      </header>
      <main>{children}</main>
    </>
  );
}
