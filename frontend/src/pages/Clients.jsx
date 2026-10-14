import { useState } from 'react';
import { clientsApi, riskApi, mlApi } from '../api/client';
import { Page, RiskPill } from './Dashboard';

export default function Clients() {
  const [clientId, setClientId] = useState('');
  const [record, setRecord] = useState(null);
  const [risk, setRisk] = useState(null);
  const [mlData, setMlData] = useState(null);
  const [transactions, setTransactions] = useState([]);
  const [neighbors, setNeighbors] = useState([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function investigate(event) {
    event.preventDefault();
    const id = clientId.trim();
    if (!id) return;
    setLoading(true);
    setError('');
    setRecord(null);
    setMlData(null);

    try {
      const [clientResult, riskResult, txnResult, neighborResult, mlResult] = await Promise.all([
        clientsApi.get(id),
        riskApi.client(id),
        clientsApi.transactions(id),
        clientsApi.neighbors(id),
        mlApi.predictClient(id).catch(() => ({ data: null })),
      ]);
      setRecord(clientResult.data);
      setRisk(riskResult.data);
      setTransactions(txnResult.data);
      setNeighbors(neighborResult.data.nodes);
      if (mlResult.data && !mlResult.data.error) {
        setMlData(mlResult.data);
      }
    } catch (e) {
      setError(
        e.response?.status === 404
          ? `No client found for ID ${id}.`
          : e.response?.data?.detail || 'Could not load this client from FastAPI.'
      );
    } finally {
      setLoading(false);
    }
  }

  const related = (type) => neighbors.filter((node) => node._labels?.includes(type));
  const devices = related('Device');
  const locations = related('Location');
  const connectedClients = related('Client').filter((node) => node.client_id !== record?.client_id);

  return (
    <Page title="Client investigation" subtitle="Search a client to inspect rule-based risk, ML fraud probabilities, and graph connections">
      <form className="search-bar" onSubmit={investigate}>
        <label htmlFor="client-id">Client ID</label>
        <input
          id="client-id"
          value={clientId}
          onChange={(e) => setClientId(e.target.value)}
          placeholder="Enter Client ID (e.g. CLT031, CLT001)"
        />
        <button className="button-primary" disabled={loading}>
          {loading ? 'Searching…' : 'Investigate'}
        </button>
      </form>

      {error && <div className="notice error-notice">{error}</div>}

      {record && (
        <>
          {/* Top Score & Identity Strip */}
          <section className="investigation-summary" style={{ flexWrap: 'wrap', gap: '14px' }}>
            <div className="identity-card" style={{ minWidth: 260 }}>
              <div className="avatar">{record.name?.slice(0, 1) || 'C'}</div>
              <div>
                <span className="eyebrow">CLIENT / {record.client_id}</span>
                <h2>{record.name}</h2>
                <p>{record.email}</p>
              </div>
            </div>

            {/* Rule-Based Risk Card */}
            <div className="score-card" style={{ minWidth: 210 }}>
              <span>Rule-based risk score</span>
              <div>
                <strong>{risk?.riskScore ?? '—'}</strong>
                {risk && <RiskPill level={risk.riskLevel} />}
              </div>
              <small>Explainable graph factors</small>
            </div>

            {/* Machine Learning Model Prediction Card */}
            <div className="score-card" style={{ minWidth: 210 }}>
              <span>ML fraud probability</span>
              <div>
                <strong style={{ color: mlData?.mlFraudProbability >= 0.5 ? '#dc2626' : '#16a34a' }}>
                  {mlData ? `${(mlData.mlFraudProbability * 100).toFixed(1)}%` : '—'}
                </strong>
                {mlData && (
                  <span
                    className={`risk-pill ${mlData.mlFraudProbability >= 0.5 ? 'critical' : 'low'}`}
                    style={{ fontSize: 9 }}
                  >
                    {mlData.mlPrediction === 'PREDICTED_FRAUD' ? 'ML: FRAUD' : 'ML: LEGIT'}
                  </span>
                )}
              </div>
              <small>Random forest classifier</small>
            </div>

            {/* Combined Risk Index Card */}
            {mlData?.combinedRiskScore !== undefined && (
              <div className="score-card" style={{ minWidth: 210 }}>
                <span>Combined risk index</span>
                <div>
                  <strong>{mlData.combinedRiskScore} / 100</strong>
                  <RiskPill level={mlData.combinedRiskScore >= 50 ? 'HIGH' : (mlData.combinedRiskScore >= 25 ? 'MEDIUM' : 'LOW')} />
                </div>
                <small>60% rules + 40% ML</small>
              </div>
            )}
          </section>

          {/* Legal / Compliance Disclaimer */}
          <div style={{ background: '#f8fafc', padding: '10px 14px', borderRadius: '8px', border: '1px solid #e2e8f0', fontSize: 11, color: '#64748b', marginBottom: '16px' }}>
            ℹ️ <b>Investigative Disclaimer:</b> {mlData?.disclaimer || 'Machine learning predictions are triage signals for investigator review and do not constitute legal proof of financial crime.'}
          </div>

          <div className="investigation-grid">
            {/* Account Attributes & Rule Explanations */}
            <section className="panel">
              <div className="panel-heading">
                <div>
                  <h2>Client details</h2>
                  <p>Account and identity attributes</p>
                </div>
              </div>
              <dl className="details-list">
                <Detail label="Client ID" value={record.client_id} />
                <Detail label="Email" value={record.email} />
                <Detail label="Phone" value={record.phone} />
                <Detail label="Account type" value={record.account_type} />
                <Detail label="Balance" value={record.account_balance == null ? '—' : `₹${Number(record.account_balance).toLocaleString()}`} />
                <Detail label="KYC verified" value={record.kyc_verified ? 'Yes' : 'No'} />
                <Detail label="Flagged" value={record.is_flagged ? 'Yes' : 'No'} />
              </dl>

              {/* Explainable Rule-Based Breakdown */}
              <div className="reason-list">
                <h3>Rule-based score factors</h3>
                {risk?.reasons.length ? (
                  risk.reasons.map((reason) => (
                    <div className="reason-item" key={reason.factor}>
                      <span>{reason.explanation}</span>
                      <strong>+{reason.contribution}</strong>
                    </div>
                  ))
                ) : (
                  <p className="muted">No active graph risk signals.</p>
                )}
              </div>

              {/* Phase 8 Top Contributing ML Features */}
              {mlData?.topContributingFeatures?.length > 0 && (
                <div className="reason-list" style={{ borderTop: '1px solid #edf0f5' }}>
                  <h3>Key machine learning features</h3>
                  {mlData.topContributingFeatures.map((feat) => (
                    <div className="reason-item" key={feat.feature}>
                      <span>{feat.feature.replace(/_/g, ' ')}</span>
                      <strong>Value: {feat.value}</strong>
                    </div>
                  ))}
                </div>
              )}
            </section>

            {/* Connected Graph Entities */}
            <section className="panel">
              <div className="panel-heading">
                <div>
                  <h2>Connected graph entities</h2>
                  <p>Found by traversing two hops from this client</p>
                </div>
              </div>
              <EntityList title="Devices" nodes={devices} nameKey="ip_address" empty="No connected devices" />
              <EntityList title="Locations" nodes={locations} nameKey="city" empty="No connected locations" />
              <EntityList title="Connected clients" nodes={connectedClients} nameKey="name" empty="No connected clients" />
            </section>
          </div>

          {/* Transactions List */}
          <section className="panel">
            <div className="panel-heading">
              <div>
                <h2>Transactions</h2>
                <p>Outgoing transaction relationships for this client</p>
              </div>
              <span className="count-pill">{transactions.length}</span>
            </div>
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Transaction</th>
                    <th>Amount</th>
                    <th>Time</th>
                    <th>Receiver</th>
                    <th>Risk status</th>
                  </tr>
                </thead>
                <tbody>
                  {transactions.map((tx) => (
                    <tr key={tx.transaction_id}>
                      <td className="mono">{tx.transaction_id}</td>
                      <td>₹{Number(tx.amount || 0).toLocaleString()}</td>
                      <td>{formatDate(tx.timestamp)}</td>
                      <td>{tx.receiver_name || '—'}</td>
                      <td><RiskPill level={tx.is_fraud ? 'HIGH' : 'LOW'} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}

      {!record && !loading && !error && (
        <div className="empty-state">
          Enter a Client ID (e.g. <code>CLT031</code> for a synthetic fraudster or <code>CLT001</code> for legitimate) to inspect risk scores, ML predictions, transactions, and graph connections.
        </div>
      )}
    </Page>
  );
}

function Detail({ label, value }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value || '—'}</dd>
    </div>
  );
}

function EntityList({ title, nodes, nameKey, empty }) {
  return (
    <div className="entity-list">
      <h3>
        {title}<span>{nodes.length}</span>
      </h3>
      {nodes.length ? (
        nodes.slice(0, 8).map((node, i) => (
          <div className="entity-row" key={`${node.client_id || node.device_id || node.location_id || i}`}>
            <span>{node[nameKey] || node.client_id || node.device_id || node.location_id}</span>
            <code>{node.client_id || node.device_id || node.location_id}</code>
          </div>
        ))
      ) : (
        <p className="muted">{empty}</p>
      )}
    </div>
  );
}

function formatDate(value) {
  return value ? new Date(value).toLocaleString() : '—';
}
