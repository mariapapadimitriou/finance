// Small shared presentation pieces.

function Notice({ kind = '', children }) {
  return <div className={`notice ${kind}`}>{children}</div>;
}

export function Empty({ title, children }) {
  return (
    <div className="empty">
      <h2>{title}</h2>
      <div>{children}</div>
    </div>
  );
}

export function Loading({ what = 'data' }) {
  return <div className="empty muted">Loading {what}…</div>;
}

export function ErrorNote({ error, onRetry }) {
  if (!error) return null;
  return (
    <Notice kind="error">
      {String(error.message || error)}
      {onRetry && (
        <>
          {' '}
          <button className="btn quiet" onClick={onRetry}>Retry</button>
        </>
      )}
    </Notice>
  );
}
