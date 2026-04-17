import React, { useEffect, useState } from 'react';
import { getAnalytics, getBets } from '../api';
import { Bar, Doughnut } from 'react-chartjs-2';
import {
    Chart as ChartJS, BarElement, ArcElement, Tooltip, Legend,
    CategoryScale, LinearScale,
} from 'chart.js';

ChartJS.register(BarElement, ArcElement, Tooltip, Legend, CategoryScale, LinearScale);

export default function AnalyticsPage() {
    const [analytics, setAnalytics] = useState(null);
    const [bets, setBets] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    const load = async () => {
        setLoading(true);
        setError(null);
        try {
            const [a, b] = await Promise.all([getAnalytics(), getBets({ limit: 200 })]);
            setAnalytics(a || {});
            setBets(Array.isArray(b) ? b : []);
        } catch (e) {
            console.error('Analytics load error:', e);
            setError('Cannot connect to Intelligence Engine. Please check your network or try again.');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        load();
    }, []);

    if (loading) return <div className="loading-wrapper"><div className="spinner" /><span>Loading analytics…</span></div>;

    if (error) return (
        <div style={{ padding: '4rem', textAlign: 'center' }}>
            <div className="card">
                <div className="icon" style={{ fontSize: '3rem', marginBottom: '1rem' }}>📊</div>
                <h2>Analytics Unavailable</h2>
                <p style={{ color: 'var(--text-secondary)', marginBottom: '1.5rem', maxWidth: '400px', margin: '0 auto 1.5rem' }}>
                    {error}
                </p>
                <button className="btn btn-primary" onClick={load}>🔄 Retry Connection</button>
            </div>
        </div>
    );


    // Win/Draw/Loss doughnut
    const doughnutData = {
        labels: ['Won', 'Lost', 'Void', 'Pending'],
        datasets: [{
            data: [analytics?.won || 0, analytics?.lost || 0, analytics?.void || 0, analytics?.pending || 0],
            backgroundColor: ['#00d4aa', '#ef4444', '#8b5cf6', '#475569'],
            borderWidth: 0,
        }],

    };

    // Profit by bet (bar chart — last 20 settled)
    const settled = bets.filter(b => b.result !== 'pending').slice(-20);
    const barData = {
        labels: settled.map((_, i) => `Bet ${i + 1}`),
        datasets: [{
            label: 'Profit/Loss',
            data: settled.map(b => parseFloat((b.actual_payout - b.stake).toFixed(2))),
            backgroundColor: settled.map(b => b.result === 'won' ? 'rgba(0,212,170,0.7)' : 'rgba(239,68,68,0.7)'),
            borderRadius: 4,
        }],
    };

    const chartOptions = {
        responsive: true,
        plugins: {
            legend: { display: false },
            tooltip: {
                backgroundColor: 'rgba(15,22,41,0.95)',
                borderColor: 'rgba(0,212,170,0.3)',
                borderWidth: 1,
                titleColor: '#f1f5f9',
                bodyColor: '#94a3b8',
            },
        },
        scales: {
            x: { grid: { color: 'rgba(148,163,184,0.06)' }, ticks: { color: '#475569' } },
            y: { grid: { color: 'rgba(148,163,184,0.06)' }, ticks: { color: '#475569' } },
        },
    };

    const doughnutOptions = {
        responsive: true,
        maintainAspectRatio: true,
        plugins: {
            legend: {
                position: 'bottom',
                labels: { color: '#94a3b8', padding: 16, font: { size: 12 } },
            },
        },
        cutout: '65%',
    };

    const kpis = [
        { label: 'ROI', value: `${(analytics?.roi || 0).toFixed(2)}%`, color: (analytics?.roi || 0) >= 0 ? 'positive' : 'negative' },
        { label: 'Yield', value: `${(analytics?.yield_pct || 0).toFixed(2)}%`, color: (analytics?.yield_pct || 0) >= 0 ? 'positive' : 'negative' },
        { label: 'Hit Rate', value: `${(analytics?.hit_rate || 0).toFixed(1)}%`, color: 'neutral' },
        { label: 'Avg Odds', value: (analytics?.avg_odds || 0).toFixed(3), color: 'neutral' },
        { label: 'Total Staked', value: (analytics?.total_staked || 0).toFixed(2), color: 'neutral' },
        { label: 'Net Profit', value: `${(analytics?.total_profit || 0) >= 0 ? '+' : ''}${(analytics?.total_profit || 0).toFixed(2)}`, color: (analytics?.total_profit || 0) >= 0 ? 'positive' : 'negative' },
    ];


    return (
        <div>
            <div className="page-header">
                <h1>Analytics</h1>
                <p>Detailed performance metrics and visualisations</p>
            </div>

            {/* KPI Grid */}
            <div className="grid-3 section">
                {kpis.map(({ label, value, color }) => (
                    <div key={label} className="metric-card">
                        <div className="metric-label">{label}</div>
                        <div className={`metric-value metric-${color}`}>{value}</div>
                    </div>
                ))}
            </div>

            <div className="grid-2">
                {/* Win/Loss doughnut */}
                <div className="card">
                    <div className="card-header"><div className="card-title">🎯 Result Distribution</div></div>
                    <div style={{ maxWidth: 280, margin: '0 auto' }}>
                        <Doughnut data={doughnutData} options={doughnutOptions} />
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'center', gap: '1rem', marginTop: '1rem', flexWrap: 'wrap' }}>
                        {['Won', 'Lost', 'Void', 'Pending'].map((label, i) => {
                            const colors = ['badge-green', 'badge-red', 'badge-purple', 'badge-yellow'];
                            const values = [analytics.won, analytics.lost, analytics.void, analytics.pending];
                            return (
                                <span key={label} className={`badge ${colors[i]}`}>{label}: {values[i]}</span>
                            );
                        })}
                    </div>
                </div>

                {/* P&L bar chart */}
                <div className="card">
                    <div className="card-header"><div className="card-title">📊 Profit / Loss per Bet (Last 20)</div></div>
                    {settled.length === 0 ? (
                        <div className="empty-state"><p>No settled bets to display.</p></div>
                    ) : (
                        <Bar data={barData} options={chartOptions} />
                    )}
                </div>
            </div>

            {/* Recent bets table */}
            <div className="section" style={{ marginTop: '1.5rem' }}>
                <div className="section-title">📋 Recent Bets</div>
                <div className="table-container card" style={{ padding: 0 }}>
                    <table>
                        <thead>
                            <tr>
                                <th>#</th><th>Bookmaker</th><th>Selection</th>
                                <th>Odds</th><th>Stake</th><th>Payout</th>
                                <th>P/L</th><th>Result</th><th>Date</th>
                            </tr>
                        </thead>
                        <tbody>
                            {bets.slice(0, 30).map((b) => {
                                const pl = b.actual_payout - b.stake;
                                return (
                                    <tr key={b.id}>
                                        <td>{b.id}</td>
                                        <td>{b.bookmaker}</td>
                                        <td>{b.selection}</td>
                                        <td>{b.decimal_odds}</td>
                                        <td>{b.stake.toFixed(2)}</td>
                                        <td>{b.actual_payout?.toFixed(2) ?? '—'}</td>
                                        <td style={{ color: pl >= 0 ? 'var(--accent-green)' : 'var(--accent-red)', fontWeight: 600 }}>
                                            {b.result === 'pending' ? '—' : `${pl >= 0 ? '+' : ''}${pl.toFixed(2)}`}
                                        </td>
                                        <td>
                                            <span className={{
                                                won: 'badge badge-green', lost: 'badge badge-red',
                                                void: 'badge badge-purple', pending: 'badge badge-yellow',
                                                push: 'badge badge-blue',
                                            }[b.result] || 'badge badge-yellow'}>{b.result}</span>
                                        </td>
                                        <td>{new Date(b.placed_at).toLocaleDateString()}</td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
}
