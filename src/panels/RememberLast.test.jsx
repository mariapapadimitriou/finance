import { describe, expect, it, vi } from 'vitest';

vi.mock('../api.js', async (orig) => ({ ...(await orig()), undoChange: vi.fn(async () => ({ ok: true })) }));

describe('Remember on the Sorted card (2026-10-23)', () => {
  it('ticking it puts the change back and saves it again with the rule, so Undo undoes all of it', async () => {
    const api = await import('../api.js');
    const { rememberEntry } = await import('./SortCard.jsx');
    const redo = vi.fn(async (on) => ({ title: on ? 'Moved to Transport.' : 'Moved.', detail: 'd', undo: { n: on ? 2 : 3 },
                                        rule: on ? 'Pearl will do the same for every Lyft from now on.' : '' }));
    const entry = { key: 'k', title: 'Moved.', undo: { n: 1 }, remember: { label: 'Remember for Lyft', redo }, remembered: false };
    const on = await rememberEntry(entry, true);
    expect(api.undoChange).toHaveBeenCalledWith({ n: 1 });
    expect(redo).toHaveBeenCalledWith(true);
    expect(on).toMatchObject({ remembered: true, undo: { n: 2 }, title: 'Moved to Transport.' });
    expect(on.rule).toMatch(/every Lyft/);
    const off = await rememberEntry(on, false);
    expect(api.undoChange).toHaveBeenLastCalledWith({ n: 2 });
    expect(off).toMatchObject({ remembered: false, undo: { n: 3 }, rule: '' });
    expect(await rememberEntry({ key: 'x' }, true)).toEqual({ key: 'x' });
  });
});
