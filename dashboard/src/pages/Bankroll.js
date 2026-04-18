import React, { useEffect, useState } from 'react';
import { getBankroll, addBankrollSnapshot } from '../api';

import { Line } from 'react-chartjs-2';
import {
    Chart as ChartJS, LineElement, PointElement, LinearScale, CategoryScale,
    Filler, Tooltip, Legend,
} from 'chart.js';
import toast from 'react-hot-toast';
import { CardSkeleton, ChartSkeleton } from '../components/Skeleton';

ChartJS.register(LineElement, PointElement, LinearScale, CategoryScale, Filler, Tooltip, Legend);


export default function BankrollPage() {
    const [snapshots, setSnapshots] = useState([]);

    const [newBalance, setNewBalance] = useState('');
    const [note, setNote] = useState('');
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);

    const load = async () => {
        setLoading(true);
        try {
            const s = await getBankroll(30);
            const validSnapshots = Array.isArray(s) ? s : [];
            setSnapshots([...validSnapshots].reverse()); // chronological

        } catch (err) {
            toast.error('Failed to load bankroll data');
        } finally {
            setTimeout(() => setLoading(false), 200);
        }
    };

    useEffect(() => { load(); }, []);

    const handleAddSnapshot = async (e) => {
        e.preventDefault();
        if (!newBalance) return;
        
        setSaving(true);
        const saveToast = toast.loading('Saving snapshot...');
        try {
            await addBankrollSnapshot({ balance: parseFloat(newBalance), note });
            setNewBalance('');
            setNote('');
            toast.success('Snapshot saved successfully', { id: saveToast });
            load();
        } catch (err) {
            toast.error('Failed to save snapshot', { id: saveToast });
        } finally {
            setSaving(false);
        }
    };



    // Chart data
    const chartData = {
        labels: snapshots.map(s => new Date(s.snapshot_at).toLocaleDateString()),
        datasets: [{
            label: 'Bankroll',
            data: snapshots.map(s => s.balance),
            borderColor: '#00d4aa',
            backgroundColor: 'rgba(0, 212, 170, 0.08)',
            borderWidth: 2,
            fill: true,
            tension: 0.4,
            pointRadius: 4,
            pointBackgroundColor: '#00d4aa',
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

    const currentBalance = snapshots[snapshots.length - 1]?.balance ?? 0;
    const startBalance = snapshots[0]?.balance ?? currentBalance;
    const growth = startBalance > 0 ? ((currentBalance - startBalance) / startBalance * 100) : 0;

    if (loading) return (
        <div className="fade-in">
            <div className="page-header">
                <h1>Bankroll Tracker</h1>
                <p>Monitor your bankroll growth and manage staking</p>
            </div>
            <div className="grid-3 section">
                <CardSkeleton />
                <CardSkeleton />
                <CardSkeleton />
            </div>
            <div className="grid-2">
                <ChartSkeleton />
                <CardSkeleton />
            </div>
        </div>
    );

    return (
        <div className="fade-in">
            <div className="page-header">
                <h1>Bankroll Tracker</h1>
                <p>Monitor your bankroll growth and manage staking</p>
            </div>

            {/* Quick stats */}
            <div className="grid-3 section">
                {[
                    { label: 'Current Balance', value: currentBalance.toFixed(2), color: 'neutral' },
                    { label: 'Growth', value: `${growth >= 0 ? '+' : ''}${growth.toFixed(2)}%`, color: growth >= 0 ? 'positive' : 'negative' },
                    { label: 'Total Snapshots', value: snapshots.length, color: 'neutral' },
                ].map(({ label, value, color }) => (
                    <div key={label} className="metric-card">
                        <div className="metric-label">{label}</div>
                        <div className={`metric-value metric-${color}`}>{value}</div>
                    </div>
                ))}
            </div>

            <div className="grid-2">
                {/* Chart */}
                <div className="card" style={{ gridColumn: 'span 1' }}>
                    <div className="card-header"><div className="card-title">📈 Bankroll History</div></div>
                    {snapshots.length < 2 ? (
                        <div className="empty-state"><p>Add at least 2 snapshots to see the chart.</p></div>
                    ) : (
                        <Line data={chartData} options={chartOptions} />
                    )}
                </div>

                {/* Update form */}
                <div className="card">
                    <div className="card-header"><div className="card-title">💰 Add Snapshot</div></div>
                    <form onSubmit={handleAddSnapshot}>
                        <div className="form-group">
                            <label className="form-label">New Balance</label>
                            <input className="form-input" type="number" step="0.01" min="0"
                                placeholder="1000.00"
                                value={newBalance}
                                onChange={e => setNewBalance(e.target.value)}
                                id="bankroll-balance-input"
                                required
                            />
                        </div>
                        <div className="form-group">
                            <label className="form-label">Note (optional)</label>
                            <input className="form-input" type="text"
                                placeholder="After Saturday winnings…"
                                value={note}
                                onChange={e => setNote(e.target.value)}
                                id="bankroll-note-input"
                            />
                        </div>
                        <button className="btn btn-primary" type="submit" id="bankroll-submit-btn"
                            disabled={saving}
                            style={{ width: '100%', justifyContent: 'center' }}>
                            {saving ? '⏳ Saving…' : '✅ Save Snapshot'}
                        </button>
                    </form>


                    <div style={{ marginTop: '1.5rem' }}>
                        <div className="card-title" style={{ marginBottom: '0.75rem' }}>📋 Recent Snapshots</div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', maxHeight: 200, overflowY: 'auto' }}>
                            {[...snapshots].reverse().slice(0, 8).map(s => (
                                <div key={s.id} style={{
                                    display: 'flex', justifyContent: 'space-between', padding: '0.5rem 0.75rem',
                                    background: 'var(--bg-elevated)', borderRadius: 6, fontSize: '0.8rem',
                                }}>
                                    <span style={{ color: 'var(--text-muted)' }}>{new Date(s.snapshot_at).toLocaleDateString()}</span>
                                    <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{s.balance.toFixed(2)}</span>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
