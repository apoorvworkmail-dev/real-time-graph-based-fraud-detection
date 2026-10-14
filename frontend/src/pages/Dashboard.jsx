import { useEffect, useState, useRef } from 'react';
import { clientsApi, devicesApi, locationsApi, transactionsApi, fraudApi, riskApi, streamApi, casesApi, getWsUrl } from '../api/client';

const countOf = (response) => Array.isArray(response.data) ? response.data.length : (response.data?.value?.length ?? 0);
const riskById = (scores) => Object.fromEntries(scores.map((item) => [item.entityId, item]));

export default function Dashboard({ onNavigate, currentUser }) {
  const isAdmin = currentUser?.role === 'admin';
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [simStatus, setSimStatus] = useState({ isRunning: false, totalGenerated: 0, totalAlerts: 0, activeScenario: 'random' });
  const [selectedScenario, setSelectedScenario] = useState('random');
  const [selectedInterval, setSelectedInterval] = useState('2.5');
  const [latestActivity, setLatestActivity] = useState(null);
  const [wsState, setWsState] = useState('connecting'); // 'connecting' | 'connected' | 'reconnecting' | 'disconnected'
  const wsRef = useRef(null);


  // Initial fetch for baseline metrics
  useEffect(() => {
    Promise.all([
      clientsApi.list({ limit: 500 }),
      transactionsApi.list({ limit: 500 }),
      devicesApi.list(),
      locationsApi.list(),
      fraudApi.alerts(100),
      riskApi.highRisk({ limit: 500 }),
      streamApi.status(),
    ]).then(([clients, transactions, devices, locations, alerts, scores, sim]) => {
      setData({
        clients: countOf(clients),
        transactions: countOf(transactions),
        devices: countOf(devices),
        locations: countOf(locations),
        alerts: alerts.data || [],
        scores: scores.data || [],
      });
      setSimStatus(sim.data);
      if (sim.data.activeScenario) setSelectedScenario(sim.data.activeScenario);
      if (sim.data.intervalSeconds) setSelectedInterval(String(sim.data.intervalSeconds));
    }).catch((e) => setError(e.response?.data?.detail || 'Could not reach FastAPI. Verify that the backend is running.'));
  }, []);

  // WebSocket with bounded exponential backoff & ping heartbeat
  useEffect(() => {
    let socket = null;
    let reconnectTimer = null;
    let heartbeatTimer = null;
    let backoffDelay = 1000;
    let isUnmounted = false;

    const connectWs = () => {
      if (isUnmounted) return;
      try {
        setWsState((prev) => (prev === 'connected' ? 'reconnecting' : 'connecting'));
        const url = getWsUrl('/ws/alerts');
        socket = new WebSocket(url);
        wsRef.current = socket;

        socket.onopen = () => {
          if (isUnmounted) return;
          setWsState('connected');
          backoffDelay = 1000; // Reset backoff on successful handshake
          // Heartbeat keep-alive every 20 seconds
          heartbeatTimer = setInterval(() => {
            if (socket && socket.readyState === WebSocket.OPEN) {
              socket.send(JSON.stringify({ type: 'PING' }));
            }
          }, 20000);
        };

        socket.onmessage = (msgEvent) => {
          if (isUnmounted) return;
          try {
            const payload = JSON.parse(msgEvent.data);

            if (payload.type === 'TRANSACTION_EVENT') {
              const tx = payload.data;
              setLatestActivity({
                isFraud: tx.isFraud,
                label: tx.isFraud ? 'FRAUD SIGNAL' : 'TX INGESTED',
                text: `${tx.senderId} → ${tx.receiverId} (₹${Number(tx.amount).toLocaleString()}) [${tx.scenario}]`,
                timestamp: new Date().toLocaleTimeString(),
              });
              setData((prev) => prev ? { ...prev, transactions: prev.transactions + 1 } : prev);
            } else if (payload.type === 'FRAUD_ALERT') {
              const alert = payload.alert;
              setLatestActivity({
                isFraud: true,
                label: '🚨 QUALIFIED FRAUD ALERT',
                text: `${alert.entity_id || alert.entityId} — Risk ${alert.risk_score || alert.riskScore} (${alert.risk_level || alert.riskLevel}): ${alert.risk_reason || alert.riskReason}`,
                timestamp: new Date().toLocaleTimeString(),
              });
              setData((prev) => {
                if (!prev) return prev;
                const alertId = alert.alert_id || alert.alertId || alert.entity_id || alert.entityId;
                // Idempotency: prevent duplicate alert insertion in feed
                const exists = prev.alerts.some((a) => (a.alert_id || a.alertId || a.entity_id || a.entityId) === alertId);
                if (exists) return prev;

                const normalizedAlert = {
                  entityId: alert.entity_id || alert.entityId,
                  entityType: alert.entity_type || alert.entityType || 'Transaction',
                  riskScore: alert.risk_score || alert.riskScore,
                  riskLevel: alert.risk_level || alert.riskLevel,
                  riskReason: alert.risk_reason || alert.riskReason,
                  connectedEntities: alert.connected_entities || alert.connectedEntities || [],
                  timestamp: alert.timestamp,
                };
                // Bounded alert history: keep top 25
                const updated = [normalizedAlert, ...prev.alerts].slice(0, 25);
                return { ...prev, alerts: updated };
              });
              setSimStatus((prev) => ({ ...prev, totalAlerts: prev.totalAlerts + 1 }));
            }
          } catch {
            // ignore non-json frames
          }
        };

        socket.onclose = () => {
          if (isUnmounted) return;
          clearInterval(heartbeatTimer);
          setWsState('disconnected');
          reconnectTimer = setTimeout(connectWs, backoffDelay);
          backoffDelay = Math.min(Math.round(backoffDelay * 1.5), 15000); // Bounded exponential backoff max 15s
        };

        socket.onerror = () => {
          if (isUnmounted) return;
          setWsState('disconnected');
        };
      } catch {
        if (!isUnmounted) setWsState('disconnected');
      }
    };

    connectWs();

    return () => {
      isUnmounted = true;
      clearInterval(heartbeatTimer);
      clearTimeout(reconnectTimer);
      if (wsRef.current) wsRef.current.close();
    };
  }, []);

  const handleToggleStream = async () => {
    try {
      if (simStatus.isRunning) {
        const res = await streamApi.stop();
        setSimStatus(res.data);
      } else {
        await streamApi.config({
          interval_seconds: parseFloat(selectedInterval),
          active_scenario: selectedScenario,
        });
        const res = await streamApi.start();
        setSimStatus(res.data);
      }
    } catch (e) {
      setError(e.response?.data?.detail || 'Failed to toggle stream simulator');
    }
  };

  const handleStepStream = async () => {
    try {
      const res = await streamApi.step(selectedScenario);
      if (res.data?.status) setSimStatus(res.data.status);
    } catch (e) {
      setError(e.response?.data?.detail || 'Failed to execute stream step');
    }
  };

  const handleScenarioChange = async (e) => {
    const val = e.target.value;
    setSelectedScenario(val);
    if (simStatus.isRunning) {
      const res = await streamApi.config({ active_scenario: val });
      setSimStatus(res.data);
    }
  };

  const handleIntervalChange = async (e) => {
    const val = e.target.value;
    setSelectedInterval(val);
    if (simStatus.isRunning) {
      const res = await streamApi.config({ interval_seconds: parseFloat(val) });
      setSimStatus(res.data);
    }
  };

  if (error) return <Page title="Dashboard" subtitle="Live overview of your Neo4j fraud graph"><div className="notice error-notice">{error}</div></Page>;
  if (!data) return <Page title="Dashboard" subtitle="Live overview of your Neo4j fraud graph"><div className="loading">Loading live graph data…</div></Page>;

  const scores = riskById(data.scores);
  const highRiskClients = data.scores.filter((item) => item.entityId.startsWith('CLT')).length;
  const metrics = [
    ['Total clients', data.clients, 'People and accounts', 'blue'],
    ['Transactions', data.transactions, 'Graph activity', 'violet'],
    ['Devices', data.devices, 'Known endpoints', 'amber'],
    ['Locations', data.locations, 'Observed origins', 'teal'],
    ['Fraud alerts', data.alerts.length, 'Graph-derived signals', 'red'],
    ['High-risk clients', highRiskClients, 'Score 50 and above', 'orange'],
  ];

  const wsBadgeClass = wsState === 'connected' ? 'connected' : (wsState === 'connecting' || wsState === 'reconnecting' ? 'connecting' : 'disconnected');

  return (
    <Page title="Dashboard" subtitle="Real-time transaction streaming & Neo4j graph fraud monitoring">
      {/* Real-time Simulator Control Bar */}
      <div className="simulator-bar">
        <div className="simulator-status-group">
          <span className={`live-badge ${simStatus.isRunning ? 'streaming' : 'idle'}`}>
            <span className="pulse-dot" />
            {simStatus.isRunning ? `Streaming (${simStatus.intervalSeconds || selectedInterval}s)` : 'Stream Idle'}
          </span>
          <span className={`count-pill ${wsBadgeClass}`}>
            WS: {wsState.toUpperCase()}
          </span>
          {simStatus.totalGenerated > 0 && <span className="count-pill">Generated: {simStatus.totalGenerated}</span>}
          {simStatus.totalPersisted > 0 && <span className="count-pill">Committed: {simStatus.totalPersisted}</span>}
          {!isAdmin && (
            <span className="sim-role-pill" title="Administrator role required to start/stop or modify stream generator">
              🔒 Read-Only (Admin Stream Controls)
            </span>
          )}
        </div>
        <div className="simulator-actions">
          <label style={{ fontSize: 11, fontWeight: 600, color: '#64748b' }}>Scenario:</label>
          <select className="sim-select" value={selectedScenario} onChange={handleScenarioChange} disabled={!isAdmin}>
            <option value="random">Random Distribution</option>
            <option value="normal">Normal Transfers</option>
            <option value="velocity">Velocity Burst Fraud</option>
            <option value="ring">Device Sharing Ring</option>
            <option value="cycle">Money Laundering Cycle</option>
            <option value="geo_anomaly">Geo-Location Anomaly</option>
            <option value="multi_hop">Multi-Hop Traversal</option>
          </select>
          <select className="sim-select" value={selectedInterval} onChange={handleIntervalChange} disabled={!isAdmin}>
            <option value="1.0">1.0s Rapid</option>
            <option value="2.5">2.5s Standard</option>
            <option value="5.0">5.0s Paced</option>
          </select>
          <button
            className={`btn-stream ${simStatus.isRunning ? 'stop' : 'start'}`}
            onClick={handleToggleStream}
            disabled={!isAdmin}
            title={!isAdmin ? "Requires Administrator privileges" : ""}
          >
            {simStatus.isRunning ? '⏹ Stop Stream' : '▶ Start Stream'}
          </button>
          <button
            className="btn-stream btn-step"
            onClick={handleStepStream}
            disabled={!isAdmin}
            title={!isAdmin ? "Requires Administrator privileges" : ""}
          >
            ⚡ Step (1 Txn)
          </button>
        </div>
      </div>


      {/* Live Transaction / Alert Activity Ticker */}
      {latestActivity && (
        <div className={`stream-ticker ${latestActivity.isFraud ? 'alert' : ''}`}>
          <div>
            <span className="ticker-tag">{latestActivity.label}</span>
            <span>{latestActivity.text}</span>
          </div>
          <small style={{ opacity: 0.8 }}>{latestActivity.timestamp}</small>
        </div>
      )}

      {/* Core Review 2 KPI Metric Cards */}
      <div className="metric-grid">
        {metrics.map(([label, value, note, color]) => (
          <div className="metric-card" key={label}>
            <div className="metric-top"><span>{label}</span><span className={`metric-dot ${color}`} /></div>
            <strong>{Number(value).toLocaleString()}</strong><small>{note}</small>
          </div>
        ))}
      </div>

      {/* Live Fraud Alerts Table */}
      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>Recent fraud alerts</h2>
            <p>Real-time graph signals broadcasted via WebSockets (bounded to 25 events)</p>
          </div>
          <button className="text-button" onClick={() => onNavigate('fraud')}>View all alerts →</button>
        </div>
        <AlertsTable alerts={data.alerts} scores={scores} />
      </section>

      <div className="dashboard-note">
        <span>Real-Time Graph Intelligence</span>
        <p>New transactions are dynamically ingested into Neo4j, evaluated against multi-factor graph risk algorithms, and pushed instantly to connected clients via WebSockets.</p>
      </div>
    </Page>
  );
}

export function Page({ title, subtitle, children, actions }) {
  return (
    <div className="page-wrap">
      <div className="page-title">
        <div>
          <div className="eyebrow">FRAUDGRAPH / MONITOR</div>
          <h1>{title}</h1>
          <p>{subtitle}</p>
        </div>
        {actions}
      </div>
      {children}
    </div>
  );
}

export function AlertsTable({ alerts, scores = {}, onNavigate }) {
  const [createdCases, setCreatedCases] = useState({});
  const [opening, setOpening] = useState(null);

  const handleOpenCase = async (alert, displayScore) => {
    const eid = alert.entityId;
    setOpening(eid);
    try {
      const res = await casesApi.create({
        entity_id: alert.entityId,
        entity_type: alert.entityType || 'Transaction',
        alert_id: alert.alert_id || alert.alertId,
        risk_score: typeof displayScore === 'number' ? displayScore : 75.0,
        title: `Investigation for ${alert.entityType || 'Entity'} ${alert.entityId}`,
        summary: alert.riskReason || 'Alert surfaced via real-time graph signals',
      });
      setCreatedCases((prev) => ({ ...prev, [eid]: res.data.case_id }));
      if (onNavigate) {
        onNavigate('cases');
      }
    } catch {
      // keep quiet or show error
    } finally {
      setOpening(null);
    }
  };

  if (!alerts.length) return <div className="empty-state">No alerts returned by current graph signals.</div>;
  return (
    <div className="table-scroll">
      <table className="data-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>Entity</th>
            <th>Risk score</th>
            <th>Risk level</th>
            <th>Reason</th>
            <th>Case</th>
          </tr>
        </thead>
        <tbody>
          {alerts.map((alert, index) => {
            const connectedScore = (alert.connectedEntities || []).map((id) => scores[id]).find(Boolean);
            const score = scores[alert.entityId] || connectedScore;
            const displayScore = alert.riskScore !== undefined ? alert.riskScore : (score ? score.riskScore : '—');
            const displayLevel = alert.riskLevel || (score ? score.riskLevel : 'LOW');
            const hasCase = createdCases[alert.entityId];

            return (
              <tr key={`${alert.entityType}-${alert.entityId}-${index}`} className={index === 0 ? 'new-alert-row' : ''}>
                <td className="mono">{alert.entityId}</td>
                <td><span className="entity-chip">{alert.entityType}</span></td>
                <td>{displayScore}</td>
                <td><RiskPill level={displayLevel} /></td>
                <td className="reason-cell">{alert.riskReason}</td>
                <td>
                  <button
                    className="case-action-btn secondary"
                    style={{ fontSize: 9, padding: '3px 7px' }}
                    disabled={opening === alert.entityId}
                    onClick={() => handleOpenCase(alert, displayScore)}
                  >
                    {hasCase ? `Case ✓` : opening === alert.entityId ? 'Opening…' : 'Open Case'}
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function RiskPill({ level }) {
  return <span className={`risk-pill ${String(level).toLowerCase()}`}>{level}</span>;
}
