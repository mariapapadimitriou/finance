import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.jsx';
import './styles.css';

// ?kit=1 in development shows every Pearl component; the build drops it.
const Kit = import.meta.env.DEV && new URLSearchParams(window.location.search).has('kit')
  ? React.lazy(() => import('./pearl/KitSheet.jsx')) : null;

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    {Kit ? <React.Suspense fallback={null}><Kit /></React.Suspense> : <App />}
  </React.StrictMode>
);
