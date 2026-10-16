import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { Mark } from './PearlEarned.jsx';
import { pathFill } from './WinsPanel.jsx';

const html = (el) => renderToStaticMarkup(el);

describe('You earned a pearl (THL-256)', () => {
  it('the still mark is the Logo/Mark image behind a nacre halo, hidden from readers', () => {
    const out = html(<Mark still />);
    expect(out).toContain('class="pe-mark still"');
    expect(out).toContain('aria-hidden="true"');
    expect(out).toContain('pe-halo');
    expect(out).toContain('<img');
    expect(out).toContain('logo-mark');
  });

  it('with motion, the Lottie gets a box of its own', () => {
    const out = html(<Mark />);
    expect(out).toContain('class="pe-lottie"');
    expect(out).not.toContain('<img');
  });
});

describe('the path line fills to the last pearl earned', () => {
  const p = (state) => ({ state });
  it('three of six earned is 40% along', () => {
    expect(pathFill([p('earned'), p('earned'), p('earned'), p('next'), p('todo'), p('todo')])).toBe(40);
  });
  it('none earned is empty, all earned is full', () => {
    expect(pathFill([p('next'), p('todo'), p('todo'), p('todo'), p('todo'), p('todo')])).toBe(0);
    expect(pathFill(Array(6).fill(p('earned')))).toBe(100);
  });
});
