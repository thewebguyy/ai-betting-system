import React, { useEffect, useState } from 'react';
import { getReports, generateReport } from '../api';

export default function ReportsPage() {
    const [reports, setReports] = useState([]);
    const [loading, setLoading] = useState(true);
    const [generating, setGenerating] = useState(false);
    const [error, setError] = useState(null);

    const load = async () => {
        setLoading(true);
        setError(null);
        try {
            const data = await getReports();
            setReports(Array.isArray(data) ? data : []);
        } catch (err) {
            setError('Cannot connect to Intelligence Engine. Please check your network or try again.');
        } finally {
            setLoading(false);
        }
    };


    useEffect(() => { load(); }, []);

    const handleGenerate = async (type) => {
        setGenerating(true);
        await generateReport(type);
        setTimeout(() => { load(); setGenerating(false); }, 3000);
    };

    const TYPE_ICON = { daily: '📅', match: '🏟', performance: '📈' };

    return (
        <div>
            <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div>
                    <h1>Reports</h1>
                    <p>AI-generated match intelligence and performance reports</p>
                </div>
                <div style={{ display: 'flex', gap: '0.75rem' }}>
                    {['daily', 'performance'].map(type => (
                        <button key={type} className="btn btn-secondary" id={`gen-${type}-report`}
                            onClick={() => handleGenerate(type)} disabled={generating}>
                            {generating ? '⏳' : TYPE_ICON[type]} {type.charAt(0).toUpperCase() + type.slice(1)} Report
                        </button>
                    ))}
                </div>
            </div>

            {loading ? (
                <div className="loading-wrapper"><div className="spinner" /><span>Loading reports…</span></div>
            ) : error ? (
                <div className="card" style={{ textAlign: 'center', padding: '3rem' }}>
                    <div className="icon" style={{ fontSize: '2rem', marginBottom: '1rem' }}>📡</div>
                    <p style={{ color: 'var(--text-secondary)', marginBottom: '1.5rem' }}>{error}</p>
                    <button className="btn btn-secondary" onClick={load}>🔄 Retry Connection</button>
                </div>
            ) : reports.length === 0 ? (
                <div className="card"><div className="empty-state">
                    <div className="icon">📄</div>
                    <p>No reports generated yet. Click a button above to create your first report.</p>
                </div></div>
            ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                    {reports.map(r => (
                        <div key={r.id} className="card" style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                            <div style={{ fontSize: '2rem' }}>{TYPE_ICON[r.report_type] || '📄'}</div>
                            <div style={{ flex: 1 }}>
                                <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{r.title}</div>
                                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
                                    {new Date(r.created_at).toLocaleString()}
                                </div>
                            </div>
                            <div style={{ display: 'flex', gap: '0.5rem' }}>
                                <span className={`badge ${{ daily: 'badge-blue', match: 'badge-green', performance: 'badge-purple' }[r.report_type] || 'badge-yellow'}`}>
                                    {r.report_type}
                                </span>
                                {r.file_path && (
                                    <a href={`/reports/${r.file_path.split('/').pop()}`}
                                        className="btn btn-secondary" style={{ padding: '0.25rem 0.75rem', fontSize: '0.75rem' }}
                                        target="_blank" rel="noopener noreferrer">
                                        📥 Download
                                    </a>
                                )}
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
