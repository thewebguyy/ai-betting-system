import React from 'react';

export const CardSkeleton = () => (
    <div className="card skeleton" style={{ height: '160px', marginBottom: '1.5rem' }}>
        <div className="skeleton" style={{ width: '40%', height: '20px', marginBottom: '1rem', background: 'rgba(255,255,255,0.05)' }} />
        <div className="skeleton" style={{ width: '80%', height: '32px', background: 'rgba(255,255,255,0.05)' }} />
    </div>
);

export const TableSkeleton = ({ rows = 5 }) => (
    <div className="card" style={{ padding: 0 }}>
        <div style={{ padding: '1rem', borderBottom: '1px solid var(--border)', background: 'var(--bg-elevated)' }}>
            <div className="skeleton" style={{ width: '100%', height: '20px', opacity: 0.5 }} />
        </div>
        {[...Array(rows)].map((_, i) => (
            <div key={i} style={{ padding: '1rem', borderBottom: '1px solid var(--border)', display: 'flex', gap: '1rem' }}>
                <div className="skeleton" style={{ flex: 1, height: '16px', opacity: 0.3 }} />
                <div className="skeleton" style={{ flex: 2, height: '16px', opacity: 0.3 }} />
                <div className="skeleton" style={{ flex: 1, height: '16px', opacity: 0.3 }} />
            </div>
        ))}
    </div>
);

export const ChartSkeleton = () => (
    <div className="card" style={{ height: '300px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div className="skeleton" style={{ width: '80%', height: '80%', borderRadius: '50%', opacity: 0.2 }} />
    </div>
);
