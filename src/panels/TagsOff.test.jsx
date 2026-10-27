import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { TAGS_ON } from '../features.js';
import { RulesPage } from './RulesPanel.jsx';
import { TxFiltersPanel } from './TxFilters.jsx';

const html = (el) => renderToStaticMarkup(el);

describe('Tags are off for now (2026-10-26, in the backlog)', () => {
  it('is switched off', () => { expect(TAGS_ON).toBe(false); });

  it('Categories and rules has no Tags tab, even asked for one', () => {
    const page = html(<RulesPage rules={[]} tags={[{ tag: 'Ibiza', count: 3, spent: 420 }]} tab="tags" />);
    expect(page).not.toMatch(/>Tags</);
    expect(page).not.toContain('Ibiza');
  });

  it('the filters show no tags when none are passed in', () => {
    const page = html(<TxFiltersPanel filters={{}} thisMonth="2026-10" tags={[]} onApply={() => {}} onClose={() => {}} />);
    expect(page).not.toMatch(/aria-label="Tags"/);
  });
});
