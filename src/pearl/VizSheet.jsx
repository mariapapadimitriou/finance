import { useState } from 'react';
import {
  Breakdown, PearlProgress, ProgressBar, RangeBand, Slider, SnapshotBar,
} from './viz.jsx';
import { projection, sliderBounds, sliderWords, whatIf } from './vizMath.js';

// Every state of the data visualisation patterns (THL-110, V-01 to V-05) as
// the pattern sheets draw them, in light and in dark. Part of the kit sheet
// at ?kit=1. The light column follows the page, so under a dark system
// setting both columns are dark; switch the app to light to compare.

const NOW = '2026-10';
const PACE = { best: { saved: 600 }, quietest: { saved: 200 }, usual: 263 };
const TO_GO = 2400;

const CATEGORIES = [
  { name: 'Rent', amount: 1050 }, { name: 'Groceries', amount: 412 },
  { name: 'Dining out', amount: 214 }, { name: 'Transit', amount: 120 },
];
const MANY = [...CATEGORIES, { name: 'Phone', amount: 80 }, { name: 'Books', amount: 60 },
  { name: 'Gifts', amount: 40 }, { name: 'Pets', amount: 35 }];

const SNAPSHOT = {
  category: 'Lifestyle', usualMonth: 1150, usualByToday: 445, day: 12, daysInMonth: 31,
  monthsOfHistory: 4,
};

function State({ name, children }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
      <p className="text-overline" style={{ margin: 0, color: 'var(--ink-muted)' }}>{name}</p>
      {children}
    </div>
  );
}

function Group({ title, children }) {
  return (
    <section style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-5)' }}>
      <h2 className="display-heading-3" style={{ margin: 0 }}>{title}</h2>
      {children}
    </section>
  );
}

function WhatIfState({ at, focus = false }) {
  const bounds = sliderBounds(PACE.usual);
  const [value, setValue] = useState(at === 'max' ? bounds.max : at === 'moved' ? 310 : bounds.min);
  const current = projection(TO_GO, PACE, NOW);
  const result = whatIf({ toGo: TO_GO, pace: PACE, now: NOW, current }, value);
  const words = sliderWords(value, result);
  return (
    <>
      <Slider value={value} bounds={bounds} onChange={setValue} label="Put aside"
              valueText={words} className={focus ? 'show-focus' : ''} />
      <p className="text-label viz-muted" style={{ margin: 0 }}>{words}</p>
    </>
  );
}

function Column({ theme }) {
  return (
    <div data-theme={theme} style={{
      flex: '1 1 320px', minWidth: 0, display: 'flex', flexDirection: 'column',
      gap: 'var(--space-8)', padding: 'var(--space-6)', borderRadius: 'var(--radius-md)',
      background: 'var(--surface-card)', color: 'var(--ink)',
    }}>
      <p className="text-overline" style={{ margin: 0, color: 'var(--link)' }}>
        THL-110 · {theme}
      </p>

      <Group title="V-01 Goal progress">
        <State name="Not started">
          <ProgressBar label="Japan trip" value="$0 of $3,000" share={0} />
        </State>
        <State name="In progress">
          <ProgressBar label="Japan trip" value="$750 of $3,000" share={0.25} />
        </State>
        <State name="Done">
          <ProgressBar label="First stop" value="$500 · done" share={1} tone="positive" />
        </State>
        <State name="Two steps">
          <div className="gl-pair">
            <ProgressBar label="First stop" value="$500 · done" share={1} tone="positive" />
            <ProgressBar label="Full Anchor" value="$1,800 to go" share={0.4} />
          </div>
        </State>
        <State name="Anchor hero (not yet in Goals)">
          <PearlProgress title="Anchor" saved={1800} target={3000} share={0.6} delta={300} />
          <PearlProgress title="Anchor" saved={1680} target={3000} share={0.56} delta={-120} />
          <PearlProgress title="Anchor" saved={30} target={3000} share={0.01} delta={0} />
        </State>
      </Group>

      <Group title="V-02 Date-range projection">
        <State name="Range"><RangeBand now={NOW} from="2027-03" to="2027-06" /></State>
        <State name="Narrow"><RangeBand now={NOW} from="2026-12" to="2026-12" /></State>
        <State name="Runs past the axis"><RangeBand now={NOW} from="2027-05" to="2027-11" /></State>
        <State name="Beyond the axis"><RangeBand now={NOW} from="2027-11" to="2028-03" /></State>
        <State name="No date"><RangeBand now={NOW} /></State>
      </Group>

      <Group title="V-03 This month vs usual">
        <State name="Under pace"><SnapshotBar {...SNAPSHOT} spent={330} /></State>
        <State name="On pace"><SnapshotBar {...SNAPSHOT} spent={460} /></State>
        <State name="Over pace"><SnapshotBar {...SNAPSHOT} spent={640} /></State>
        <State name="Over the month"><SnapshotBar {...SNAPSHOT} spent={1290} /></State>
        <State name="Tick hidden"><SnapshotBar {...SNAPSHOT} spent={460} showTick={false} /></State>
      </Group>

      <Group title="V-04 Category breakdown">
        <State name="Breakdown"><Breakdown items={CATEGORIES} daysOfData={40} /></State>
        <State name="Everything else"><Breakdown items={MANY} daysOfData={40} /></State>
        <State name="Thin data"><Breakdown items={CATEGORIES.slice(0, 2)} daysOfData={6} /></State>
        <State name="Empty"><Breakdown items={[]} daysOfData={40} /></State>
      </Group>

      <Group title="V-05 What-if slider">
        <State name="Min"><WhatIfState at="min" /></State>
        <State name="Moved"><WhatIfState at="moved" /></State>
        <State name="Max"><WhatIfState at="max" /></State>
        <State name="Focused"><WhatIfState at="moved" focus /></State>
      </Group>
    </div>
  );
}

export default function VizSheet() {
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-6)' }}>
      <Column theme="light" />
      <Column theme="dark" />
    </div>
  );
}
