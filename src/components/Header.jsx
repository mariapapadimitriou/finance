export default function Header({ market, onMarket, lookback, onLookback, theme, onThemeToggle }) {
  const markets = [
    { code: 'US', flag: '🇺🇸' },
    { code: 'CA', flag: '🇨🇦' },
    { code: 'MX', flag: '🇲🇽' },
    { code: 'BR', flag: '🇧🇷' },
    { code: 'CL', flag: '🇨🇱' },
  ];

  const periods = [
    { value: 5,   label: '5D' },
    { value: 20,  label: '1M' },
    { value: 60,  label: '3M' },
    { value: 120, label: '6M' },
    { value: 252, label: '1Y' },
  ];

  return (
    <header>
      <div className="logo">
        RED<span style={{ color: 'var(--dim)' }}>EYE</span>
        <sub>equity</sub>
      </div>
      <div className="hbar-right">
        <div className="lkb">
          <span>PERIOD</span>
          <select value={lookback} onChange={e => onLookback(parseInt(e.target.value))}>
            {periods.map(p => (
              <option key={p.value} value={p.value}>{p.label}</option>
            ))}
          </select>
        </div>
        <div className="mkt-group">
          {markets.map(m => (
            <button
              key={m.code}
              className={`mkt-btn${market === m.code ? ' active' : ''}`}
              onClick={() => onMarket(m.code)}
            >
              {m.flag} {m.code}
            </button>
          ))}
        </div>
        <button className="theme-toggle" onClick={onThemeToggle} title="Toggle dark / light mode">
          <span className="theme-toggle-icon">{theme === 'dark' ? '☀' : '☾'}</span>
          {theme === 'dark' ? 'LIGHT' : 'DARK'}
        </button>
      </div>
    </header>
  );
}
