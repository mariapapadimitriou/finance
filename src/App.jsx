import { useState } from 'react';
import Header from './components/Header.jsx';
import TabNav from './components/TabNav.jsx';
import RegimeSummaryBar from './components/RegimeSummaryBar.jsx';
import EquitiesPanel from './panels/EquitiesPanel.jsx';
import FixedIncomePanel from './panels/FixedIncomePanel.jsx';
import DifficultyPanel from './panels/DifficultyPanel.jsx';
import MorningBriefPanel from './panels/MorningBriefPanel.jsx';
import MacroPanel from './panels/MacroPanel.jsx';

export default function App() {
  const [market, setMarket] = useState('US');
  const [lookback, setLookback] = useState(20);
  const [tab, setTab] = useState('morning');

  return (
    <>
      <Header
        market={market}
        onMarket={setMarket}
        lookback={lookback}
        onLookback={setLookback}
      />
      <TabNav tab={tab} onTab={setTab} />
      <RegimeSummaryBar market={market} />
      <main>
        {tab === 'morning'     && <MorningBriefPanel market={market} />}
        {tab === 'equities'    && <EquitiesPanel    market={market} lookback={lookback} />}
        {tab === 'fixedincome' && <FixedIncomePanel market={market} lookback={lookback} />}
        {tab === 'difficulty'  && <DifficultyPanel  market={market} lookback={lookback} />}
        {tab === 'macro'       && <MacroPanel       market={market} />}
      </main>
    </>
  );
}
