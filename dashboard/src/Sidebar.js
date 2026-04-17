import React, { useState } from 'react';
import { NavLink } from 'react-router-dom';

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
    const [isOpen, setIsOpen] = useState(false);

    const toggle = () => setIsOpen(!isOpen);
    const close = () => setIsOpen(false);

    return (
        <>
            <button className="hamburger" onClick={toggle} aria-label="Toggle Menu">
                {isOpen ? '✕' : '☰'}
            </button>

            {isOpen && <div 
                onClick={close}
                style={{
                    position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', 
                    zIndex: 900, backdropFilter: 'blur(4px)'
                }} 
            />}

            <aside className={`sidebar ${isOpen ? 'open' : ''}`}>
                {/* Logo */}
                <div className="sidebar-logo">
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

                {/* Nav */}
                <nav className="sidebar-nav">
                    {navItems.map(({ to, icon, label }) => (
                        <NavLink
                            key={to}
                            to={to}
                            end={to === '/'}
                            className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}
                            onClick={close}
                        >
                            <span>{icon}</span>
                            <span>{label}</span>
                        </NavLink>
                    ))}
                </nav>

                {/* Footer */}
                <div style={{ padding: '1rem 0.75rem', borderTop: '1px solid var(--border)' }}>
                    <p style={{ fontSize: '0.65rem', color: 'var(--text-muted)', textAlign: 'center' }}>
                        For personal use only
                    </p>
                </div>
            </aside>
        </>
    );
}

