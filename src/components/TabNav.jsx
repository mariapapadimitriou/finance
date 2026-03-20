export default function TabNav({ tab, onTab }) {
  const tabs = [
    { id: 'morning',     label: 'Morning Brief' },
    { id: 'equities',    label: 'Equities' },
    { id: 'fixedincome', label: 'Fixed Income' },
    { id: 'difficulty',  label: 'Trading Difficulty' },
    { id: 'macro',       label: 'Macro' },
  ];

  return (
    <div className="tabs">
      {tabs.map(t => (
        <button
          key={t.id}
          className={`tab${tab === t.id ? ' active' : ''}`}
          onClick={() => onTab(t.id)}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}
