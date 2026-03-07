import React, { useState } from 'react';
import { NavLink } from 'react-router-dom';
import { useAuth } from './AuthContext';

const navItems = [
    { to: '/', icon: '🏠', label: 'Dashboard' },
    { to: '/value-bets', icon: '🎯', label: 'Value Bets' },
    { to: '/bankroll', icon: '💰', label: 'Bankroll' },
    { to: '/analytics', icon: '📊', label: 'Analytics' },
    { to: '/bets', icon: '📋', label: 'Bet Tracker' },
    { to: '/reports', icon: '📄', label: 'Reports' },
    { to: '/ev-calc', icon: '🧮', label: 'EV Calculator' },
];

export default function Sidebar() {
    const { logout } = useAuth();

    return (
        <aside style={{
            position: 'fixed',
            left: 0, top: 0, bottom: 0,
            width: 240,
            background: 'rgba(10, 14, 26, 0.95)',
            borderRight: '1px solid var(--border)',
            backdropFilter: 'blur(20px)',
            display: 'flex',
            flexDirection: 'column',
            zIndex: 100,
            padding: '1.5rem 0',
        }}>
            {/* Logo */}
            <div style={{ padding: '0 1.25rem 1.5rem', borderBottom: '1px solid var(--border)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                    <div style={{
                        width: 36, height: 36,
                        background: 'linear-gradient(135deg, var(--accent-green), var(--accent-blue))',
                        borderRadius: 10,
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        fontSize: 18,
                    }}>🎯</div>
                    <div>
                        <div style={{ fontWeight: 700, fontSize: '0.875rem' }}>AI Betting</div>
                        <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Intelligence System</div>
                    </div>
                </div>
            </div>

            {/* Nav */}
            <nav style={{ flex: 1, padding: '1rem 0.75rem', display: 'flex', flexDirection: 'column', gap: 4 }}>
                {navItems.map(({ to, icon, label }) => (
                    <NavLink
                        key={to}
                        to={to}
                        end={to === '/'}
                        style={({ isActive }) => ({
                            display: 'flex',
                            alignItems: 'center',
                            gap: '0.625rem',
                            padding: '0.625rem 0.875rem',
                            borderRadius: 'var(--radius-sm)',
                            textDecoration: 'none',
                            fontSize: '0.875rem',
                            fontWeight: 500,
                            transition: 'var(--transition)',
                            color: isActive ? 'var(--accent-green)' : 'var(--text-secondary)',
                            background: isActive ? 'rgba(0, 212, 170, 0.08)' : 'transparent',
                            border: isActive ? '1px solid rgba(0, 212, 170, 0.15)' : '1px solid transparent',
                        })}
                    >
                        <span>{icon}</span>
                        <span>{label}</span>
                    </NavLink>
                ))}
            </nav>

            {/* Footer / logout */}
            <div style={{ padding: '1rem 0.75rem', borderTop: '1px solid var(--border)' }}>
                <button
                    onClick={logout}
                    className="btn btn-secondary"
                    style={{ width: '100%', justifyContent: 'center', fontSize: '0.8rem' }}
                    id="sidebar-logout"
                >
                    🚪 Sign Out
                </button>
                <p style={{ fontSize: '0.65rem', color: 'var(--text-muted)', textAlign: 'center', marginTop: '0.75rem' }}>
                    For personal use only
                </p>
            </div>
        </aside>
    );
}
