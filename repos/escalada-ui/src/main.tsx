import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { HashRouter } from 'react-router-dom';
import './index.css';
import './styles/animations.css';
import './styles/utilities.css';
import App from './App';
import ErrorBoundary from './components/ErrorBoundary';
import { APP_BUILD_INFO } from './utilis/buildInfo';

const rootElement = document.getElementById('root');
if (!rootElement) {
  throw new Error('Root element not found');
}

document.documentElement.dataset.escaladaBuildMarker = APP_BUILD_INFO.marker;
document.documentElement.dataset.escaladaBuildVersion = APP_BUILD_INFO.version;

createRoot(rootElement).render(
  <StrictMode>
    <ErrorBoundary>
      <HashRouter>
        <App />
      </HashRouter>
    </ErrorBoundary>
  </StrictMode>,
);
