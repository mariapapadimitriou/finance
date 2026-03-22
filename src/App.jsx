import { useState, useEffect } from 'react';
import Header from './components/Header.jsx';
import TabNav from './components/TabNav.jsx';
import RegimeSummaryBar from './components/RegimeSummaryBar.jsx';
import EquitiesPanel from './panels/EquitiesPanel.jsx';
import FixedIncomePanel from './panels/FixedIncomePanel.jsx';
import DifficultyPanel from './panels/DifficultyPanel.jsx';
import MacroPanel from './panels/MacroPanel.jsx';

export default function App() {
  const [market, setMarket]   = useState('US');
  const [lookback, setLookback] = useState(20);
  const [tab, setTab]         = useState('macro');
  const [theme, setTheme]     = useState('dark');

  // Apply theme to root element so CSS vars take effect everywhere
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);

  const toggleTheme = () => setTheme(t => t === 'dark' ? 'light' : 'dark');

  return (
    <>
      <Header
        market={market}
        onMarket={setMarket}
        lookback={lookback}
        onLookback={setLookback}
        theme={theme}
        onThemeToggle={toggleTheme}
      />
      <TabNav tab={tab} onTab={setTab} />
      <RegimeSummaryBar market={market} theme={theme} />
      <main>
        {tab === 'equities'    && <EquitiesPanel    market={market} lookback={lookback} theme={theme} />}
        {tab === 'fixedincome' && <FixedIncomePanel market={market} lookback={lookback} theme={theme} />}
        {tab === 'difficulty'  && <DifficultyPanel  market={market} lookback={lookback} theme={theme} />}
        {tab === 'macro'       && <MacroPanel       market={market} theme={theme} />}
      </main>
    </>
  );
}
