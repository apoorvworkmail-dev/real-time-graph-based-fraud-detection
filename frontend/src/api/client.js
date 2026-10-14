import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE,
  timeout: 15000,
  withCredentials: true, // Enables automatic HttpOnly cookie transmission across CORS
});

// In-memory token storage with sessionStorage fallback
let authToken = null;
try {
  authToken = sessionStorage.getItem('fg_access_token') || null;
} catch {
  // SessionStorage might be unavailable in restricted environments
}

let onUnauthorizedHandler = null;

export const setAuthToken = (token) => {
  authToken = token;
  try {
    if (token) {
      sessionStorage.setItem('fg_access_token', token);
    } else {
      sessionStorage.removeItem('fg_access_token');
    }
  } catch {
    // ignore storage errors
  }
};

export const getAuthToken = () => authToken;

export const setOnUnauthorized = (handler) => {
  onUnauthorizedHandler = handler;
};

// Request interceptor: attach Authorization header if token is present
api.interceptors.request.use(
  (config) => {
    if (authToken && !config.headers.Authorization) {
      config.headers.Authorization = `Bearer ${authToken}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor: intercept 401 and 403 responses
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response) {
      if (error.response.status === 401) {
        // Clear expired credentials
        setAuthToken(null);
        if (onUnauthorizedHandler) {
          onUnauthorizedHandler();
        }
      }
    }
    return Promise.reject(error);
  }
);

// ── Auth & Identity APIs ───────────────────────────────────────
export const authApi = {
  login: (credentials) => api.post('/api/v1/auth/login', credentials),
  refresh: (data = {}) => api.post('/api/v1/auth/refresh', data),
  logout: () => api.post('/api/v1/auth/logout'),
  me: () => api.get('/api/v1/auth/me'),
  wsTicket: () => api.post('/api/v1/auth/ws-ticket'),
};

// ── User Administration APIs ──────────────────────────────────
export const usersApi = {
  list: (params = {}) => api.get('/api/v1/users', { params }),
  get: (id) => api.get(`/api/v1/users/${encodeURIComponent(id)}`),
  create: (data) => api.post('/api/v1/users', data),
  update: (id, data) => api.patch(`/api/v1/users/${encodeURIComponent(id)}`, data),
  delete: (id) => api.delete(`/api/v1/users/${encodeURIComponent(id)}`),
};

// ── Existing Domain APIs ───────────────────────────────────────
export const clientsApi = {
  list: (params = {}) => api.get('/api/v1/clients/', { params }),
  get: (id) => api.get(`/api/v1/clients/${encodeURIComponent(id)}`),
  transactions: (id) => api.get(`/api/v1/clients/${encodeURIComponent(id)}/transactions`),
  neighbors: (id) => api.get(`/api/v1/graph/neighbors/${encodeURIComponent(id)}`, { params: { hops: 2 } }),
};

export const transactionsApi = {
  list: (params = {}) => api.get('/api/v1/transactions/', { params }),
};

export const devicesApi = { list: () => api.get('/api/v1/devices/') };
export const locationsApi = { list: () => api.get('/api/v1/locations/') };

export const fraudApi = {
  alerts: (limit = 100) => api.get('/api/v1/fraud/alerts', { params: { limit } }),
  sharedDevices: () => api.get('/api/v1/fraud/shared-devices'),
  cycles: () => api.get('/api/v1/fraud/cycles'),
  multiHop: () => api.get('/api/v1/fraud/multi-hop'),
};

export const riskApi = {
  client: (id) => api.get(`/api/v1/risk/client/${encodeURIComponent(id)}`),
  highRisk: (params = {}) => api.get('/api/v1/risk/high-risk', { params }),
};

export const graphApi = {
  subgraph: (limit = 20) => api.get('/api/v1/graph/subgraph', { params: { limit_clients: limit } }),
};

export const mlApi = {
  info: () => api.get('/api/v1/ml/info'),
  predictClient: (id) => api.get(`/api/v1/ml/predict/client/${encodeURIComponent(id)}`),
  communities: () => api.get('/api/v1/ml/communities'),
};

export const casesApi = {
  list: (params = {}) => api.get('/api/v1/cases', { params }),
  get: (id) => api.get(`/api/v1/cases/${encodeURIComponent(id)}`),
  create: (data) => api.post('/api/v1/cases', data),
  assign: (id, assigned_analyst, actor = 'analyst') =>
    api.patch(`/api/v1/cases/${encodeURIComponent(id)}/assign`, { assigned_analyst, actor }),
  updatePriority: (id, priority, actor = 'analyst') =>
    api.patch(`/api/v1/cases/${encodeURIComponent(id)}/priority`, { priority, actor }),
  transition: (id, data) =>
    api.post(`/api/v1/cases/${encodeURIComponent(id)}/transition`, data),
  addNote: (id, note, author = 'analyst') =>
    api.post(`/api/v1/cases/${encodeURIComponent(id)}/notes`, { note, author }),
  history: (id) => api.get(`/api/v1/cases/${encodeURIComponent(id)}/history`),
};

export const streamApi = {
  status: () => api.get('/api/v1/stream/status'),
  start: () => api.post('/api/v1/stream/start'),
  stop: () => api.post('/api/v1/stream/stop'),
  config: (params) => api.post('/api/v1/stream/config', params),
  step: (scenario) => api.post('/api/v1/stream/step', null, { params: scenario ? { scenario } : {} }),
  submit: (event) => api.post('/api/v1/stream/transactions', event),
};

export const getWsUrl = (path = '/ws/alerts', ticket = null) => {
  const wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  let base;
  if (import.meta.env.VITE_API_BASE_URL) {
    const url = new URL(import.meta.env.VITE_API_BASE_URL);
    base = `${url.protocol === 'https:' ? 'wss:' : 'ws:'}//${url.host}${path}`;
  } else if (window.location.port === '5173') {
    base = `${wsProto}//${window.location.hostname}:8000${path}`;
  } else {
    base = `${wsProto}//${window.location.host}${path}`;
  }

  if (ticket) {
    const sep = base.includes('?') ? '&' : '?';
    return `${base}${sep}ticket=${encodeURIComponent(ticket)}`;
  }
  return base;
};

export default api;
