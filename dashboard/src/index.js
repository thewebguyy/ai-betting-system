import React from 'react';
import ReactDOM from 'react-dom/client';
import './index.css';
import App from './App';

import { getCLS, getFID, getLCP } from 'web-vitals';

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);

// Performance Monitoring
function sendToAnalytics({ name, delta, id }) {
  console.log(`[Performance] ${name}:`, (delta / 1000).toFixed(3), 's', `(${id})`);
}

getCLS(sendToAnalytics);
getFID(sendToAnalytics);
getLCP(sendToAnalytics);

