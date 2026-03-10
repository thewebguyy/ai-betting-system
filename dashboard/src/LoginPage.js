import React, { useState } from 'react';
import { useAuth } from './AuthContext';

export default function LoginPage() {
    const { login } = useAuth();
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');
        setLoading(true);
        try {
            await login(username, password);
        } catch (err) {
            if (err.response?.status === 401) {
                setError('Invalid credentials. Double-check ADMIN_USERNAME and ADMIN_PASSWORD in Railway.');
            } else if (!err.response) {
                setError(`Connection failed. Ensure backend is running at ${err.config?.baseURL}`);
            } else {
                setError(`Login failed: ${err.response?.data?.detail || err.message}`);
            }
        } finally {
            setLoading(false);
        }
    };

    return (
        <div style={{
            minHeight: '100vh',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: 'var(--bg-primary)',
        }}>
            <div style={{
                width: '100%',
                maxWidth: 400,
                background: 'var(--bg-card)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-xl)',
                padding: '2.5rem',
                backdropFilter: 'blur(12px)',
            }}>
                {/* Logo */}
                <div style={{ textAlign: 'center', marginBottom: '2rem' }}>
                    <div style={{
                        width: 56, height: 56,
                        background: 'linear-gradient(135deg, var(--accent-green), var(--accent-blue))',
                        borderRadius: 16,
                        display: 'inline-flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontSize: 28,
                        marginBottom: '1rem',
                    }}>🎯</div>
                    <h1 style={{ fontSize: '1.5rem', marginBottom: '0.375rem' }}>AI Betting Intelligence</h1>
                    <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>Personal value betting system</p>
                </div>

                <form onSubmit={handleSubmit}>
                    <div className="form-group">
                        <label className="form-label">Username</label>
                        <input
                            id="login-username"
                            className="form-input"
                            type="text"
                            value={username}
                            onChange={e => setUsername(e.target.value)}
                            placeholder="admin"
                            required
                        />
                    </div>

                    <div className="form-group">
                        <label className="form-label">Password</label>
                        <input
                            id="login-password"
                            className="form-input"
                            type="password"
                            value={password}
                            onChange={e => setPassword(e.target.value)}
                            placeholder="••••••••"
                            required
                        />
                    </div>

                    {error && (
                        <div style={{
                            background: 'rgba(239,68,68,0.1)',
                            border: '1px solid rgba(239,68,68,0.2)',
                            borderRadius: 8,
                            padding: '0.75rem 1rem',
                            color: 'var(--accent-red)',
                            fontSize: '0.8rem',
                            marginBottom: '1rem',
                        }}>
                            {error}
                        </div>
                    )}

                    <button
                        id="login-submit"
                        className="btn btn-primary"
                        type="submit"
                        disabled={loading}
                        style={{ width: '100%', justifyContent: 'center', marginTop: '0.5rem' }}
                    >
                        {loading ? '⏳ Signing in…' : '🔑 Sign In'}
                    </button>
                </form>
            </div>
        </div>
    );
}
