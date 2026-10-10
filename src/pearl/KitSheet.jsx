import { useState } from 'react';
import {
  Alert, CategoryChip, DayHeader, EmptyState, FilterChip, PButton, SearchField, StatTile,
  StatusPill, TxRow,
} from './kit.jsx';

// Every kit component in each of its states, for review in light and dark.
// Development only: main.jsx shows it at ?kit=1 and the build leaves it out.
export default function KitSheet() {
  const [q, setQ] = useState('');
  const [month, setMonth] = useState('2026-10');
  const [group, setGroup] = useState('lifestyle');
  return (
    <div className="pk" style={{ background: 'var(--surface-page)', minHeight: '100vh',
                                 padding: 'clamp(16px, 4vw, 48px)', display: 'flex',
                                 flexDirection: 'column', gap: 24 }}>
      <div>
        <p className="pk-overline accent">Pearl kit</p>
        <h1 className="pk-h1">Components</h1>
      </div>

      <section style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'center' }}>
        <CategoryChip label="Dining" />
        <CategoryChip label="Food Delivery" suggested />
        <CategoryChip label="Repayment" />
        <CategoryChip label="Not sorted yet" suggested />
      </section>

      <section style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'center' }}>
        <SearchField value={q} onChange={setQ} placeholder="Search merchants or amounts" />
        <FilterChip label="Month" value={month} onChange={setMonth}
                    options={[{ value: '2026-10', label: 'October' }, { value: '2026-09', label: 'September' }]} />
        <FilterChip label="Account" value="" onChange={() => {}}
                    options={[{ value: '', label: 'All accounts' }]} />
        <FilterChip label="Category" value={group} onChange={setGroup} active={group !== ''}
                    options={[{ value: '', label: 'All categories' }, { value: 'lifestyle', label: 'Lifestyle' }]} />
      </section>

      <div className="pk-tiles">
        <StatTile label="Spent so far" value="$3,144.34" />
        <StatTile label="Income so far" value="$2,150.00" />
        <StatTile label="Not counted" value="$654.50" />
      </div>

      <Alert action="Review">3 transactions need a look. Sorting them keeps your numbers right.</Alert>
      <Alert tone="caution">You’re close to your usual for Lifestyle.</Alert>
      <Alert tone="positive">All sorted.</Alert>
      <StatusPill>Pending · usually clears in 1–3 days</StatusPill>

      <div className="pk-list">
        <DayHeader>Today · Friday, October 9</DayHeader>
        <TxRow name="Uber Eats" meta="Visa ··4421 · Pending" amount={24.8}
               chip={{ label: 'Food Delivery', suggested: true }} />
        <TxRow name="e-Transfer from Priya" meta="TD Chequing ··4417"
               note="Paid you back for Sushi Nami · not income" amount={-42.5} inflow muted
               chip={{ label: 'Repayment' }} />
        <TxRow name="Sushi Nami" meta="Visa ··4421" note="Your share of $85.00 · split with Priya"
               amount={42.5} chip={{ label: 'Dining' }} />
        <DayHeader>Thursday, October 8</DayHeader>
        <TxRow name="Payment to Visa" meta="TD Chequing ··4417"
               note="Card payment · not counted as spending" amount={612} muted
               chip={{ label: 'Transfer' }} />
        <TxRow name="e-Transfer to M. Papas" meta="TD Chequing ··4417" note="Saved or spent? Tell us"
               noteLink amount={200} chip={{ label: 'Not sorted yet', suggested: true }} />
        <TxRow name="Payroll · Acme" meta="TD Chequing ··4417" amount={-2150} inflow
               chip={{ label: 'Income' }} />
      </div>

      <EmptyState title="Nothing matches “sushi place”" action="Clear search"
                  extra={<PButton variant="text">Clear filters</PButton>}>
        Try a shorter word, or check the month and account filters. We search merchant names,
        notes and amounts.
      </EmptyState>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 12, maxWidth: 480 }}>
        <PButton>Yes, that’s right</PButton>
        <PButton variant="secondary">Change category</PButton>
        <PButton variant="text">Clear filters</PButton>
      </div>
    </div>
  );
}
