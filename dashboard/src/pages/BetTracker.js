import React, { useEffect, useState } from 'react';
import { getBets, placeBet, settleBet } from '../api';
import toast from 'react-hot-toast';

const RESULT_BADGE = {
    won: 'badge-green', lost: 'badge-red',
    void: 'badge-purple', pending: 'badge-yellow', push: 'badge-blue',
};


export default function BetTracker() {
    const [bets, setBets] = useState([]);
    const [loading, setLoading] = useState(true);
    const [form, setForm] = useState({
        bookmaker: '', market: '1X2', selection: '',
        decimal_odds: '', stake: '', notes: '',
    });
    const [settling, setSettling] = useState(null);
    const [settleData, setSettleData] = useState({ result: 'won', actual_payout: '' });

    const load = async () => {
        setLoading(true);
        try {
            const data = await getBets({ limit: 100 });
            setBets(Array.isArray(data) ? data : []);
        } catch (err) {
            toast.error('Failed to load bets');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => { load(); }, []);

    const handlePlace = async (e) => {
        e.preventDefault();
        const tid = toast.loading('Placing bet...');
        try {
            await placeBet({
                ...form,
                decimal_odds: parseFloat(form.decimal_odds),
                stake: parseFloat(form.stake),
            });
            setForm({ bookmaker: '', market: '1X2', selection: '', decimal_odds: '', stake: '', notes: '' });
            toast.success('Bet placed!', { id: tid });
            load();
        } catch (err) {
            toast.error('Failed to place bet', { id: tid });
        }
    };

    const handleSettle = async (id) => {
        const tid = toast.loading('Settling bet...');
        try {
            await settleBet(id, {
                result: settleData.result,
                actual_payout: parseFloat(settleData.actual_payout) || 0,
            });
            setSettling(null);
            toast.success('Bet settled', { id: tid });
            load();
        } catch (err) {
            toast.error('Settlement failed', { id: tid });
        }
    };


    return (
        <div>
            <div className="page-header">
                <h1>Bet Tracker</h1>
                <p>Log and manage all your bets with profit tracking</p>
            </div>

            <div className="grid-2" style={{ marginBottom: '2rem' }}>
                {/* Place bet form */}
                <div className="card">
                    <div className="card-header"><div className="card-title">➕ Place New Bet</div></div>
                    <form onSubmit={handlePlace}>
                        {[
                            { key: 'bookmaker', label: 'Bookmaker', placeholder: 'SportyBet', id: 'bet-bookmaker' },
                            { key: 'selection', label: 'Selection', placeholder: 'Home / Draw / Away', id: 'bet-selection' },
                        ].map(({ key, label, placeholder, id }) => (
                            <div className="form-group" key={key}>
                                <label className="form-label">{label}</label>
                                <input className="form-input" id={id} placeholder={placeholder}
                                    value={form[key]} onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))} required />
                            </div>
                        ))}

                        <div className="form-group">
                            <label className="form-label">Market</label>
                            <select className="form-select" id="bet-market"
                                value={form.market} onChange={e => setForm(f => ({ ...f, market: e.target.value }))}>
                                {['1X2', 'BTTS', 'O/U', 'DNB', 'AH'].map(m => <option key={m}>{m}</option>)}
                            </select>
                        </div>

                        <div className="grid-2" style={{ gap: '1rem' }}>
                            <div className="form-group">
                                <label className="form-label">Decimal Odds</label>
                                <input className="form-input" type="number" step="0.01" min="1.01" id="bet-odds"
                                    placeholder="2.10" value={form.decimal_odds}
                                    onChange={e => setForm(f => ({ ...f, decimal_odds: e.target.value }))} required />
                            </div>
                            <div className="form-group">
                                <label className="form-label">Stake</label>
                                <input className="form-input" type="number" step="0.01" min="0.01" id="bet-stake"
                                    placeholder="50.00" value={form.stake}
                                    onChange={e => setForm(f => ({ ...f, stake: e.target.value }))} required />
                            </div>
                        </div>

                        <div className="form-group">
                            <label className="form-label">Notes (optional)</label>
                            <input className="form-input" id="bet-notes" placeholder="Value bet from scan…"
                                value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} />
                        </div>

                        {/* Potential payout preview */}
                        {form.decimal_odds && form.stake && (
                            <div style={{
                                background: 'rgba(0,212,170,0.06)', border: '1px solid rgba(0,212,170,0.15)',
                                borderRadius: 8, padding: '0.625rem 1rem', marginBottom: '1rem', fontSize: '0.8rem',
                            }}>
                                Potential Payout: <strong style={{ color: 'var(--accent-green)' }}>
                                    {(parseFloat(form.decimal_odds) * parseFloat(form.stake)).toFixed(2)}
                                </strong>
                            </div>
                        )}

                        <button className="btn btn-primary" type="submit" id="place-bet-btn"
                            style={{ width: '100%', justifyContent: 'center' }}>
                            🎰 Place Bet
                        </button>
                    </form>
                </div>

                {/* Settle panel */}
                {settling && (
                    <div className="card">
                        <div className="card-header">
                            <div className="card-title">✅ Settle Bet #{settling}</div>
                            <button onClick={() => setSettling(null)} style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}>✕</button>
                        </div>
                        <div className="form-group">
                            <label className="form-label">Result</label>
                            <select className="form-select" id="settle-result"
                                value={settleData.result} onChange={e => setSettleData(s => ({ ...s, result: e.target.value }))}>
                                {['won', 'lost', 'void', 'push'].map(r => <option key={r}>{r}</option>)}
                            </select>
                        </div>
                        <div className="form-group">
                            <label className="form-label">Actual Payout</label>
                            <input className="form-input" type="number" step="0.01" min="0" id="settle-payout"
                                placeholder="0.00"
                                value={settleData.actual_payout}
                                onChange={e => setSettleData(s => ({ ...s, actual_payout: e.target.value }))} />
                        </div>
                        <button className="btn btn-primary" onClick={() => handleSettle(settling)} id="settle-confirm-btn"
                            style={{ width: '100%', justifyContent: 'center' }}>
                            Confirm Settlement
                        </button>
                    </div>
                )}
            </div>

            {/* Bets table */}
            {loading ? (
                <div className="loading-wrapper"><div className="spinner" /></div>
            ) : (
                <div className="table-container card" style={{ padding: 0 }}>
                    <table>
                        <thead>
                            <tr>
                                <th>#</th><th>Bookmaker</th><th>Selection</th>
                                <th>Odds</th><th>Stake</th><th>Payout</th>
                                <th>Result</th><th>Placed</th><th>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {bets.map(b => (
                                <tr key={b.id}>
                                    <td>{b.id}</td>
                                    <td>{b.bookmaker}</td>
                                    <td style={{ color: 'var(--text-primary)', fontWeight: 500 }}>{b.selection}</td>
                                    <td>{b.decimal_odds}</td>
                                    <td>{b.stake.toFixed(2)}</td>
                                    <td>{b.actual_payout > 0 ? b.actual_payout.toFixed(2) : '—'}</td>
                                    <td><span className={`badge ${RESULT_BADGE[b.result] || 'badge-yellow'}`}>{b.result}</span></td>
                                    <td>{new Date(b.placed_at).toLocaleDateString()}</td>
                                    <td>
                                        {b.result === 'pending' && (
                                            <button className="btn btn-secondary" style={{ padding: '0.25rem 0.625rem', fontSize: '0.75rem' }}
                                                onClick={() => { setSettling(b.id); setSettleData({ result: 'won', actual_payout: b.potential_payout }); }}
                                                id={`settle-btn-${b.id}`}>
                                                Settle
                                            </button>
                                        )}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
}
