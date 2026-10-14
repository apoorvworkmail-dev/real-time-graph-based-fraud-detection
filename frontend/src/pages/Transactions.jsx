import { useEffect, useState } from 'react';
import { transactionsApi } from '../api/client';
import { Page, RiskPill } from './Dashboard';

export default function Transactions() {
  const [transactions, setTransactions] = useState(null);
  const [filter, setFilter] = useState('all');
  const [error, setError] = useState('');

  useEffect(() => {
    transactionsApi.list({ limit: 250, is_fraud: filter === 'fraud' ? true : undefined })
      .then((response) => setTransactions(response.data))
      .catch((e) => setError(e.response?.data?.detail || 'Could not load transactions from FastAPI.'));
  }, [filter]);

  const shown = transactions?.filter((tx) => filter !== 'fraud' || tx.is_fraud) || [];
  return <Page title="Transactions" subtitle="Transfers and payments linked to their graph participants">
    {error && <div className="notice error-notice">{error}</div>}
    <section className="panel">
      <div className="panel-heading"><div><h2>Transaction list</h2><p>{transactions ? `${shown.length} records from Neo4j` : 'Loading transaction data…'}</p></div>
        <select value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Filter transactions"><option value="all">All transactions</option><option value="fraud">Fraud flagged</option></select>
      </div>
      {!transactions ? <div className="loading">Loading transactions…</div> : <div className="table-scroll"><table className="data-table"><thead><tr><th>Transaction ID</th><th>Amount</th><th>Timestamp</th><th>Sender</th><th>Receiver</th><th>Risk status</th></tr></thead><tbody>
        {shown.map((tx) => <tr key={tx.transaction_id}><td className="mono">{tx.transaction_id}</td><td>₹{Number(tx.amount || 0).toLocaleString()}</td><td>{tx.timestamp ? new Date(tx.timestamp).toLocaleString() : '—'}</td><td>{tx.sender_name || tx.sender_id || '—'}</td><td>{tx.receiver_name || tx.receiver_id || '—'}</td><td><RiskPill level={tx.is_fraud ? 'HIGH' : 'LOW'} /></td></tr>)}
      </tbody></table></div>}
    </section>
  </Page>;
}
