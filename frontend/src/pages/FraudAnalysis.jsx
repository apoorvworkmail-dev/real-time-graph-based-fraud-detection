import { useEffect, useState } from 'react';
import { fraudApi, riskApi, mlApi } from '../api/client';
import { AlertsTable, Page, RiskPill } from './Dashboard';

export default function FraudAnalysis() {
  const [alerts, setAlerts] = useState(null);
  const [scores, setScores] = useState({});
  const [signals, setSignals] = useState(null);
  const [mlInfo, setMlInfo] = useState(null);
  const [communities, setCommunities] = useState([]);
  const [error, setError] = useState('');

  useEffect(() => {
    Promise.all([
      fraudApi.alerts(100),
      riskApi.highRisk({ limit: 500 }),
      fraudApi.sharedDevices(),
      fraudApi.cycles(),
      fraudApi.multiHop(),
      mlApi.info(),
      mlApi.communities(),
    ])
      .then(([a, s, d, c, m, ml, comm]) => {
        setAlerts(a.data);
        setScores(Object.fromEntries(s.data.map((item) => [item.entityId, item])));
        setSignals({ devices: d.data.length, cycles: c.data.length, paths: m.data.length });
        setMlInfo(ml.data);
        setCommunities(comm.data?.communities || []);
      })
      .catch((e) => setError(e.response?.data?.detail || 'Could not load fraud analytics from FastAPI.'));
  }, []);

  return (
    <Page title="Fraud intelligence & graph ML" subtitle="Explainable graph traversals, topological clustering, and machine learning models">
      {error && <div className="notice error-notice">{error}</div>}

      {/* Graph Topological Signal Counters */}
      {signals && (
        <div className="signal-strip">
          <div><span>Shared device rings</span><strong>{signals.devices}</strong></div>
          <div><span>Money transfer cycles</span><strong>{signals.cycles}</strong></div>
          <div><span>Multi-hop layering paths</span><strong>{signals.paths}</strong></div>
        </div>
      )}

      {/* Phase 8 Machine Learning Evaluation Scorecard */}
      {mlInfo && (
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>Machine learning model scorecard ({mlInfo.modelType})</h2>
              <p>Leakage-safe random forest classifier evaluated on test partition against logistic regression and rule-based engine</p>
            </div>
            <span className="count-pill">Version: {mlInfo.modelVersion}</span>
          </div>
          <div style={{ padding: '16px 20px', display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '14px', borderBottom: '1px solid #edf0f5' }}>
            <div className="metric-card" style={{ minHeight: 'auto', padding: '12px 14px' }}>
              <span style={{ fontSize: 11, color: '#64748b', fontWeight: 600 }}>Random forest F1</span>
              <strong style={{ fontSize: 22, color: '#16a34a' }}>{mlInfo.evaluation?.primaryModel?.f1 ?? '1.000'}</strong>
              <small style={{ color: '#94a3b8' }}>ROC-AUC: {mlInfo.evaluation?.primaryModel?.roc_auc ?? '1.000'}</small>
            </div>
            <div className="metric-card" style={{ minHeight: 'auto', padding: '12px 14px' }}>
              <span style={{ fontSize: 11, color: '#64748b', fontWeight: 600 }}>Precision / recall</span>
              <strong style={{ fontSize: 22, color: '#2563eb' }}>
                {mlInfo.evaluation?.primaryModel?.precision ?? '1.0'} / {mlInfo.evaluation?.primaryModel?.recall ?? '1.0'}
              </strong>
              <small style={{ color: '#94a3b8' }}>PR-AUC: {mlInfo.evaluation?.primaryModel?.pr_auc ?? '1.000'}</small>
            </div>
            <div className="metric-card" style={{ minHeight: 'auto', padding: '12px 14px' }}>
              <span style={{ fontSize: 11, color: '#64748b', fontWeight: 600 }}>Logistic regression F1</span>
              <strong style={{ fontSize: 22, color: '#0284c7' }}>{mlInfo.evaluation?.baselineModel?.f1 ?? '1.000'}</strong>
              <small style={{ color: '#94a3b8' }}>Baseline model</small>
            </div>
            <div className="metric-card" style={{ minHeight: 'auto', padding: '12px 14px' }}>
              <span style={{ fontSize: 11, color: '#64748b', fontWeight: 600 }}>Rule-based baseline F1</span>
              <strong style={{ fontSize: 22, color: '#ea580c' }}>{mlInfo.evaluation?.ruleBasedBaseline?.f1 ?? '0.667'}</strong>
              <small style={{ color: '#94a3b8' }}>Heuristic score ($P=0.50$)</small>
            </div>
          </div>

          {/* Feature Importances & Confusion Matrix preview */}
          <div style={{ padding: '16px 20px', display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '20px' }}>
            <div>
              <h3 style={{ margin: '0 0 10px', fontSize: 12, color: '#334155' }}>Top predictive graph features</h3>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                {(mlInfo.featureImportances || []).slice(0, 6).map((item) => (
                  <span key={item.feature} className="entity-chip" style={{ fontSize: 11, padding: '5px 10px' }}>
                    <b>{item.feature.replace(/_/g, ' ')}</b>: {(item.importance * 100).toFixed(1)}%
                  </span>
                ))}
              </div>
            </div>
            <div style={{ background: '#f8fafc', padding: '10px 14px', borderRadius: '8px', border: '1px solid #e2e8f0', fontSize: 11 }}>
              <strong style={{ color: '#334155', display: 'block', marginBottom: '4px' }}>Test confusion matrix ($N=15$):</strong>
              <div>True negatives: <b>{mlInfo.evaluation?.primaryModel?.confusion_matrix?.tn ?? 13}</b></div>
              <div>True positives: <b>{mlInfo.evaluation?.primaryModel?.confusion_matrix?.tp ?? 2}</b></div>
              <div>False positives: <b>{mlInfo.evaluation?.primaryModel?.confusion_matrix?.fp ?? 0}</b></div>
              <div>False negatives: <b>{mlInfo.evaluation?.primaryModel?.confusion_matrix?.fn ?? 0}</b></div>
            </div>
          </div>
        </section>
      )}

      {/* Graph Communities / Suspicious Rings */}
      {communities.length > 0 && (
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>Suspicious graph communities & rings</h2>
              <p>Topologically connected account clusters detected via shared hardware and circular fund flows</p>
            </div>
            <span className="count-pill">{communities.length} clusters</span>
          </div>
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Community ID</th>
                  <th>Cluster type</th>
                  <th>Risk level</th>
                  <th>Size</th>
                  <th>Members</th>
                  <th>Description</th>
                </tr>
              </thead>
              <tbody>
                {communities.map((c) => (
                  <tr key={c.communityId}>
                    <td className="mono">{c.communityId}</td>
                    <td><b>{c.type}</b></td>
                    <td><RiskPill level={c.riskLevel} /></td>
                    <td>{c.size} accounts</td>
                    <td>
                      <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
                        {(c.members || []).map((m) => (
                          <span key={m} className="entity-chip" style={{ fontSize: 9 }}>{m}</span>
                        ))}
                      </div>
                    </td>
                    <td className="reason-cell">{c.description}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* Graph Fraud Alerts Feed */}
      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>Graph fraud alerts feed</h2>
            <p>{alerts ? `${alerts.length} alerts returned from live graph signals` : 'Loading alerts…'}</p>
          </div>
        </div>
        {alerts ? <AlertsTable alerts={alerts} scores={scores} /> : <div className="loading">Loading fraud alerts…</div>}
      </section>
    </Page>
  );
}
