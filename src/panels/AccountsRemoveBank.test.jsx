import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { AccountDetail, RemoveBankDialog } from './AccountsPanel.jsx';

// Remove a bank entirely (2026-10-21): for a connection that keeps
// misbehaving, every account on the login comes off and the bank can be
// linked again from scratch.

const html = (el) => renderToStaticMarkup(el);
const base = { counted: true, joint: false, anchor: false, can_anchor: false, owing: false,
               status: 'up_to_date', balance: 400, transactions: 120, history_from: '2025-06-01',
               nickname: '', kind: 'chequing', source: 'plaid' };
const ws = { ...base, id: 'ws1', name: 'Wealthsimple Cash', bank_name: 'Wealthsimple Cash', mask: '2201',
             institution: 'Wealthsimple', item_id: 'item-ws' };
const ws2 = { ...base, id: 'ws2', name: 'Wealthsimple TFSA', bank_name: 'Wealthsimple TFSA', mask: '',
              institution: 'Wealthsimple', item_id: 'item-ws', kind: 'investment', transactions: 8 };

describe('Remove a bank entirely', () => {
  it('a linked account offers it, under Remove this account', () => {
    const out = html(<AccountDetail a={ws} onSave={() => {}} onRemove={() => {}} onRemoveBank={() => {}} />);
    expect(out).toContain('Remove this account');
    expect(out).toContain('Remove Wealthsimple entirely and link it again');
  });

  it('a disconnected account offers it too', () => {
    const out = html(<AccountDetail a={{ ...ws, status: 'disconnected' }} onSave={() => {}} onRemove={() => {}}
                                    onRemoveBank={() => {}} onReconnect={() => {}} onKeepManual={() => {}} />);
    expect(out).toContain('Reconnect');
    expect(out).toContain('Remove Wealthsimple entirely and link it again');
  });

  it('an account with no bank login behind it does not', () => {
    const out = html(<AccountDetail a={{ ...ws, item_id: '', source: 'statement' }} onSave={() => {}}
                                    onRemove={() => {}} onRemoveBank={() => {}} />);
    expect(out).not.toContain('entirely');
  });

  it('the dialog names every account that goes, and asks about their transactions', () => {
    const out = html(<RemoveBankDialog a={ws} siblings={[ws, ws2]} onClose={() => {}} onRemove={() => Promise.resolve()} />);
    expect(out).toContain('Remove Wealthsimple entirely?');
    expect(out).toContain('all 2 of its accounts');
    expect(out).toContain('Wealthsimple Cash ••2201');
    expect(out).toContain('Wealthsimple TFSA');
    expect(out).toContain('128 transactions across them');
    expect(out).toContain('Keep them');
    expect(out).toContain('Delete them too');
    expect(out).toContain('link Wealthsimple again afterwards');
    expect(out).toContain('>Remove Wealthsimple<');
  });
});
