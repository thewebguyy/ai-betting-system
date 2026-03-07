import React, { useState } from 'react';
import { calcEV } from '../api';

export default function EVCalculator() {
    const [form, setForm] = useState({
        decimal_odds: '',
        model_prob: '',
        stake: '100',
        bankroll: '1000',
        kelly_fraction: '0.25',
    });
    const [result, setResult] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');

    const handleCalc = async (e) => {
        e.preventDefault();
        setError('');
        setLoading(true);
        try {
            const data = await calcEV({
                decimal_odds: parseFloat(form.decimal_odds),
                model_prob: parseFloat(form.model_prob),
                stake: parseFloat(form.stake),
                bankroll: parseFloat(form.bankroll),
                kelly_fraction: parseFloat(form.kelly_fraction),
            });
            setResult(data);
        } catch (e) {
            setError('Calculation failed. Check your inputs.');
        } finally {
            setLoading(false);
        }
    };

    const field = (key, label, type, placeholder, min, max, step) => (
        <div className="form-group">
            <label className="form-label">{label}</label>
            <input
                className="form-input"
                id={`ev-${key}`}
                type={type || 'number'}
                placeholder={placeholder}
                min={min}
                max={max}
                step={step || '0.01'}
                value={form[key]}
                onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))}
                required
            />
        </div>
    );

    return (
        <div>
            <div className="page-header">
                <h1>EV Calculator</h1>
                <p>Calculate expected value and optimal Kelly stake for any bet</p>
            </div>

            <div className="grid-2">
                {/* Input form */}
                <div className="card">
                    <div className="card-header"><div className="card-title">📊 Inputs</div></div>
                    <form onSubmit={handleCalc}>
                        {field('decimal_odds', 'Decimal Odds', 'number', '2.10', '1.01', null, '0.01')}
                        {field('model_prob', 'Model Probability (0-1)', 'number', '0.55', '0', '1', '0.001')}
                        {field('stake', 'Stake Amount', 'number', '100', '0.01')}
                        {field('bankroll', 'Bankroll', 'number', '1000', '1')}
                        {field('kelly_fraction', 'Kelly Fraction (0-1)', 'number', '0.25', '0.01', '1', '0.05')}
                        {error && <div style={{ color: 'var(--accent-red)', fontSize: '0.8rem', marginBottom: '0.75rem' }}>{error}</div>}
                        <button className="btn btn-primary" type="submit" id="ev-calc-btn"
                            style={{ width: '100%', justifyContent: 'center' }} disabled={loading}>
                            {loading ? '⏳ Calculating…' : '🧮 Calculate EV'}
                        </button>
                    </form>

                    {/* Formula legend */}
                    <div style={{ marginTop: '1.5rem', padding: '1rem', background: 'var(--bg-elevated)', borderRadius: 8, fontSize: '0.75rem' }}>
                        <div style={{ fontWeight: 600, marginBottom: '0.5rem', color: 'var(--text-secondary)' }}>Formulas</div>
                        {[
                            'Implied Prob = 1 / Decimal Odds',
                            'Edge = Model Prob − Implied Prob',
                            'EV = (Model Prob × (Odds−1)) − (1−Model Prob)',
                            'Kelly = (b·p − q) / b',
                        ].map(f => (
                            <div key={f} style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-muted)', marginBottom: 4 }}>
                                {f}
                            </div>
                        ))}
                    </div>
                </div>

                {/* Results */}
                <div className="card">
                    <div className="card-header"><div className="card-title">📈 Results</div></div>
                    {!result ? (
                        <div className="empty-state">
                            <div className="icon">🧮</div>
                            <p>Enter values and calculate to see results.</p>
                        </div>
                    ) : (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                            {/* Value badge */}
                            <div style={{
                                text: 'center', padding: '1.25rem',
                                background: result.is_value ? 'rgba(0,212,170,0.08)' : 'rgba(239,68,68,0.08)',
                                border: `1px solid ${result.is_value ? 'rgba(0,212,170,0.2)' : 'rgba(239,68,68,0.2)'}`,
                                borderRadius: 12, textAlign: 'center',
                            }}>
                                <div style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>
                                    {result.is_value ? '✅' : '❌'}
                                </div>
                                <div style={{
                                    fontWeight: 700, fontSize: '1.125rem',
                                    color: result.is_value ? 'var(--accent-green)' : 'var(--accent-red)',
                                }}>
                                    {result.is_value ? 'VALUE BET' : 'NO VALUE'}
                                </div>
                                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
                                    {result.is_value ? 'Model probability exceeds implied probability' : 'No positive edge detected'}
                                </div>
                            </div>

                            {[
                                { label: 'Implied Probability', value: `${(result.implied_prob * 100).toFixed(2)}%` },
                                { label: 'Edge', value: `${(result.edge * 100).toFixed(3)}%`, color: result.edge > 0 ? 'positive' : 'negative' },
                                { label: 'Expected Value', value: `${(result.ev * 100).toFixed(2)}%`, color: result.ev > 0 ? 'positive' : 'negative' },
                                { label: 'Full Kelly', value: `${(result.kelly_full * 100).toFixed(2)}%` },
                                { label: 'Fractional Kelly', value: `${(result.kelly_fractional * 100).toFixed(2)}%` },
                                { label: 'Suggested Stake', value: result.suggested_stake.toFixed(2) },
                            ].map(({ label, value, color }) => (
                                <div key={label} style={{
                                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                                    padding: '0.75rem 1rem', background: 'var(--bg-elevated)',
                                    borderRadius: 8, border: '1px solid var(--border)',
                                }}>
                                    <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>{label}</span>
                                    <span style={{
                                        fontFamily: 'var(--font-mono)', fontWeight: 600,
                                        color: color === 'positive' ? 'var(--accent-green)' :
                                            color === 'negative' ? 'var(--accent-red)' : 'var(--text-primary)',
                                    }}>{value}</span>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
