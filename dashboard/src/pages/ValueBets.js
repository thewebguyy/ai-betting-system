import React, { useEffect, useState } from 'react';
import { FixedSizeList } from 'react-window';
import { getValueBets, triggerScan } from '../api';
import { TableSkeleton } from '../components/Skeleton';

const STATUS_BADGE = {
    pending: 'badge-yellow',
    placed: 'badge-blue',
    won: 'badge-green',
    lost: 'badge-red',
    void: 'badge-purple',
};



const ValueBetRow = React.memo(({ index, data, style }) => {
    const vb = data[index];
    return (
        <div style={{ ...style, display: 'flex', borderBottom: '1px solid var(--border)', alignItems: 'center', padding: '0 1rem', background: index % 2 === 0 ? 'rgba(255,255,255,0.02)' : 'transparent' }}>
            <div style={{ flex: 1, fontSize: '0.8rem' }}>{vb.match_id ?? '—'}</div>
            <div style={{ flex: 1.5 }}>{vb.bookmaker}</div>
            <div style={{ flex: 2 }}>
                <button className={`prediction-btn ${vb.selection.toLowerCase().includes('home') || vb.selection === '1' ? 'home' : vb.selection.toLowerCase().includes('away') || vb.selection === '2' ? 'away' : 'draw'}`}>
                    {vb.selection}
                </button>
            </div>
            <div style={{ flex: 1 }} className="odds-value">{vb.decimal_odds}</div>
            <div style={{ flex: 1 }}>{(vb.model_prob * 100).toFixed(1)}%</div>
            <div style={{ flex: 1, color: 'var(--accent-green)', fontWeight: 600 }}>+{(vb.edge * 100).toFixed(2)}%</div>
            <div style={{ flex: 1 }}>
                <span className={`badge ${vb.ev >= 0.05 ? 'badge-green' : 'badge-yellow'}`}>
                    {(vb.ev * 100).toFixed(1)}%
                </span>
            </div>
            <div style={{ flex: 1.5 }}><span className={`badge ${STATUS_BADGE[vb.status] || 'badge-yellow'}`}>{vb.status}</span></div>
            <div style={{ flex: 2, fontSize: '0.7rem', color: 'var(--text-muted)' }}>{new Date(vb.detected_at).toLocaleString()}</div>
        </div>
    );
});




export default function ValueBetsPage() {
    const [bets, setBets] = useState([]);
    const [loading, setLoading] = useState(true);
    const [scanning, setScanning] = useState(false);
    const [minEv, setMinEv] = useState(0);
    const [filterStatus, setFilterStatus] = useState('');

    const [error, setError] = useState(null);

    const load = React.useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const data = await getValueBets({ min_ev: minEv, status: filterStatus || undefined, limit: 500 });
            setBets(Array.isArray(data) ? data : []);
        } catch (err) {
            if (err.name !== 'CanceledError') {
                setError('Cannot connect to Intelligence Engine. Please check your network or try again.');
            }
        } finally {
            setTimeout(() => setLoading(false), 200);
        }
    }, [minEv, filterStatus]);

    useEffect(() => { load(); }, [load]);

    const handleScan = React.useCallback(async () => {
        setScanning(true);
        try {
            await triggerScan();
            setTimeout(load, 4000);
        } finally {
            setScanning(false);
        }
    }, [load]);

    if (loading) return (
        <div className="fade-in">
            <div className="page-header">
                <h1>Value Bets</h1>
                <p>Opportunities where model probability exceeds implied odds</p>
            </div>
            <TableSkeleton rows={10} />
        </div>
    );

    return (
        <div className="fade-in" style={{ height: 'calc(100vh - 120px)', display: 'flex', flexDirection: 'column' }}>
            <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexShrink: 0 }}>
                <div>
                    <h1>Value Bets</h1>
                    <p>Opportunities where model probability exceeds implied odds</p>
                </div>
                <button className="btn btn-primary" onClick={handleScan} disabled={scanning} id="scan-vb-btn">
                    {scanning ? '⏳ Scanning…' : '🎯 Run Scan'}
                </button>
            </div>


            {/* Filters */}
            <div className="card" style={{ marginBottom: '1.5rem', display: 'flex', gap: '1.5rem', alignItems: 'flex-end', flexShrink: 0 }}>
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
            ) : error ? (
                <div className="card" style={{ textAlign: 'center', padding: '3rem' }}>
                    <div className="icon" style={{ fontSize: '2rem', marginBottom: '1rem' }}>📡</div>
                    <p style={{ color: 'var(--text-secondary)', marginBottom: '1.5rem' }}>{error}</p>
                    <button className="btn btn-secondary" onClick={load}>🔄 Retry Connection</button>
                </div>
            ) : bets.length === 0 ? (
                <div className="card"><div className="empty-state">
                    <div className="icon">🎯</div>
                    <p>No value bets found. Adjust filters or run a scan.</p>
                </div></div>
            ) : (
                <div className="card" style={{ padding: 0, flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
                    {/* Header */}
                    <div style={{ display: 'flex', background: 'var(--bg-elevated)', padding: '1rem', borderBottom: '2px solid var(--border)', fontWeight: 700, fontSize: '0.85rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                        <div style={{ flex: 1 }}>Match</div>
                        <div style={{ flex: 1.5 }}>Bookie</div>
                        <div style={{ flex: 2 }}>Selection</div>
                        <div style={{ flex: 1 }}>Odds</div>
                        <div style={{ flex: 1 }}>Model</div>
                        <div style={{ flex: 1 }}>Edge</div>
                        <div style={{ flex: 1 }}>EV</div>
                        <div style={{ flex: 1.5 }}>Status</div>
                        <div style={{ flex: 2 }}>Detected</div>
                    </div>
                    {/* Virtualized List */}
                    <div style={{ flex: 1 }}>
                        <FixedSizeList
                            height={500}
                            itemCount={bets.length}
                            itemSize={60}
                            width="100%"
                            itemData={bets}
                        >
                            {ValueBetRow}
                        </FixedSizeList>

                    </div>
                </div>
            )}
        </div>
    );
}


