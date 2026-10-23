import { useCallback, useEffect, useRef, useState } from 'react';
import HomePanel from './panels/HomePanel.jsx';
import InsightsPanel from './panels/InsightsPanel.jsx';
import CalendarPanel from './panels/CalendarPanel.jsx';
import QuickSort from './panels/QuickSort.jsx';
import DebtsPanel from './panels/DebtsPanel.jsx';
import TransactionsList from './panels/TransactionsList.jsx';
import NeedsALook from './panels/NeedsALook.jsx';
import CategoryBudgetsPanel from './panels/CategoryBudgetsPanel.jsx';
import IncomeBillsPanel from './panels/IncomeBillsPanel.jsx';
import AccountsPanel from './panels/AccountsPanel.jsx';
import ProfilePanel from './panels/ProfilePanel.jsx';
import RulesPanel from './panels/RulesPanel.jsx';
import SecurityPanel from './panels/SecurityPanel.jsx';
import NotificationsPanel from './panels/NotificationsPanel.jsx';
import ConsentPanel from './panels/ConsentPanel.jsx';
import DataPanel, { AccountDeleted } from './panels/DataPanel.jsx';
import ProtectPanel from './panels/ProtectPanel.jsx';
import SignedOut, { resetTokenFromUrl, timeoutFromUrl, timeoutUrl } from './pearl/SignedOut.jsx';
import { DeviceApprovals, SessionTimeout } from './pearl/Session.jsx';
import Onboarding from './pearl/Onboarding.jsx';
import { Empty, ErrorNote, Loading } from './components/ui.jsx';
import Logo from './components/Logo.jsx';
import { ANCHORS, GROUPS, PANELS, resolve } from './nav.js';
import {
  appPanelFromHistory, clearUrl, isCalendarUrl, writeAppUrl, isInsightsUrl, isReviewUrl, readTxUrl, redirectOldUrl, writeCalendarUrl,
  writeInsightsUrl, writeReviewUrl,
} from './router.js';
import {
  getAccounts, getAuthStatus, getCategories, getQuickSort, getReview, getSummary, logout,
  setLedgerCurrency, setUnauthorizedHandler, syncPlaid,
} from './api.js';

// Icons are 24×24 stroke paths, drawn in currentColor.

// Panels worth opening with nothing in the ledger: Accounts, where a bank is
// linked and which decides what keeps arriving — and which is also where the
// ledger gets emptied, so it is reachable immediately afterwards. The Profile
// hub and its pages too: a brand-new account has an empty ledger, and must
// still be able to change its email or sign out. And Home, whose no-data
// state is where linking starts.
const WORKS_WHEN_EMPTY = ['home', 'debts', 'budgets', 'accounts', 'income', 'profile', 'security',
                          'rules', 'notifications', 'consent', 'data', 'protect'];

// Pages that draw their section pills themselves, under their own title
// (Growth › Path, THL-129 GR-01; Insights, THL-196 GR-28; Projections, THL-197
// GR-33; Learn, THL-134 GR-11), so the shell's strip would say it twice.
// Run `fn` once no sheet or dialog is open (the notifications prime, a
// carry-over question), so the quick sort never stacks on another one.
function whenNoDialog(fn) {
  const open = () => !!document.querySelector('.pk-scrim, .pk-dialog-scrim');
  // The page's own sheets arrive a moment after it loads, so the first look
  // waits, and the prompt needs a short quiet spell with nothing open.
  let clear = 0;
  const tick = setInterval(() => {
    clear = open() ? 0 : clear + 1;
    if (clear >= 3) { clearInterval(tick); fn(); }
  }, 250);
}

const OWN_SECTIONS = ['insights', 'calendar', 'budgets', 'debts', 'transactions', 'review'];

// An old Growth address (before THL-248) becomes its new one before anything
// reads it, so a saved link lands where the page went.
if (typeof window !== 'undefined') redirectOldUrl();

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
  // /transactions… opens the list (a link from anywhere lands there); every
  // other address opens Home, where the app lands (THL-44, THL-125).
  const [tab, setTab] = useState(() => (readTxUrl() || isReviewUrl() || isInsightsUrl() || isCalendarUrl()
    ? 'cashflow' : 'home'));
  const [panel, setPanel] = useState(() => (isReviewUrl() ? 'review'
    : readTxUrl() ? 'transactions' : isInsightsUrl() ? 'insights' : isCalendarUrl() ? 'calendar' : 'home'));

  /**
   * Go to a destination named either way.
   *
   * Panels link to each other by panel key — `onTab('income')` — and must not
   * have to know which group now owns it, so every one of those calls still
   * works unchanged.
   */
  const go = useCallback((key) => {
    const [group, target] = resolve(key);
    setTab(group);
    setPanel(target);
    // The list writes its own address when it mounts; Needs a look, Insights
    // and the Calendar have one too. Everything else lives at "/". A link
    // straight to one of Insights' views has already written its address.
    if (target === 'review') writeReviewUrl({ from: panelRef.current });
    else if (target === 'insights') { if (!isInsightsUrl()) writeInsightsUrl(); }
    else if (target === 'calendar') { if (!isCalendarUrl()) writeCalendarUrl(); }
    else if (target !== 'transactions') writeAppUrl(target);
    // Coming to the list from elsewhere is a step of its own (2026-10-22);
    // the list then only ever replaces its own entry as filters change.
    else if (!readTxUrl()) window.history.pushState(null, '', '/transactions');
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
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  // null while we're still asking; the app renders nothing rather than
  // flashing a dashboard at someone who then gets bounced to a login.
  const [signedIn, setSignedIn] = useState(null);
  // Who is signed in, for onboarding: a new account sets itself up before the
  // app opens. `fresh` is true straight after making one, which is when a
  // passkey is offered.
  const [user, setUser] = useState(null);
  const [fresh, setFresh] = useState(false);
  // THL-116 D-05: set once her account is deleted, shown until she closes it.
  const [deleted, setDeleted] = useState(null);
  // Bumped on every reload so panels that fetch their own data — Home,
  // Income and bills — refetch after an import instead of showing what
  // they loaded when they mounted.
  const [version, setVersion] = useState(0);
  // THL-254: quick sort of new transactions Pearl isn't sure of, offered
  // once a day on open.
  const [quickSort, setQuickSort] = useState(null);
  const askQuickSort = useCallback(() => {
    getQuickSort().then((q) => {
      if (q?.show) whenNoDialog(() => setQuickSort(q));
    }).catch(() => {});
  }, []);
  // "Quick sort all" on To review (TR-01): the same cards, asked for — for
  // every unsure row still there, whether or not the prompt offered it
  // before (2026-10-21).
  const openQuickSort = useCallback(() => {
    getQuickSort({ all: true }).then((q) => {
      if (q?.items?.length) setQuickSort({ ...q, show: true });
    }).catch(() => {});
  }, []);
  // A-14: signed out for being idle in this page's life, so signing back in
  // only needs the address put back; after a reload it needs a fresh load.
  const timedOut = useRef(false);
  const signOutIdle = useCallback(async () => {
    const here = window.location.pathname + window.location.search;
    await logout().catch(() => {});
    timedOut.current = true;
    window.history.replaceState(null, '', timeoutUrl(here));
    setData(null);
    setSignedIn(false);
  }, []);

  // Applied during render rather than in an effect, on purpose. Charts read
  // their colours from CSS custom properties when they build, and React runs
  // child effects before parent ones — so an effect here would set the theme
  // attribute *after* the charts had already sampled the outgoing theme,
  // leaving every chart one toggle behind.
  if (typeof document !== 'undefined') {
    document.documentElement.setAttribute('data-theme', theme);
  }

  useEffect(() => { localStorage.setItem('spendie-theme-2', theme); }, [theme]);

  // Back and forward between the list's addresses and the rest of the app.
  const panelRef = useRef(panel);
  panelRef.current = panel;
  useEffect(() => {
    if (window.location.pathname === '/' && !window.history.state?.panel) writeAppUrl(panelRef.current, { push: false });
    const onPop = () => {
      if (isReviewUrl()) { setTab('cashflow'); setPanel('review'); }
      else if (isInsightsUrl()) { setTab('cashflow'); setPanel('insights'); }
      else if (isCalendarUrl()) { setTab('cashflow'); setPanel('calendar'); }
      else if (readTxUrl()) { setTab('cashflow'); setPanel('transactions'); }
      else {
        // "/" — the page this entry was for (2026-10-22), else Home.
        const [g, t] = resolve(appPanelFromHistory() || 'home');
        setTab(g); setPanel(t);
      }
    };
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);

  // A 401 from any request means the session went away — a password change,
  // or a cookie that expired while the tab sat open. Returning to the login
  // screen is better than every panel failing with its own error.
  useEffect(() => {
    setUnauthorizedHandler(() => setSignedIn(false));
  }, []);

  const checkAuth = useCallback(async () => {
    try {
      const s = await getAuthStatus();
      setUser(s.user ?? null);
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
      const [summary, accounts, categories, review] = await Promise.all([
        getSummary(), getAccounts(), getCategories(),
        // Only a badge: a failure here must not stop the app loading.
        getReview().catch(() => ({ count: 0 })),
      ]);
      // Before anything is drawn: every figure in the app is formatted with
      // this, and a wrong default is how the whole ledger came to read as
      // US dollars.
      setLedgerCurrency(summary.currency);
      setData({
        summary,
        accounts: accounts.accounts ?? [],
        categories: categories.categories ?? [],
        review: review.count ?? 0,
      });
      setVersion((v) => v + 1);
    } catch (e) {
      setError(e);
    }
  }, []);

  const onboarding = !!user && user.onboarding && !user.onboarding.done;

  useEffect(() => { if (signedIn && !onboarding) load(); }, [load, signedIn, onboarding]);

  // Pull from the banks as soon as the app opens, after the first paint so
  // the page never waits on Plaid. Once per sign-in; the figures reload only
  // if something actually came in, changed or went away. A failure is left
  // for Profile › Accounts to report.
  const synced = useRef(false);
  useEffect(() => {
    if (!signedIn || !data || synced.current) return;
    synced.current = true;
    syncPlaid()
      .then((r) => {
        const changed = (r?.imported ?? 0) > 0 || (r?.items ?? []).some(
          (i) => (i.modified ?? 0) > 0 || (i.removed ?? 0) > 0);
        if (changed) load();
      })
      .catch(() => {});
  }, [signedIn, data, load]);

  // Once the app has opened: the quick sort, if new transactions need it.
  const askedQuickSort = useRef(false);
  useEffect(() => {
    if (!signedIn || !data || askedQuickSort.current) return;
    askedQuickSort.current = true;
    askQuickSort();
  }, [signedIn, data, askQuickSort]);

  if (signedIn === null) {
    return <Shell theme={theme} setTheme={setTheme}><Loading what="Pearl" /></Shell>;
  }

  if (deleted) {
    return <AccountDeleted sentTo={deleted.sentTo} onClose={() => setDeleted(null)} />;
  }

  // A reset link opens the reset screen even on a device that is signed in.
  if (!signedIn || resetTokenFromUrl()) {
    // A different person may be signing in on this device: nothing from the
    // last session's ledger is carried over.
    return <SignedOut onSignedIn={(u, { created = false } = {}) => {
      // A-15: back to the page she was on.
      const after = timeoutFromUrl();
      if (after && !timedOut.current) { window.location.replace(after.returnTo); return; }
      if (after) window.history.replaceState(null, '', after.returnTo);
      timedOut.current = false;
      setData(null);
      synced.current = false;
      setUser(u ?? null); setFresh(created);
      setSignedIn(true); setError(null);
    }} />;
  }

  if (onboarding) {
    const signOut = async () => { await logout(); setUser(null); setSignedIn(false); };
    return (
      <>
        <Onboarding user={user} startAt={fresh ? 'passkey' : null}
                    onSignOut={signOut}
                    onDone={(dest) => {
                      setFresh(false);
                      setUser((u) => ({ ...u, onboarding: { ...u.onboarding, done: true } }));
                      if (dest) go(dest);
                    }} />
        <SessionTimeout onTimeout={signOutIdle} onSignOut={signOut} />
      </>
    );
  }

  if (error) {
    return (
      <Shell theme={theme} setTheme={setTheme}>
        <div className="notice error" style={{ marginTop: 24 }}>
          <strong>Can&apos;t reach the Pearl API.</strong> {String(error.message)}
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

  const { summary, accounts, categories } = data;

  // An empty ledger hides the panels that have nothing to show — but not the
  // ones that exist to fix that, or this is a dead end: the Connect button
  // would set the tab and the same empty state would render over it, which
  // looks exactly like a button that does nothing.
  if (summary.empty && !WORKS_WHEN_EMPTY.includes(panel)) {
    return (
      <Shell theme={theme} setTheme={setTheme} tab={tab} panel={panel} onTab={go}>
        <Empty title="No spending yet">
          <div className="row" style={{ justifyContent: 'center', marginTop: 14 }}>
            <button className="btn primary" onClick={() => go('accounts')}>
              Link your bank
            </button>
          </div>
        </Empty>
      </Shell>
    );
  }

  const signOut = async () => { await logout(); setData(null); setSignedIn(false); };
  return (
    <>
    <SessionTimeout onTimeout={signOutIdle} onSignOut={signOut} />
    <DeviceApprovals />
    <Shell
      theme={theme} setTheme={setTheme} tab={tab} panel={panel} onTab={go}
      counts={{ cashflow: data.review }}
      // The Pearl pages draw their own header (overline + title). Insights
      // has its own month switcher too (GR-28), so the shell picks no month.
      ownTitle={['home', 'insights', 'calendar', 'debts', 'budgets', 'transactions', 'review', 'profile',
                 'accounts', 'rules', 'security', 'income', 'notifications', 'consent', 'data',
                 'protect'].includes(panel)}
      ownSections={OWN_SECTIONS.includes(panel)}
      onSignOut={signOut}
    >
      {panel === 'income' && <IncomeBillsPanel onTab={go} onChanged={load} version={version} />}
      {quickSort && (
        <QuickSort data={quickSort} categories={categories} onClose={() => setQuickSort(null)}
                   onChanged={load} />
      )}
      {panel === 'home' && <HomePanel onTab={go} onChanged={load} onQuickSort={openQuickSort} version={version} />}
      {panel === 'debts' && <DebtsPanel onTab={go} onChanged={load} version={version} />}
      {panel === 'insights' && <InsightsPanel onTab={go} version={version} />}
      {panel === 'calendar' && <CalendarPanel onTab={go} version={version} categories={categories} />}
      {panel === 'review' && (
        <NeedsALook categories={categories} onChanged={load} onTab={go} version={version} />
      )}
      {panel === 'transactions' && (
        <TransactionsList summary={summary} categories={categories} accounts={accounts}
                          reviewCount={data.review} onTab={go} onChanged={load}
                          version={version} />
      )}
      {panel === 'budgets' && (
        <CategoryBudgetsPanel onTab={go} onChanged={load} version={version} />
      )}
      {panel === 'profile' && (
        <ProfilePanel onTab={go} version={version} theme={theme} setTheme={setTheme} onSignOut={signOut} />
      )}
      {panel === 'accounts' && <AccountsPanel onChanged={load} onTab={go} version={version} />}
      {panel === 'rules' && (
        <RulesPanel categories={categories} onTab={go} onChanged={load} version={version} />
      )}
      {panel === 'notifications' && <NotificationsPanel onTab={go} version={version} />}
      {panel === 'consent' && <ConsentPanel onTab={go} version={version} />}
      {panel === 'protect' && <ProtectPanel onTab={go} version={version} />}
      {panel === 'data' && (
        <DataPanel onTab={go} onChanged={load} onDeleted={(info) => {
          // Signed out on the server already; nothing of hers stays on screen.
          setData(null); setUser(null); synced.current = false;
          setDeleted(info); setSignedIn(false); go('home');
        }} />
      )}
      {panel === 'security' && (
        <SecurityPanel onTab={go} onSignOut={signOut} />
      )}
    </Shell>
    </>
  );
}

function Shell({ theme, setTheme, tab, panel, onTab, counts = {}, onSignOut,
                 ownTitle = false, ownSections = false, children }) {
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

  // Theme and sign-out live on the Profile hub (Profile › Appearance); the
  // phone's top bar no longer carries a theme switch (2026-10-21).
  const main = GROUPS.filter((g) => !g.foot);
  const foot = GROUPS.filter((g) => g.foot);
  const navButton = (g) => (
    <button
      key={g.key}
      className={g.foot ? 'nav-foot' : undefined}
      role="tab"
      aria-selected={tab === g.key}
      // The group's first page.
      onClick={() => onTab(g.panels[0])}
    >
      <Icon d={g.icon} />
      <Label full={g.label} short={g.short} />
      {counts[g.key] > 0 && (
        <span className="count" aria-label={`${counts[g.key]} to sort`}>
          {counts[g.key]}
        </span>
      )}
    </button>
  );

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <Logo size={34} />
          <div className="name">pearl</div>
        </div>

        {onTab && (
          <nav className="nav" role="tablist" aria-orientation="vertical" ref={navRef}>
            {main.map(navButton)}
            <div className="nav-spacer" aria-hidden="true" />
            {foot.map(navButton)}
          </nav>
        )}
      </aside>

      <div className="content">
        <div className="topbar">
          <div className="topbar-inner">
            <div className="title">
              {!ownTitle && <h1>{current?.label ?? 'Pearl'}</h1>}
            </div>

          </div>

          {group && group.panels.length > 1 && !group.crumbs && !ownSections && (
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
