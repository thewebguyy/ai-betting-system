import axios from 'axios';

let BASE_URL = process.env.REACT_APP_API_URL || (window.location.hostname.includes('localhost') 
    ? 'http://localhost:8000'
    : 'https://ai-betting-system-production.up.railway.app');

// Force protocol if missing
if (BASE_URL && !BASE_URL.startsWith('http')) {
    BASE_URL = 'https://' + BASE_URL;
}

console.log('API Base URL:', BASE_URL);

const api = axios.create({
    baseURL: BASE_URL,
    timeout: 10000,
});

// Cache and deduplication state
const cache = new Map();
const pendingRequests = new Map();
const abortControllers = new Map();

/**
 * Invalidate specific cache keys or clear all
 * @param {string} keyPrefix 
 */
export const invalidateCache = (keyPrefix) => {
    if (!keyPrefix) {
        cache.clear();
        return;
    }
    for (const key of cache.keys()) {
        if (key.includes(keyPrefix)) {
            cache.delete(key);
        }
    }
};

/**
 * Enhanced GET helper with deduplication, caching, and cancellation
 */
const getWithCache = async (url, options = {}) => {
    const { params = {}, cacheSeconds = 0, cancelPrevious = false } = options;
    const cacheKey = JSON.stringify({ url, params });

    // 1. Cancel previous if requested
    if (cancelPrevious && abortControllers.has(url)) {
        abortControllers.get(url).abort();
    }

    // 2. Check valid cache
    if (cacheSeconds > 0 && cache.has(cacheKey)) {
        const { data, timestamp } = cache.get(cacheKey);
        if (Date.now() - timestamp < cacheSeconds * 1000) {
            return data;
        }
        cache.delete(cacheKey);
    }

    // 3. Check for pending request
    if (pendingRequests.has(cacheKey)) {
        return pendingRequests.get(cacheKey);
    }

    const controller = new AbortController();
    abortControllers.set(url, controller);

    console.time(`fetch:${url}`);
    const requestPromise = api.get(url, { params, signal: controller.signal }).then(res => {
        console.timeEnd(`fetch:${url}`);
        const data = res.data;
        if (cacheSeconds > 0) {
            cache.set(cacheKey, { data, timestamp: Date.now() });
        }
        pendingRequests.delete(cacheKey);
        return data;
    }).catch(err => {
        if (err.name !== 'CanceledError') {
            console.error(`Fetch error ${url}:`, err);
        }
        pendingRequests.delete(cacheKey);
        throw err;
    });

    pendingRequests.set(cacheKey, requestPromise);
    return requestPromise;
};



// ── Interceptors ─────────────────────────────────────────────────────────────
api.interceptors.response.use(
    (response) => {
        // Successful response - backend is up
        window.dispatchEvent(new CustomEvent('backend-status-change', { detail: { isDown: false } }));
        return response;
    },
    (error) => {
        // Check for timeout or network failure
        const isTimeout = error.code === 'ECONNABORTED' || error.message.includes('timeout');
        const isNetworkError = !error.response; // No response from server
        const isServiceUnavailable = error.response && error.response.status === 503;

        if (isTimeout || isNetworkError || isServiceUnavailable) {
            console.error('Backend unreachable:', error.message);
            window.dispatchEvent(new CustomEvent('backend-status-change', { detail: { isDown: true, error: error.message } }));
        }
        return Promise.reject(error);
    }
);

// ── Auth ───────────────────────────────────────────────────────────────────
export const login = async (username, password) => {
    const params = new URLSearchParams();
    params.append('username', username);
    params.append('password', password);
    const res = await axios.post(`${BASE_URL}/auth/token`, params, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        timeout: 10000
    });


    localStorage.setItem('access_token', res.data.access_token);
    return res.data;
};


// ── Dashboard ─────────────────────────────────────────────────────────────
export const getAnalytics = () => getWithCache('/analytics', { cacheSeconds: 30 });
export const getBankroll = (limit = 30) => getWithCache('/bankroll', { params: { limit }, cacheSeconds: 30 });
export const addBankrollSnapshot = (data) => api.post('/bankroll', data).then(r => {
    invalidateCache('/bankroll');
    invalidateCache('/analytics');
    return r.data;
});

// ── Value Bets ────────────────────────────────────────────────────────────
export const getValueBets = (params = {}) => getWithCache('/value-bets', { params, cacheSeconds: 5, cancelPrevious: true });
export const triggerScan = () => api.post('/value-bets/scan').then(r => {
    invalidateCache('/value-bets');
    return r.data;
});

// ── EV Calculator ─────────────────────────────────────────────────────────
export const calcEV = (data) => api.post('/analytics/ev-calc', data).then(r => r.data);

// ── Bets ──────────────────────────────────────────────────────────────────
export const getBets = (params = {}) => getWithCache('/bets', { params, cacheSeconds: 10 });
export const placeBet = (data) => api.post('/bets', data).then(r => {
    invalidateCache('/bets');
    invalidateCache('/analytics');
    invalidateCache('/value-bets');
    return r.data;
});
export const settleBet = (id, data) => api.patch(`/bets/${id}/settle`, data).then(r => {
    invalidateCache('/bets');
    invalidateCache('/analytics');
    return r.data;
});

// ── Odds ──────────────────────────────────────────────────────────────────
export const getOdds = (params = {}) => getWithCache('/odds', { params, cacheSeconds: 5 });
export const fetchLiveOdds = () => api.post('/odds/fetch-live').then(r => {
    invalidateCache('/odds');
    return r.data;
});
export const getLineMovement = (matchId, bookmaker) =>
    getWithCache(`/analytics/line-movement`, { params: { match_id: matchId, bookmaker }, cacheSeconds: 60 });

// ── Matches ───────────────────────────────────────────────────────────────
export const getMatches = (params = {}) => getWithCache('/matches', { params, cacheSeconds: 30 });
export const getTodayPredictions = () => getWithCache('/api/today_predictions', { cacheSeconds: 10, cancelPrevious: true });

// ── Reports ───────────────────────────────────────────────────────────────
export const getReports = () => getWithCache('/reports', { cacheSeconds: 30 });
export const generateReport = (type, matchId) =>
    api.post('/reports/generate', null, { params: { report_type: type, match_id: matchId } }).then(r => {
        invalidateCache('/reports');
        return r.data;
    });



export default api;

