import axios from 'axios';

const BASE_URL = process.env.REACT_APP_API_URL || (window.location.hostname.includes('vercel.app') 
    ? ''  // Use relative path for Vercel/Railway proxy
    : 'http://localhost:8000');


const api = axios.create({
    baseURL: BASE_URL,
    timeout: 15000,
});

// Attach JWT token to every request
api.interceptors.request.use((config) => {
    const token = localStorage.getItem('access_token');
    if (token) {
        config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
});

// Handle auth errors globally
api.interceptors.response.use(
    (res) => res,
    (err) => {
        if (err.response?.status === 401) {
            localStorage.removeItem('access_token');
            window.location.href = '/login';
        }
        return Promise.reject(err);
    }
);

// ── Auth ───────────────────────────────────────────────────────────────────
export const login = async (username, password) => {
    const form = new FormData();
    form.append('username', username);
    form.append('password', password);
    const res = await api.post('/auth/token', form);
    localStorage.setItem('access_token', res.data.access_token);
    return res.data;
};

// ── Dashboard ─────────────────────────────────────────────────────────────
export const getAnalytics = () => api.get('/analytics').then(r => r.data);
export const getBankroll = (limit = 30) => api.get(`/bankroll?limit=${limit}`).then(r => r.data);
export const addBankrollSnapshot = (data) => api.post('/bankroll', data).then(r => r.data);

// ── Value Bets ────────────────────────────────────────────────────────────
export const getValueBets = (params = {}) =>
    api.get('/value-bets', { params }).then(r => r.data);

export const triggerScan = () => api.post('/value-bets/scan').then(r => r.data);

// ── EV Calculator ─────────────────────────────────────────────────────────
export const calcEV = (data) => api.post('/analytics/ev-calc', data).then(r => r.data);

// ── Bets ──────────────────────────────────────────────────────────────────
export const getBets = (params = {}) => api.get('/bets', { params }).then(r => r.data);
export const placeBet = (data) => api.post('/bets', data).then(r => r.data);
export const settleBet = (id, data) => api.patch(`/bets/${id}/settle`, data).then(r => r.data);

// ── Odds ──────────────────────────────────────────────────────────────────
export const getOdds = (params = {}) => api.get('/odds', { params }).then(r => r.data);
export const fetchLiveOdds = () => api.post('/odds/fetch-live').then(r => r.data);
export const getLineMovement = (matchId, bookmaker) =>
    api.get(`/analytics/line-movement`, { params: { match_id: matchId, bookmaker } }).then(r => r.data);

// ── Matches ───────────────────────────────────────────────────────────────
export const getMatches = (params = {}) => api.get('/matches', { params }).then(r => r.data);

// ── Reports ───────────────────────────────────────────────────────────────
export const getReports = () => api.get('/reports').then(r => r.data);
export const generateReport = (type, matchId) =>
    api.post('/reports/generate', null, { params: { report_type: type, match_id: matchId } }).then(r => r.data);

export default api;
