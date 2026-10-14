import { useEffect, useState } from 'react';
import api, { authApi, setAuthToken, setOnUnauthorized } from './api/client';
import Dashboard from './pages/Dashboard';
import Clients from './pages/Clients';
import Transactions from './pages/Transactions';
import FraudAnalysis from './pages/FraudAnalysis';
import GraphView from './pages/GraphView';
import Cases from './pages/Cases';

const pages = [
  { id: 'dashboard', label: 'Dashboard', icon: '▦' },
  { id: 'cases', label: 'Case management', icon: '⚖' },
  { id: 'fraud', label: 'Fraud alerts', icon: '◈' },
  { id: 'clients', label: 'Client investigation', icon: '◎' },
  { id: 'transactions', label: 'Transactions', icon: '⇄' },
  { id: 'graph', label: 'Graph view', icon: '⌘' },
];

export default function App() {
  const [active, setActive] = useState('dashboard');
  const [apiState, setApiState] = useState('checking');
  const [currentUser, setCurrentUser] = useState(null);
  const [authChecking, setAuthChecking] = useState(true);
  const [loginModalOpen, setLoginModalOpen] = useState(false);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loginError, setLoginError] = useState('');
  const [loginLoading, setLoginLoading] = useState(false);

  // Hook for 401 Unauthorized handling
  useEffect(() => {
    setOnUnauthorized(() => {
      setCurrentUser(null);
      setLoginModalOpen(true);
      setLoginError('Your session has expired or requires authentication.');
    });
  }, []);

  // Check health and initial identity session on startup
  useEffect(() => {
    api.get('/health')
      .then(() => setApiState('connected'))
      .catch(() => setApiState('offline'));

    // Check if session cookie or stored token is valid
    authApi.me()
      .then((res) => {
        setCurrentUser(res.data);
        setLoginModalOpen(false);
      })
      .catch(() => {
        setCurrentUser(null);
        setLoginModalOpen(true);
      })
      .finally(() => {
        setAuthChecking(false);
      });
  }, []);

  const handleLoginSubmit = async (e) => {
    if (e) e.preventDefault();
    if (!username.trim() || !password) {
      setLoginError('Please enter both username and password.');
      return;
    }
    setLoginError('');
    setLoginLoading(true);
    try {
      const res = await authApi.login({ username: username.trim(), password });
      setAuthToken(res.data.access_token);
      setCurrentUser(res.data.user);
      setLoginModalOpen(false);
      setUsername('');
      setPassword('');
    } catch (err) {
      setLoginError(err.response?.data?.detail || 'Authentication failed. Please verify credentials.');
    } finally {
      setLoginLoading(false);
    }
  };

  const handleQuickPersona = (userKey, passVal) => {
    setUsername(userKey);
    setPassword(passVal);
    setLoginError('');
  };

  const handleLogout = async () => {
    try {
      await authApi.logout();
    } catch {
      // ignore
    } finally {
      setAuthToken(null);
      setCurrentUser(null);
      setLoginModalOpen(true);
      setLoginError('');
    }
  };

  const content = {
    dashboard: <Dashboard onNavigate={setActive} currentUser={currentUser} />,
    cases: <Cases currentUser={currentUser} />,
    fraud: <FraudAnalysis currentUser={currentUser} />,
    clients: <Clients currentUser={currentUser} />,
    transactions: <Transactions currentUser={currentUser} />,
    graph: <GraphView currentUser={currentUser} />,
  }[active];

  const roleBadgeClass = currentUser?.role === 'admin'
    ? 'badge-role-admin'
    : currentUser?.role === 'compliance_officer'
    ? 'badge-role-compliance'
    : 'badge-role-analyst';

  const roleLabel = currentUser?.role === 'admin'
    ? 'Admin'
    : currentUser?.role === 'compliance_officer'
    ? 'Compliance Officer'
    : 'Fraud Analyst';

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">F</span>
          <div>
            <strong>FraudGraph</strong>
            <small>Investigation Console</small>
          </div>
        </div>

        {/* Authenticated User Profile Summary Card */}
        {currentUser ? (
          <div className="user-profile-card">
            <div className="user-profile-avatar">
              {(currentUser.full_name || currentUser.username)[0].toUpperCase()}
            </div>
            <div className="user-profile-info">
              <span className="user-profile-name">{currentUser.full_name || currentUser.username}</span>
              <span className={`user-role-badge ${roleBadgeClass}`}>
                {roleLabel}
              </span>
            </div>
            <button className="btn-logout" title="Sign out" onClick={handleLogout}>
              ⏻
            </button>
          </div>
        ) : (
          <div className="user-profile-card unauth" onClick={() => setLoginModalOpen(true)}>
            <div className="user-profile-avatar">?</div>
            <div className="user-profile-info">
              <span className="user-profile-name">Guest (Not Signed In)</span>
              <span className="user-role-badge badge-role-unauth">Click to Sign In</span>
            </div>
          </div>
        )}

        <div className="nav-caption">WORKSPACE</div>
        <nav aria-label="Main navigation">
          {pages.map((page) => (
            <button
              key={page.id}
              className={`nav-item ${active === page.id ? 'active' : ''}`}
              onClick={() => setActive(page.id)}
            >
              <span className="nav-icon">{page.icon}</span>
              {page.label}
            </button>
          ))}
        </nav>

        <div className="sidebar-footer">
          <span className={`online-dot ${apiState}`} /> API {apiState}
        </div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <div className="topbar-left">
            <span>Financial Crime & Graph Risk Analytics</span>
            {currentUser && (
              <span className="topbar-user-tag">
                Logged in as <strong>{currentUser.username}</strong> ({roleLabel})
              </span>
            )}
          </div>
          <div className="topbar-right">
            {currentUser ? (
              <button className="btn-topbar-logout" onClick={handleLogout}>
                Sign Out
              </button>
            ) : (
              <button className="btn-topbar-signin" onClick={() => setLoginModalOpen(true)}>
                Sign In
              </button>
            )}
            <a href="http://localhost:8000/docs" target="_blank" rel="noreferrer">
              API docs ↗
            </a>
          </div>
        </header>

        {authChecking ? (
          <div className="auth-loading-screen">
            <div className="spinner" />
            <p>Authenticating session...</p>
          </div>
        ) : (
          content
        )}
      </main>

      {/* Login / Identity Modal */}
      {loginModalOpen && (
        <div className="login-modal-overlay">
          <div className="login-modal-card">
            <div className="login-modal-header">
              <div className="login-brand">
                <span className="brand-mark">F</span>
                <h3>FraudGraph Security Sign-In</h3>
              </div>
              <p>Sign in to access graph analytics, transaction monitoring, and case investigations.</p>
            </div>

            {loginError && <div className="login-error-banner">{loginError}</div>}

            <form onSubmit={handleLoginSubmit} className="login-form">
              <div className="form-group">
                <label htmlFor="username-input">Username or Email</label>
                <input
                  id="username-input"
                  type="text"
                  className="login-input"
                  placeholder="e.g. analyst_priya"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  autoComplete="username"
                  required
                />
              </div>

              <div className="form-group">
                <label htmlFor="password-input">Password</label>
                <input
                  id="password-input"
                  type="password"
                  className="login-input"
                  placeholder="••••••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                  required
                />
              </div>

              <button type="submit" className="btn-login-submit" disabled={loginLoading}>
                {loginLoading ? 'Signing In...' : 'Sign In to Investigation Console'}
              </button>
            </form>

            <div className="persona-quick-switcher">
              <div className="persona-switcher-title">DEMO ROLE PERSONAS (1-CLICK LOAD)</div>
              <div className="persona-buttons">
                <button
                  type="button"
                  className="persona-btn admin"
                  onClick={() => handleQuickPersona('admin', 'Admin@FraudGraph2026!')}
                >
                  <span className="persona-icon">👑</span>
                  <div>
                    <strong>Admin</strong>
                    <small>Full controls & users</small>
                  </div>
                </button>

                <button
                  type="button"
                  className="persona-btn analyst"
                  onClick={() => handleQuickPersona('analyst_priya', 'AnalystPass2026!')}
                >
                  <span className="persona-icon">🔍</span>
                  <div>
                    <strong>Fraud Analyst</strong>
                    <small>Case ops & graph</small>
                  </div>
                </button>

                <button
                  type="button"
                  className="persona-btn compliance"
                  onClick={() => handleQuickPersona('officer_chen', 'CompliancePass2026!')}
                >
                  <span className="persona-icon">⚖</span>
                  <div>
                    <strong>Compliance</strong>
                    <small>Audit & resolutions</small>
                  </div>
                </button>
              </div>
            </div>

            {currentUser && (
              <div className="login-modal-footer">
                <button
                  type="button"
                  className="btn-modal-dismiss"
                  onClick={() => setLoginModalOpen(false)}
                >
                  Continue as {currentUser.username}
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
