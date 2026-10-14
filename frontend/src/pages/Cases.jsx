import { useEffect, useState } from 'react';
import { casesApi } from '../api/client';
import { Page, RiskPill } from './Dashboard';

const STATUS_OPTIONS = [
  { value: 'ALL', label: 'All Statuses' },
  { value: 'NEW_ALERT', label: 'New Alert' },
  { value: 'UNDER_INVESTIGATION', label: 'Under Investigation' },
  { value: 'ESCALATED', label: 'Escalated' },
  { value: 'CONFIRMED_FRAUD', label: 'Confirmed Fraud' },
  { value: 'DISMISSED_FALSE_POSITIVE', label: 'Dismissed (False Positive)' },
  { value: 'REOPENED', label: 'Reopened' },
];

const PRIORITY_OPTIONS = [
  { value: 'ALL', label: 'All Priorities' },
  { value: 'CRITICAL', label: 'Critical' },
  { value: 'HIGH', label: 'High' },
  { value: 'MEDIUM', label: 'Medium' },
  { value: 'LOW', label: 'Low' },
];

const ANALYSTS = ['unassigned', 'analyst_priya', 'analyst_alex', 'senior_analyst_mark'];

export default function Cases({ currentUser }) {
  const [cases, setCases] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [priorityFilter, setPriorityFilter] = useState('ALL');
  const [searchQuery, setSearchQuery] = useState('');

  // Selected case for investigation detail modal
  const [selectedCase, setSelectedCase] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [actionError, setActionError] = useState('');
  const [actionSuccess, setActionSuccess] = useState('');

  // Form states
  const [newNote, setNewNote] = useState('');
  const [resolutionModal, setResolutionModal] = useState(null); // { targetStatus: 'CONFIRMED_FRAUD' | 'DISMISSED_FALSE_POSITIVE' | 'REOPENED' }
  const [resCategory, setResCategory] = useState('TRUE_POSITIVE_FRAUD');
  const [resExplanation, setResExplanation] = useState('');

  const fetchCases = async () => {
    setLoading(true);
    try {
      const params = {};
      if (statusFilter !== 'ALL') params.status = statusFilter;
      if (priorityFilter !== 'ALL') params.priority = priorityFilter;
      if (searchQuery.trim()) params.search = searchQuery.trim();

      const res = await casesApi.list(params);
      setCases(res.data.cases || []);
      setTotal(res.data.total || 0);
      setError('');
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to fetch cases.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCases();
  }, [statusFilter, priorityFilter]);

  const handleSearchSubmit = (e) => {
    e.preventDefault();
    fetchCases();
  };

  const openCaseDetails = async (caseId) => {
    setDetailLoading(true);
    setActionError('');
    setActionSuccess('');
    try {
      const res = await casesApi.get(caseId);
      setSelectedCase(res.data);
    } catch (err) {
      setActionError(err.response?.data?.detail || 'Could not load case details.');
    } finally {
      setDetailLoading(false);
    }
  };

  const handleAssignAnalyst = async (newAnalyst) => {
    if (!selectedCase) return;
    setActionError('');
    setActionSuccess('');
    try {
      const res = await casesApi.assign(selectedCase.case_id, newAnalyst, currentUser?.username || 'analyst_console');
      setSelectedCase(res.data);
      setActionSuccess(`Assigned to ${newAnalyst}`);
      fetchCases();
    } catch (err) {
      setActionError(err.response?.data?.detail || 'Failed to assign analyst.');
    }
  };

  const handleUpdatePriority = async (newPriority) => {
    if (!selectedCase) return;
    setActionError('');
    setActionSuccess('');
    try {
      const res = await casesApi.updatePriority(selectedCase.case_id, newPriority, currentUser?.username || 'analyst_console');
      setSelectedCase(res.data);
      setActionSuccess(`Priority updated to ${newPriority}`);
      fetchCases();
    } catch (err) {
      setActionError(err.response?.data?.detail || 'Failed to update priority.');
    }
  };

  const handleTransition = async (targetStatus) => {
    if (!selectedCase) return;
    if (targetStatus === 'CONFIRMED_FRAUD' || targetStatus === 'DISMISSED_FALSE_POSITIVE' || targetStatus === 'REOPENED') {
      setResolutionModal({ targetStatus });
      setResCategory(targetStatus === 'CONFIRMED_FRAUD' ? 'TRUE_POSITIVE_FRAUD' : 'FALSE_POSITIVE_NORMAL_ACTIVITY');
      setResExplanation('');
      return;
    }

    setActionError('');
    setActionSuccess('');
    try {
      const res = await casesApi.transition(selectedCase.case_id, {
        target_status: targetStatus,
        actor: selectedCase.assigned_analyst || 'analyst',
        expected_version: selectedCase.version,
      });
      setSelectedCase(res.data);
      setActionSuccess(`Status transitioned to ${targetStatus}`);
      fetchCases();
    } catch (err) {
      setActionError(err.response?.data?.detail || 'State transition failed.');
    }
  };

  const submitResolution = async () => {
    if (!selectedCase || !resolutionModal) return;
    if (!resExplanation.trim() || resExplanation.trim().length < 5) {
      setActionError('A valid resolution explanation (minimum 5 characters) is required.');
      return;
    }

    setActionError('');
    setActionSuccess('');
    try {
      const payload = {
        target_status: resolutionModal.targetStatus,
        actor: currentUser?.username || selectedCase.assigned_analyst || 'analyst',
        expected_version: selectedCase.version,
        resolution_explanation: resExplanation.trim(),
      };
      if (resolutionModal.targetStatus !== 'REOPENED') {
        payload.resolution_category = resCategory;
      } else {
        payload.reason = resExplanation.trim();
      }

      const res = await casesApi.transition(selectedCase.case_id, payload);
      setSelectedCase(res.data);
      setActionSuccess(`Case updated: ${resolutionModal.targetStatus}`);
      setResolutionModal(null);
      fetchCases();
    } catch (err) {
      setActionError(err.response?.data?.detail || 'Resolution transition failed.');
    }
  };

  const handleAddNote = async (e) => {
    e.preventDefault();
    if (!selectedCase || !newNote.trim()) return;
    setActionError('');
    setActionSuccess('');
    try {
      await casesApi.addNote(selectedCase.case_id, newNote.trim(), currentUser?.username || selectedCase.assigned_analyst || 'analyst');
      setNewNote('');
      const updated = await casesApi.get(selectedCase.case_id);
      setSelectedCase(updated.data);
      setActionSuccess('Investigator note added');
      fetchCases();
    } catch (err) {
      setActionError(err.response?.data?.detail || 'Failed to add note.');
    }
  };

  // Metrics counts
  const countNew = cases.filter((c) => c.status === 'NEW_ALERT').length;
  const countActive = cases.filter((c) => c.status === 'UNDER_INVESTIGATION' || c.status === 'ESCALATED').length;
  const countFraud = cases.filter((c) => c.status === 'CONFIRMED_FRAUD').length;
  const countDismissed = cases.filter((c) => c.status === 'DISMISSED_FALSE_POSITIVE').length;

  return (
    <Page
      title="Fraud Case Management"
      subtitle="Investigate alerts, assign analysts, track graph neighborhood context, and record append-only audit decisions"
    >
      {error && <div className="notice error-notice">{error}</div>}

      {/* KPI Metric Strip */}
      <div className="metric-grid">
        <div className="metric-card">
          <div className="metric-top"><span>Total cases recorded</span><div className="metric-dot blue" /></div>
          <strong>{total}</strong>
          <small>Audit trail enforced</small>
        </div>
        <div className="metric-card">
          <div className="metric-top"><span>New & active alerts</span><div className="metric-dot amber" /></div>
          <strong>{countNew + countActive}</strong>
          <small>{countNew} new, {countActive} in progress</small>
        </div>
        <div className="metric-card">
          <div className="metric-top"><span>Confirmed fraud</span><div className="metric-dot red" /></div>
          <strong>{countFraud}</strong>
          <small>{countDismissed} dismissed false positives</small>
        </div>
      </div>

      {/* Search and Filters */}
      <div className="search-bar" style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
        <form onSubmit={handleSearchSubmit} style={{ display: 'flex', gap: '8px', flex: '1 1 300px' }}>
          <input
            type="text"
            placeholder="Search by Case ID, Entity ID (TXN_*, CLT*), or title..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          <button type="submit" className="button-primary">Search</button>
        </form>

        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <label style={{ fontSize: 11, color: '#64748b' }}>Status:</label>
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            {STATUS_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>

        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <label style={{ fontSize: 11, color: '#64748b' }}>Priority:</label>
          <select value={priorityFilter} onChange={(e) => setPriorityFilter(e.target.value)}>
            {PRIORITY_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Case List Table */}
      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>Investigator Case Registry</h2>
            <p>Select any case to review graph evidence, assign analysts, or execute lifecycle transitions</p>
          </div>
          <span className="count-pill">{cases.length} displayed</span>
        </div>

        {loading ? (
          <div className="loading">Loading fraud cases…</div>
        ) : cases.length === 0 ? (
          <div className="empty-state">No cases match the selected filter criteria.</div>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Case ID</th>
                  <th>Entity</th>
                  <th>Title & Summary</th>
                  <th>Status</th>
                  <th>Priority</th>
                  <th>Assigned</th>
                  <th>Risk Score</th>
                  <th>Updated</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {cases.map((c) => (
                  <tr key={c.case_id}>
                    <td className="mono" style={{ cursor: 'pointer' }} onClick={() => openCaseDetails(c.case_id)}>
                      {c.case_id}
                    </td>
                    <td>
                      <span className="entity-chip">{c.entity_type}: {c.entity_id}</span>
                    </td>
                    <td>
                      <strong>{c.title}</strong>
                      <div style={{ fontSize: 10, color: '#64748b', marginTop: 2 }}>{c.summary}</div>
                    </td>
                    <td>
                      <span className={`status-badge ${c.status.toLowerCase()}`}>
                        {c.status.replace(/_/g, ' ')}
                      </span>
                    </td>
                    <td>
                      <span className={`priority-badge ${c.priority.toLowerCase()}`}>
                        {c.priority}
                      </span>
                    </td>
                    <td>
                      <span style={{ fontSize: 11, color: c.assigned_analyst === 'unassigned' ? '#94a3b8' : '#2563eb' }}>
                        {c.assigned_analyst}
                      </span>
                    </td>
                    <td>
                      <RiskPill level={c.risk_score >= 80 ? 'CRITICAL' : c.risk_score >= 60 ? 'HIGH' : c.risk_score >= 40 ? 'MEDIUM' : 'LOW'} />
                    </td>
                    <td style={{ fontSize: 10, color: '#94a3b8' }}>
                      {new Date(c.updated_at).toLocaleDateString()} {new Date(c.updated_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </td>
                    <td>
                      <button
                        className="case-action-btn secondary"
                        onClick={() => openCaseDetails(c.case_id)}
                      >
                        Investigate →
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Case Details Modal */}
      {selectedCase && (
        <div className="case-modal-overlay" onClick={() => setSelectedCase(null)}>
          <div className="case-modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <h2 style={{ margin: 0, fontSize: 18, color: '#1e293b' }}>{selectedCase.case_id}</h2>
                  <span className={`status-badge ${selectedCase.status.toLowerCase()}`}>
                    {selectedCase.status.replace(/_/g, ' ')}
                  </span>
                  <span className={`priority-badge ${selectedCase.priority.toLowerCase()}`}>
                    {selectedCase.priority}
                  </span>
                </div>
                <p style={{ margin: '4px 0 0', color: '#64748b', fontSize: 12 }}>
                  {selectedCase.title} &bull; Entity: <b className="mono">{selectedCase.entity_id}</b> ({selectedCase.entity_type}) &bull; Concurrency v{selectedCase.version}
                </p>
              </div>
              <button
                className="text-button"
                style={{ fontSize: 18, color: '#64748b' }}
                onClick={() => setSelectedCase(null)}
              >
                ✕
              </button>
            </div>

            <div className="modal-body">
              {actionError && <div className="notice error-notice">{actionError}</div>}
              {actionSuccess && (
                <div className="notice" style={{ background: '#ecfdf5', color: '#047857', border: '1px solid #a7f3d0' }}>
                  {actionSuccess}
                </div>
              )}

              {/* Lifecycle State Actions */}
              <div style={{ background: '#f8fafc', padding: '14px 18px', borderRadius: 8, border: '1px solid #e2e8f0', marginBottom: 20 }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: '#475569', marginBottom: 8 }}>
                  LIFECYCLE TRANSITION CONTROLS (Current: {selectedCase.status})
                </div>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  {selectedCase.status === 'NEW_ALERT' && (
                    <>
                      <button className="case-action-btn primary" onClick={() => handleTransition('UNDER_INVESTIGATION')}>
                        Start Investigation
                      </button>
                      <button className="case-action-btn warning" onClick={() => handleTransition('ESCALATED')}>
                        Escalate
                      </button>
                      <button className="case-action-btn secondary" onClick={() => handleTransition('DISMISSED_FALSE_POSITIVE')}>
                        Dismiss (False Positive)
                      </button>
                    </>
                  )}
                  {selectedCase.status === 'UNDER_INVESTIGATION' && (
                    <>
                      <button className="case-action-btn danger" onClick={() => handleTransition('CONFIRMED_FRAUD')}>
                        Confirm Fraud
                      </button>
                      <button className="case-action-btn secondary" onClick={() => handleTransition('DISMISSED_FALSE_POSITIVE')}>
                        Dismiss (False Positive)
                      </button>
                      <button className="case-action-btn warning" onClick={() => handleTransition('ESCALATED')}>
                        Escalate Case
                      </button>
                    </>
                  )}
                  {selectedCase.status === 'ESCALATED' && (
                    <>
                      <button className="case-action-btn primary" onClick={() => handleTransition('UNDER_INVESTIGATION')}>
                        Resume Investigation
                      </button>
                      <button className="case-action-btn danger" onClick={() => handleTransition('CONFIRMED_FRAUD')}>
                        Confirm Fraud
                      </button>
                      <button className="case-action-btn secondary" onClick={() => handleTransition('DISMISSED_FALSE_POSITIVE')}>
                        Dismiss (False Positive)
                      </button>
                    </>
                  )}
                  {(selectedCase.status === 'CONFIRMED_FRAUD' || selectedCase.status === 'DISMISSED_FALSE_POSITIVE') && (
                    <button className="case-action-btn success" onClick={() => handleTransition('REOPENED')}>
                      Reopen Investigation
                    </button>
                  )}
                  {selectedCase.status === 'REOPENED' && (
                    <>
                      <button className="case-action-btn primary" onClick={() => handleTransition('UNDER_INVESTIGATION')}>
                        Investigate
                      </button>
                      <button className="case-action-btn danger" onClick={() => handleTransition('CONFIRMED_FRAUD')}>
                        Confirm Fraud
                      </button>
                      <button className="case-action-btn secondary" onClick={() => handleTransition('DISMISSED_FALSE_POSITIVE')}>
                        Dismiss (False Positive)
                      </button>
                    </>
                  )}
                </div>

                {selectedCase.resolution_category && (
                  <div style={{ marginTop: 12, padding: 10, background: '#fff', borderRadius: 6, border: '1px solid #e2e8f0', fontSize: 11 }}>
                    <span style={{ color: '#64748b' }}>Resolution Category: </span>
                    <b>{selectedCase.resolution_category}</b>
                    <p style={{ margin: '4px 0 0', color: '#334155' }}>
                      <em>Explanation:</em> {selectedCase.resolution_explanation}
                    </p>
                  </div>
                )}
              </div>

              {/* Case Assignment & Priority Controls */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginBottom: 20 }}>
                <div style={{ background: '#fff', padding: 12, borderRadius: 8, border: '1px solid #e2e8f0' }}>
                  <label style={{ fontSize: 11, fontWeight: 700, color: '#64748b', display: 'block', marginBottom: 6 }}>
                    Assigned Analyst:
                  </label>
                  <select
                    value={selectedCase.assigned_analyst}
                    onChange={(e) => handleAssignAnalyst(e.target.value)}
                    style={{ width: '100%' }}
                  >
                    {ANALYSTS.map((a) => (
                      <option key={a} value={a}>{a}</option>
                    ))}
                  </select>
                </div>

                <div style={{ background: '#fff', padding: 12, borderRadius: 8, border: '1px solid #e2e8f0' }}>
                  <label style={{ fontSize: 11, fontWeight: 700, color: '#64748b', display: 'block', marginBottom: 6 }}>
                    Priority / Severity:
                  </label>
                  <select
                    value={selectedCase.priority}
                    onChange={(e) => handleUpdatePriority(e.target.value)}
                    style={{ width: '100%' }}
                  >
                    {PRIORITY_OPTIONS.filter((p) => p.value !== 'ALL').map((p) => (
                      <option key={p.value} value={p.value}>{p.label}</option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Graph Neighborhood Context */}
              {selectedCase.graph_context && (
                <div style={{ background: '#fff', padding: '14px 18px', borderRadius: 8, border: '1px solid #e2e8f0', marginBottom: 20 }}>
                  <h3 style={{ margin: '0 0 10px', fontSize: 12, color: '#334155' }}>
                    Graph Context & Neighboring Entities
                  </h3>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, fontSize: 11 }}>
                    <div style={{ background: '#f8fafc', padding: 10, borderRadius: 6 }}>
                      <strong style={{ color: '#475569', display: 'block', marginBottom: 4 }}>Counterparties</strong>
                      {(selectedCase.graph_context.counterparties || []).length > 0 ? (
                        (selectedCase.graph_context.counterparties || []).map((cp, idx) => (
                          <div key={idx} style={{ marginBottom: 2 }}>
                            <span className="entity-chip" style={{ fontSize: 9 }}>{cp.role || 'peer'}</span>{' '}
                            <b className="mono">{cp.id}</b>
                          </div>
                        ))
                      ) : (
                        <span style={{ color: '#94a3b8' }}>None linked</span>
                      )}
                    </div>

                    <div style={{ background: '#f8fafc', padding: 10, borderRadius: 6 }}>
                      <strong style={{ color: '#475569', display: 'block', marginBottom: 4 }}>Devices & Hardware</strong>
                      {(selectedCase.graph_context.devices || []).length > 0 ? (
                        (selectedCase.graph_context.devices || []).map((d, idx) => (
                          <div key={idx} style={{ marginBottom: 2 }}>
                            <b className="mono">{d.device_id}</b>{' '}
                            {d.ip_address && <small style={{ color: '#64748b' }}>({d.ip_address})</small>}
                          </div>
                        ))
                      ) : (
                        <span style={{ color: '#94a3b8' }}>None linked</span>
                      )}
                    </div>

                    <div style={{ background: '#f8fafc', padding: 10, borderRadius: 6 }}>
                      <strong style={{ color: '#475569', display: 'block', marginBottom: 4 }}>Locations & Geolocation</strong>
                      {(selectedCase.graph_context.locations || []).length > 0 ? (
                        (selectedCase.graph_context.locations || []).map((l, idx) => (
                          <div key={idx} style={{ marginBottom: 2 }}>
                            <b className="mono">{l.location_id}</b>: {l.city}, {l.country}
                          </div>
                        ))
                      ) : (
                        <span style={{ color: '#94a3b8' }}>None linked</span>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {/* Analyst Observations & Notes */}
              <div style={{ background: '#fff', padding: '14px 18px', borderRadius: 8, border: '1px solid #e2e8f0', marginBottom: 20 }}>
                <h3 style={{ margin: '0 0 10px', fontSize: 12, color: '#334155' }}>
                  Analyst Observations ({selectedCase.notes?.length || 0})
                </h3>
                <div style={{ maxHeight: 180, overflowY: 'auto', marginBottom: 12 }}>
                  {(selectedCase.notes || []).map((n) => (
                    <div key={n.note_id} style={{ padding: '8px 10px', background: '#f8fafc', borderRadius: 6, marginBottom: 6, fontSize: 11 }}>
                      <div style={{ display: 'flex', justifySelf: 'space-between', justifyContent: 'space-between', color: '#64748b', fontSize: 10, marginBottom: 2 }}>
                        <span><b>{n.author}</b> recorded:</span>
                        <span>{new Date(n.created_at).toLocaleString()}</span>
                      </div>
                      <div style={{ color: '#1e293b' }}>{n.note}</div>
                    </div>
                  ))}
                  {(!selectedCase.notes || selectedCase.notes.length === 0) && (
                    <div style={{ color: '#94a3b8', fontSize: 11 }}>No notes recorded yet.</div>
                  )}
                </div>

                <form onSubmit={handleAddNote} style={{ display: 'flex', gap: 8 }}>
                  <input
                    type="text"
                    placeholder="Add an investigative note or evidence observation..."
                    value={newNote}
                    onChange={(e) => setNewNote(e.target.value)}
                    style={{ flex: 1 }}
                  />
                  <button type="submit" className="button-primary">Add Note</button>
                </form>
              </div>

              {/* Chronological Append-Only Audit Trail */}
              <div style={{ background: '#fff', padding: '14px 18px', borderRadius: 8, border: '1px solid #e2e8f0' }}>
                <h3 style={{ margin: '0 0 4px', fontSize: 12, color: '#334155' }}>
                  Append-Only Case Audit Trail
                </h3>
                <p style={{ margin: '0 0 10px', color: '#8a95a6', fontSize: 10 }}>
                  Immutable chronological log of all transitions, reassignments, and closures
                </p>

                <div className="timeline-wrap">
                  {(selectedCase.audit_trail || []).map((a) => (
                    <div key={a.audit_id} className="timeline-item">
                      <div className="timeline-dot" />
                      <div className="timeline-header">
                        <strong style={{ color: '#1e293b' }}>{a.action_type}</strong>
                        <span style={{ color: '#94a3b8', fontSize: 10 }}>
                          {new Date(a.timestamp).toLocaleString()} by <b>{a.actor}</b>
                        </span>
                      </div>
                      <div className="timeline-body">
                        {a.reason && <div>{a.reason}</div>}
                        {a.previous_value && (
                          <div style={{ fontSize: 10, color: '#94a3b8', marginTop: 2 }}>
                            Previous: {JSON.stringify(a.previous_value)} &rarr; New: {JSON.stringify(a.new_value)}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="modal-footer">
              <button className="case-action-btn secondary" onClick={() => setSelectedCase(null)}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Resolution Dialog Modal */}
      {resolutionModal && (
        <div className="case-modal-overlay" style={{ zIndex: 1100 }}>
          <div className="case-modal-content" style={{ maxWidth: 500 }} onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3 style={{ margin: 0, fontSize: 14 }}>
                {resolutionModal.targetStatus === 'REOPENED'
                  ? 'Reopen Investigation'
                  : `Resolve Case: ${resolutionModal.targetStatus.replace(/_/g, ' ')}`}
              </h3>
              <button className="text-button" onClick={() => setResolutionModal(null)}>✕</button>
            </div>
            <div className="modal-body">
              {resolutionModal.targetStatus !== 'REOPENED' && (
                <div style={{ marginBottom: 14 }}>
                  <label style={{ display: 'block', fontSize: 11, fontWeight: 700, color: '#475569', marginBottom: 4 }}>
                    Resolution Category:
                  </label>
                  <select
                    value={resCategory}
                    onChange={(e) => setResCategory(e.target.value)}
                    style={{ width: '100%' }}
                  >
                    <option value="TRUE_POSITIVE_FRAUD">True Positive Fraud</option>
                    <option value="FALSE_POSITIVE_NORMAL_ACTIVITY">False Positive (Normal Activity)</option>
                    <option value="CUSTOMER_DISPUTE">Customer Dispute</option>
                    <option value="UNRESOLVED_ESCALATED">Unresolved Escalated</option>
                    <option value="OTHER">Other</option>
                  </select>
                </div>
              )}

              <div>
                <label style={{ display: 'block', fontSize: 11, fontWeight: 700, color: '#475569', marginBottom: 4 }}>
                  {resolutionModal.targetStatus === 'REOPENED' ? 'Reopening Justification:' : 'Resolution Explanation (Required):'}
                </label>
                <textarea
                  rows={4}
                  style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid #cbd5e1', fontSize: 12, resize: 'vertical' }}
                  placeholder="Provide evidence rationale and investigator findings..."
                  value={resExplanation}
                  onChange={(e) => setResExplanation(e.target.value)}
                />
                <small style={{ color: '#94a3b8' }}>Minimum 5 characters required for compliance.</small>
              </div>
            </div>
            <div className="modal-footer">
              <button className="case-action-btn secondary" onClick={() => setResolutionModal(null)}>
                Cancel
              </button>
              <button className="case-action-btn primary" onClick={submitResolution}>
                Confirm Decision
              </button>
            </div>
          </div>
        </div>
      )}
    </Page>
  );
}
