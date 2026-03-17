import React, { useEffect, useState, useRef } from 'react';

const WS_URL = process.env.REACT_APP_WS_URL 
    || (window.location.hostname.includes('vercel.app')
        ? 'wss://ai-betting-system-production.up.railway.app/ws/alerts'
        : (window.location.protocol === 'https:' ? 'wss://' : 'ws://') 
          + (process.env.REACT_APP_API_URL?.replace(/^https?:\/\//, '') || 'localhost:8000') 
          + '/ws/alerts');




export function useWebSocket() {
    const [alerts, setAlerts] = useState([]);
    const [connected, setConnected] = useState(false);
    const wsRef = useRef(null);
    const pingRef = useRef(null);

    useEffect(() => {
        const connect = () => {
            try {
                const ws = new WebSocket(WS_URL);
                wsRef.current = ws;

                ws.onopen = () => {
                    setConnected(true);
                    // Heartbeat
                    pingRef.current = setInterval(() => {
                        if (ws.readyState === WebSocket.OPEN) ws.send('ping');
                    }, 30_000);
                };

                ws.onmessage = (evt) => {
                    if (evt.data === 'pong') return;
                    try {
                        const event = JSON.parse(evt.data);
                        setAlerts(prev => [event, ...prev].slice(0, 50));
                    } catch (_) { }
                };

                ws.onclose = () => {
                    setConnected(false);
                    clearInterval(pingRef.current);
                    // Reconnect after 5s
                    setTimeout(connect, 5000);
                };

                ws.onerror = () => ws.close();
            } catch (e) {
                setTimeout(connect, 5000);
            }
        };

        connect();
        return () => {
            wsRef.current?.close();
            clearInterval(pingRef.current);
        };
    }, []);

    const clearAlerts = () => setAlerts([]);
    return { alerts, connected, clearAlerts };
}
