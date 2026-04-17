import React, { useState, useEffect, lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Sidebar from './Sidebar';
import Dashboard from './pages/Dashboard';
import ValueBets from './pages/ValueBets';

// Lazy loaded components for performance optimization
const Bankroll = lazy(() => import('./pages/Bankroll'));
const Analytics = lazy(() => import('./pages/Analytics'));
const BetTracker = lazy(() => import('./pages/BetTracker'));
const Reports = lazy(() => import('./pages/Reports'));
const EVCalculator = lazy(() => import('./pages/EVCalculator'));

// Loading fallback for lazy routes
const PageLoader = () => (
    <div className="loading-wrapper" style={{ height: '50vh' }}>
        <div className="spinner" />
        <span style={{ marginTop: '1rem', color: 'var(--text-muted)' }}>Loading module...</span>
    </div>
);


function BackendOfflineBanner({ error }) {
    return (
        <div className="offline-banner">

            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <span style={{ fontSize: '1.2rem' }}>⚠️</span>
                <span>Intelligence Engine Offline: {error || 'Connection timed out'}</span>
            </div>
            <button 
                onClick={() => window.location.reload()}
                style={{
                    background: 'white',
                    color: '#ef4444',
                    border: 'none',
                    padding: '0.4rem 1rem',
                    borderRadius: '4px',
                    fontSize: '0.75rem',
                    fontWeight: 700,
                    cursor: 'pointer',
                    textTransform: 'uppercase'
                }}
            >
                Retry Connection
            </button>
        </div>
    );
}

class ErrorBoundary extends React.Component {
    constructor(props) {
        super(props);
        this.state = { hasError: false };
    }
    static getDerivedStateFromError() { return { hasError: true }; }
    componentDidCatch(error, errorInfo) { console.error("Layout Error Boundary caught:", error, errorInfo); }
    render() {
        if (this.state.hasError) {
            return (
                <div style={{ padding: '4rem', textAlign: 'center' }}>
                    <div className="card" style={{ maxWidth: '500px', margin: '0 auto' }}>
                        <div style={{ fontSize: '3rem', marginBottom: '1rem' }}>⚠️</div>
                        <h2>Something went wrong</h2>
                        <p style={{ color: 'var(--text-secondary)', marginBottom: '1.5rem' }}>
                            A critical error occurred while loading this view.
                        </p>
                        <button className="btn btn-primary" onClick={() => window.location.reload()}>
                            🔄 Reload Dashboard
                        </button>
                    </div>
                </div>
            );
        }
        return this.props.children;
    }
}

function ProtectedLayout() {

    const [isBackendDown, setIsBackendDown] = useState(false);
    const [backendError, setBackendError] = useState('');

    useEffect(() => {
        const handleStatusChange = (e) => {
            setIsBackendDown(e.detail.isDown);
            setBackendError(e.detail.error);
        };
        window.addEventListener('backend-status-change', handleStatusChange);
        return () => window.removeEventListener('backend-status-change', handleStatusChange);
    }, []);

    return (
        <div className="app-layout">
            {isBackendDown && <BackendOfflineBanner error={backendError} />}
            <Sidebar />
            <main className="main-content" style={{ marginTop: isBackendDown ? '48px' : 0 }}>
                <ErrorBoundary>
                    <Suspense fallback={<PageLoader />}>
                        <Routes>
                            <Route path="/" element={<Dashboard />} />
                            <Route path="/value-bets" element={<ValueBets />} />
                            <Route path="/bankroll" element={<Bankroll />} />
                            <Route path="/analytics" element={<Analytics />} />
                            <Route path="/bets" element={<BetTracker />} />
                            <Route path="/reports" element={<Reports />} />
                            <Route path="/ev-calc" element={<EVCalculator />} />
                            <Route path="*" element={<Navigate to="/" replace />} />
                        </Routes>
                    </Suspense>
                </ErrorBoundary>
            </main>


        </div>
    );
}

import { Toaster } from 'react-hot-toast';

export default function App() {
    return (
        <BrowserRouter>
            <Toaster position="top-right" toastOptions={{
                duration: 4000,
                style: {
                    background: '#0f1629',
                    color: '#f1f5f9',
                    border: '1px solid rgba(0, 212, 170, 0.2)',
                    fontSize: '0.875rem'
                }
            }} />
            <Routes>
                <Route path="/*" element={<ProtectedLayout />} />
            </Routes>
        </BrowserRouter>
    );
}


