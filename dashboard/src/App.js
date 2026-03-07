import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './AuthContext';
import LoginPage from './LoginPage';
import Sidebar from './Sidebar';
import Dashboard from './pages/Dashboard';
import ValueBets from './pages/ValueBets';
import Bankroll from './pages/Bankroll';
import Analytics from './pages/Analytics';
import BetTracker from './pages/BetTracker';
import Reports from './pages/Reports';
import EVCalculator from './pages/EVCalculator';

function ProtectedLayout() {
    const { isAuthenticated } = useAuth();

    if (!isAuthenticated) {
        return <Navigate to="/login" replace />;
    }

    return (
        <div className="app-layout">
            <Sidebar />
            <main className="main-content">
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
            </main>
        </div>
    );
}

export default function App() {
    return (
        <AuthProvider>
            <BrowserRouter>
                <Routes>
                    <Route path="/login" element={<LoginPage />} />
                    <Route path="/*" element={<ProtectedLayout />} />
                </Routes>
            </BrowserRouter>
        </AuthProvider>
    );
}
