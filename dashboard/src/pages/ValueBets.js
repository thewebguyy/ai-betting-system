import React, { useEffect, useState } from 'react';
import { getValueBets, triggerScan } from '../api';

const STATUS_BADGE = {
    pending: 'badge-yellow',
    placed: 'badge-blue',
    won: 'badge-green',
    lost: 'badge-red',
    void: 'badge-purple',
};

export default function ValueBetsPage() {
    const [bets, setBets] = useState([]);
    const [loading, setLoading] = useState(true);
    const [scanning, setScanning] = useState(false);
    const [minEv, setMinEv] = useState(0);
    const [filterStatus, setFilterStatus] = useState('');

    const load = async () => {
        setLoading(true);
        try {
            const data = await getValueBets({ min_ev: minEv, status: filterStatus || undefined, limit: 100 });
            setBets(Array.isArray(data) ? data : []);
        } finally {

            setLoading(false);
        }
    };

    useEffect(() => { load(); }, [minEv, filterStatus]); // eslint-disable-line

    const handleScan = async () => {
        setScanning(true);
        try {
            await triggerScan();
            setTimeout(load, 4000);
        } finally {
            setScanning(false);
        }
    };

    return (
        <div>
            <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div>
                    <h1>Value Bets</h1>
                    <p>Opportunities where model probability exceeds implied odds</p>
                </div>
                <button className="btn btn-primary" onClick={handleScan} disabled={scanning} id="scan-vb-btn">
                    {scanning ? '⏳ Scanning…' : '🎯 Run Scan'}
                </button>
            </div>

            {/* Filters */}
            <div className="card" style={{ marginBottom: '1.5rem', display: 'flex', gap: '1.5rem', alignItems: 'flex-end' }}>
                <div className="form-group" style={{ marginBottom: 0 }}>
                    <label className="form-label">Min EV (%)</label>
                    <input className="form-input" type="number" step="0.01" min="0" max="1"
                        value={minEv} onChange={e => setMinEv(parseFloat(e.target.value) || 0)}
                        style={{ width: 120 }} id="filter-min-ev"
                    />
                </div>
                <div className="form-group" style={{ marginBottom: 0 }}>
                    <label className="form-label">Status</label>
                    <select className="form-select" value={filterStatus} onChange={e => setFilterStatus(e.target.value)}
                        style={{ width: 140 }} id="filter-status">
                        <option value="">All</option>
                        <option value="pending">Pending</option>
                        <option value="placed">Placed</option>
                        <option value="won">Won</option>
                        <option value="lost">Lost</option>
                    </select>
                </div>
                <button className="btn btn-secondary" onClick={load}>🔍 Filter</button>
            </div>

            {loading ? (
                <div className="loading-wrapper"><div className="spinner" /><span>Loading value bets…</span></div>
            ) : bets.length === 0 ? (
                <div className="card"><div className="empty-state">
                    <div className="icon">🎯</div>
                    <p>No value bets found. Adjust filters or run a scan.</p>
                </div></div>
            ) : (
                <div className="table-container card" style={{ padding: 0 }}>
                    <table>
                        <thead>
                            <tr>
                                <th>Match ID</th>
                                <th>Bookmaker</th>
                                <th>Selection</th>
                                <th>Odds</th>
                                <th>Model Prob</th>
                                <th>Implied</th>
                                <th>Edge</th>
                                <th>EV</th>
                                <th>Kelly Stake</th>
                                <th>Status</th>
                                <th>Detected</th>
                            </tr>
                        </thead>
                        <tbody>
                            {bets.map((vb) => (
                                <tr key={vb.id}>
                                    <td>{vb.match_id ?? '—'}</td>
                                    <td>{vb.bookmaker}</td>
                                    <td style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{vb.selection}</td>
                                    <td style={{ color: 'var(--accent-blue)' }}>{vb.decimal_odds}</td>
                                    <td>{(vb.model_prob * 100).toFixed(1)}%</td>
                                    <td>{(vb.true_implied * 100).toFixed(1)}%</td>
                                    <td style={{ color: 'var(--accent-green)', fontWeight: 600 }}>
                                        +{(vb.edge * 100).toFixed(2)}%
                                    </td>
                                    <td>
                                        <span className={`badge ${vb.ev >= 0.05 ? 'badge-green' : 'badge-yellow'}`}>
                                            {(vb.ev * 100).toFixed(1)}%
                                        </span>
                                    </td>
                                    <td>{vb.suggested_stake?.toFixed(2) ?? '—'}</td>
                                    <td><span className={`badge ${STATUS_BADGE[vb.status] || 'badge-yellow'}`}>{vb.status}</span></td>
                                    <td>{new Date(vb.detected_at).toLocaleString()}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
}
