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
  const [authTab, setAuthTab] = useState('login'); // 'login' | 'signup'

  // Login state
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loginError, setLoginError] = useState('');
  const [loginLoading, setLoginLoading] = useState(false);
  const [loginSuccess, setLoginSuccess] = useState('');

  // Signup state
  const [signupFullName, setSignupFullName] = useState('');
  const [signupUsername, setSignupUsername] = useState('');
  const [signupEmail, setSignupEmail] = useState('');
  const [signupPassword, setSignupPassword] = useState('');
  const [signupConfirm, setSignupConfirm] = useState('');
  const [signupError, setSignupError] = useState('');
  const [signupLoading, setSignupLoading] = useState(false);

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
    setLoginSuccess('');
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

  const handleSignupSubmit = async (e) => {
    if (e) e.preventDefault();
    setSignupError('');
    if (!signupUsername.trim() || !signupEmail.trim() || !signupPassword) {
      setSignupError('Username, email, and password are required.');
      return;
    }
    if (signupPassword.length < 8) {
      setSignupError('Password must be at least 8 characters.');
      return;
    }
    if (signupPassword !== signupConfirm) {
      setSignupError('Passwords do not match.');
      return;
    }
    setSignupLoading(true);
    try {
      await authApi.register({
        username: signupUsername.trim(),
        email: signupEmail.trim(),
        full_name: signupFullName.trim() || undefined,
        password: signupPassword,
      });
      // Success — switch to login tab with username prefilled
      setSignupFullName('');
      setSignupUsername('');
      setSignupEmail('');
      setSignupPassword('');
      setSignupConfirm('');
      setAuthTab('login');
      setUsername(signupUsername.trim().toLowerCase());
      setPassword('');
      setLoginSuccess('Account created! Please sign in with your new credentials.');
    } catch (err) {
      setSignupError(err.response?.data?.detail || 'Registration failed. Please try again.');
    } finally {
      setSignupLoading(false);
    }
  };

  const handleQuickPersona = (userKey, passVal) => {
    setAuthTab('login');
    setUsername(userKey);
    setPassword(passVal);
    setLoginError('');
    setLoginSuccess('');
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
      setAuthTab('login');
      setLoginError('');
      setLoginSuccess('');
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

      {/* Auth Modal — Login / Sign Up */}
      {loginModalOpen && (
        <div className="login-modal-overlay">
          <div className="login-modal-card">
            <div className="login-modal-header">
              <div className="login-brand">
                <span className="brand-mark">F</span>
                <h3>FraudGraph {authTab === 'login' ? 'Sign In' : 'Create Account'}</h3>
              </div>
              <p>
                {authTab === 'login'
                  ? 'Sign in to access graph analytics, transaction monitoring, and case investigations.'
                  : 'Register a new investigator account. Your data is saved to the Neo4j database.'}
              </p>
            </div>

            {/* Tab switcher */}
            <div className="auth-tabs">
              <button
                type="button"
                className={`auth-tab-btn ${authTab === 'login' ? 'active' : ''}`}
                onClick={() => { setAuthTab('login'); setSignupError(''); setLoginError(''); }}
              >
                Sign In
              </button>
              <button
                type="button"
                className={`auth-tab-btn ${authTab === 'signup' ? 'active' : ''}`}
                onClick={() => { setAuthTab('signup'); setLoginError(''); setLoginSuccess(''); setSignupError(''); }}
              >
                Create Account
              </button>
            </div>

            {/* ── LOGIN TAB ─────────────────────────────────── */}
            {authTab === 'login' && (
              <>
                {loginError && <div className="login-error-banner">{loginError}</div>}
                {loginSuccess && <div className="login-success-banner">{loginSuccess}</div>}

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
                        <small>Full controls &amp; users</small>
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
                        <small>Case ops &amp; graph</small>
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
                        <small>Audit &amp; resolutions</small>
                      </div>
                    </button>
                  </div>
                </div>

                <div className="auth-switch-hint">
                  New user?{' '}
                  <button
                    type="button"
                    className="btn-auth-switch"
                    onClick={() => { setAuthTab('signup'); setLoginError(''); setLoginSuccess(''); }}
                  >
                    Create an account →
                  </button>
                </div>
              </>
            )}

            {/* ── SIGNUP TAB ────────────────────────────────── */}
            {authTab === 'signup' && (
              <>
                {signupError && <div className="login-error-banner">{signupError}</div>}

                <form onSubmit={handleSignupSubmit} className="login-form">
                  <div className="form-group">
                    <label htmlFor="signup-fullname">
                      Full Name <span className="field-optional">(optional)</span>
                    </label>
                    <input
                      id="signup-fullname"
                      type="text"
                      className="login-input"
                      placeholder="e.g. Jane Doe"
                      value={signupFullName}
                      onChange={(e) => setSignupFullName(e.target.value)}
                      autoComplete="name"
                    />
                  </div>

                  <div className="form-group">
                    <label htmlFor="signup-username">
                      Username <span className="field-required">*</span>
                    </label>
                    <input
                      id="signup-username"
                      type="text"
                      className="login-input"
                      placeholder="Minimum 3 characters"
                      value={signupUsername}
                      onChange={(e) => setSignupUsername(e.target.value)}
                      autoComplete="username"
                      required
                    />
                  </div>

                  <div className="form-group">
                    <label htmlFor="signup-email">
                      Email Address <span className="field-required">*</span>
                    </label>
                    <input
                      id="signup-email"
                      type="email"
                      className="login-input"
                      placeholder="you@example.com"
                      value={signupEmail}
                      onChange={(e) => setSignupEmail(e.target.value)}
                      autoComplete="email"
                      required
                    />
                  </div>

                  <div className="signup-password-row">
                    <div className="form-group">
                      <label htmlFor="signup-password">
                        Password <span className="field-required">*</span>
                      </label>
                      <input
                        id="signup-password"
                        type="password"
                        className="login-input"
                        placeholder="Min 8 characters"
                        value={signupPassword}
                        onChange={(e) => setSignupPassword(e.target.value)}
                        autoComplete="new-password"
                        required
                      />
                    </div>

                    <div className="form-group">
                      <label htmlFor="signup-confirm">
                        Confirm Password <span className="field-required">*</span>
                      </label>
                      <input
                        id="signup-confirm"
                        type="password"
                        className={`login-input ${signupConfirm && signupPassword !== signupConfirm ? 'input-error' : ''}`}
                        placeholder="Repeat password"
                        value={signupConfirm}
                        onChange={(e) => setSignupConfirm(e.target.value)}
                        autoComplete="new-password"
                        required
                      />
                    </div>
                  </div>

                  <div className="signup-role-note">
                    <span>🔒</span>
                    New accounts are created with the <strong>Fraud Analyst</strong> role.
                    Admins can promote accounts later.
                  </div>

                  <button type="submit" className="btn-login-submit btn-signup" disabled={signupLoading}>
                    {signupLoading ? 'Creating Account...' : 'Create Account & Save to Database'}
                  </button>
                </form>

                <div className="auth-switch-hint">
                  Already have an account?{' '}
                  <button
                    type="button"
                    className="btn-auth-switch"
                    onClick={() => { setAuthTab('login'); setSignupError(''); }}
                  >
                    Sign in →
                  </button>
                </div>
              </>
            )}

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
