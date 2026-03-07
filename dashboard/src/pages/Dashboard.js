import React, { useEffect, useState, useCallback } from 'react';
import { getAnalytics, getBankroll, getValueBets, triggerScan, fetchLiveOdds } from '../api';
import { useWebSocket } from '../useWebSocket';

function MetricCard({ label, value, sub, color = 'neutral' }) {
    return (
        <div className="metric-card">
            <div className="metric-label">{label}</div>
            <div className={`metric-value metric-${color}`}>{value}</div>
            {sub && <div className="metric-sub">{sub}</div>}
        </div>
    );
}

export default function Dashboard() {
    const [analytics, setAnalytics] = useState(null);
    const [bankroll, setBankroll] = useState([]);
    const [valueBets, setValueBets] = useState([]);
    const [loading, setLoading] = useState(true);
    const [scanning, setScanning] = useState(false);
    const { alerts, connected, clearAlerts } = useWebSocket();

    const loadData = useCallback(async () => {
        try {
            const [a, b, vb] = await Promise.all([
                getAnalytics(), getBankroll(1), getValueBets({ min_ev: 0.05, limit: 5 })
            ]);
            setAnalytics(a);
            setBankroll(b);
            setValueBets(vb);
        } catch (e) {
            console.error(e);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { loadData(); }, [loadData]);

    const handleScan = async () => {
        setScanning(true);
        try {
            await triggerScan();
            setTimeout(loadData, 3000);
        } finally {
            setScanning(false);
        }
    };

    const handleFetchOdds = async () => {
        await fetchLiveOdds();
    };

    const currentBalance = bankroll[0]?.balance ?? 0;
    const roiColor = analytics?.roi >= 0 ? 'positive' : 'negative';

    if (loading) {
        return (
            <div className="loading-wrapper">
                <div className="spinner" />
                <span>Loading dashboard…</span>
            </div>
        );
    }

    return (
        <div>
            {/* Header */}
            <div className="page-header" style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
                <div>
                    <h1>Dashboard</h1>
                    <p style={{ marginTop: '0.25rem' }}>Real-time betting intelligence overview</p>
                </div>
                <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                        <div className="pulse-dot" style={{ background: connected ? 'var(--accent-green)' : 'var(--accent-red)' }} />
                        {connected ? 'Live' : 'Disconnected'}
                    </div>
                    <button className="btn btn-secondary" onClick={handleFetchOdds} id="fetch-odds-btn">
                        🔄 Fetch Odds
                    </button>
                    <button className="btn btn-primary" onClick={handleScan} disabled={scanning} id="scan-btn">
                        {scanning ? '⏳ Scanning…' : '🎯 Scan Value Bets'}
                    </button>
                </div>
            </div>

            {/* Real-time alerts */}
            {alerts.length > 0 && (
                <div className="section">
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
                        <div className="section-title">🔔 Live Alerts ({alerts.length})</div>
                        <button className="btn btn-secondary" onClick={clearAlerts} style={{ padding: '0.25rem 0.75rem', fontSize: '0.75rem' }}>Clear</button>
                    </div>
                    {alerts.slice(0, 3).map((alert, i) => (
                        <div key={i} className="alert-banner alert-value">
                            <span>🎯</span>
                            <div>
                                <div style={{ fontWeight: 600, fontSize: '0.875rem' }}>{alert.event_type}</div>
                                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>{alert.timestamp}</div>
                            </div>
                        </div>
                    ))}
                </div>
            )}

            {/* KPI Grid */}
            <div className="grid-4 section">
                <MetricCard
                    label="Current Bankroll"
                    value={`${currentBalance.toFixed(2)}`}
                    sub="Latest snapshot"
                    color="neutral"
                />
                <MetricCard
                    label="ROI"
                    value={`${analytics?.roi?.toFixed(2) ?? 0}%`}
                    sub={`${analytics?.total_bets ?? 0} bets settled`}
                    color={roiColor}
                />
                <MetricCard
                    label="Hit Rate"
                    value={`${analytics?.hit_rate?.toFixed(1) ?? 0}%`}
                    sub={`${analytics?.won ?? 0}W / ${analytics?.lost ?? 0}L`}
                    color="neutral"
                />
                <MetricCard
                    label="Total Profit"
                    value={`${analytics?.total_profit >= 0 ? '+' : ''}${analytics?.total_profit?.toFixed(2) ?? 0}`}
                    sub={`Staked: ${analytics?.total_staked?.toFixed(2) ?? 0}`}
                    color={analytics?.total_profit >= 0 ? 'positive' : 'negative'}
                />
            </div>

            <div className="grid-2">
                {/* Top Value Bets */}
                <div className="card">
                    <div className="card-header">
                        <div className="card-title">🎯 Top Value Bets</div>
                        <a href="/value-bets" style={{ fontSize: '0.75rem', color: 'var(--accent-green)', textDecoration: 'none' }}>View all →</a>
                    </div>
                    {valueBets.length === 0 ? (
                        <div className="empty-state">
                            <div className="icon">🔍</div>
                            <p>No value bets detected. Run a scan to find opportunities.</p>
                        </div>
                    ) : (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                            {valueBets.map((vb) => (
                                <div key={vb.id} style={{
                                    background: 'var(--bg-elevated)',
                                    border: '1px solid var(--border)',
                                    borderRadius: 'var(--radius-md)',
                                    padding: '1rem',
                                }}>
                                    <div style={{ display: 'flex', justify: 'space-between', alignItems: 'flex-start', gap: '0.5rem' }}>
                                        <div style={{ flex: 1 }}>
                                            <div style={{ fontWeight: 600, fontSize: '0.875rem' }}>
                                                {vb.selection} — {vb.bookmaker}
                                            </div>
                                            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
                                                Odds: {vb.decimal_odds} | Model: {(vb.model_prob * 100).toFixed(1)}%
                                            </div>
                                        </div>
                                        <div style={{ textAlign: 'right' }}>
                                            <div className="badge badge-green">EV {(vb.ev * 100).toFixed(1)}%</div>
                                        </div>
                                    </div>
                                    <div className="ev-bar" style={{ marginTop: '0.75rem' }}>
                                        <div className="ev-bar-fill" style={{ width: `${Math.min(vb.edge * 200, 100)}%` }} />
                                    </div>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '0.375rem' }}>
                                        <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Edge: {(vb.edge * 100).toFixed(2)}%</span>
                                        <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Kelly: {vb.suggested_stake?.toFixed(2) ?? '—'}</span>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>

                {/* Stats Panel */}
                <div className="card">
                    <div className="card-header">
                        <div className="card-title">📈 Performance Stats</div>
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                        {[
                            { label: 'Total Bets', value: analytics?.total_bets ?? 0 },
                            { label: 'Average Odds', value: analytics?.avg_odds?.toFixed(3) ?? '—' },
                            { label: 'Pending Bets', value: analytics?.pending ?? 0 },
                            { label: 'Yield', value: `${analytics?.yield_pct?.toFixed(2) ?? 0}%` },
                        ].map(({ label, value }) => (
                            <div key={label} style={{
                                display: 'flex',
                                justifyContent: 'space-between',
                                alignItems: 'center',
                                padding: '0.75rem',
                                background: 'var(--bg-elevated)',
                                borderRadius: 'var(--radius-sm)',
                                border: '1px solid var(--border)',
                            }}>
                                <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>{label}</span>
                                <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, color: 'var(--text-primary)' }}>{value}</span>
                            </div>
                        ))}
                    </div>
                </div>
            </div>
        </div>
    );
}
