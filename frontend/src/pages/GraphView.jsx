import { useEffect, useRef, useState } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { graphApi } from '../api/client';
import { Page } from './Dashboard';

const colors = { Client: '#3478f6', Transaction: '#21a179', Device: '#e6a23c', Location: '#8b6fd6' };

export default function GraphView() {
  const [graph, setGraph] = useState({ nodes: [], links: [], stats: {} });
  const [selected, setSelected] = useState(null);
  const [error, setError] = useState('');
  const ref = useRef();

  useEffect(() => {
    graphApi.subgraph(20).then(({ data }) => setGraph(data))
      .catch((e) => setError(e.response?.data?.detail || 'Could not load graph data from FastAPI.'));
  }, []);

  return <Page title="Graph view" subtitle="Explore real Client, Transaction, Device and Location relationships from Neo4j">
    {error && <div className="notice error-notice">{error}</div>}
    <div className="graph-toolbar">
      <div className="graph-legend">{Object.entries(colors).map(([type, color]) => <span key={type}><i style={{ background: color }} />{type}</span>)}</div>
      <div className="graph-counts">{Object.entries(graph.stats || {}).filter(([key]) => key.endsWith('_nodes')).map(([key, count]) => <span key={key}>{key.replace('_nodes', '')}: <b>{count}</b></span>)}<span>edges: <b>{graph.links.length}</b></span></div>
    </div>
    <section className="panel graph-panel">
      {error ? <div className="empty-state">Graph data is unavailable.</div> : !graph.nodes.length ? <div className="loading">Loading graph relationships…</div> : <div className="graph-stage">
        <ForceGraph2D ref={ref} graphData={graph} height={560} backgroundColor="#f8fafc"
          nodeRelSize={5} linkDirectionalArrowLength={4} linkDirectionalArrowRelPos={1}
          linkColor={(link) => link.is_fraud ? '#df5360' : '#b7c4d5'} linkWidth={(link) => link.is_fraud ? 1.8 : 1}
          nodeColor={(node) => node.is_flagged || node.is_fraud ? '#dc5360' : colors[node.type] || '#7c8798'}
          nodeLabel={(node) => `${node.type}: ${node.label}${node.amount ? ` · ₹${node.amount}` : ''}`}
          onNodeClick={(node) => setSelected(node)} cooldownTicks={90} />
      </div>}
    </section>
    {selected && <section className="panel selected-node"><div className="panel-heading"><div><h2>Selected graph entity</h2><p>{selected.type}</p></div><button className="text-button" onClick={() => setSelected(null)}>Close</button></div>
      <div className="selected-node-details">{Object.entries(selected).filter(([key, value]) => !['x','y','vx','vy','index','__indexColor','color'].includes(key) && typeof value !== 'object').map(([key, value]) => <div key={key}><span>{key.replaceAll('_', ' ')}</span><b>{String(value ?? '—')}</b></div>)}</div>
    </section>}
  </Page>;
}
