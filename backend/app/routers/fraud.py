"""
Phase 5 & 6 — Fraud detection + explainable risk scoring
Queries:
  1. /alerts          — All flagged fraud transactions
  2. /shared-device   — Clients sharing same device (ring signal)
  3. /velocity        — High-frequency transactions (velocity fraud)
  4. /cycles          — Money cycle detection (A→B→C→A)
  5. /high-risk-locations — Transactions from high-risk countries
  6. /risk-score/{client_id} — Explainable risk scoring
  7. /summary         — Platform-wide fraud summary
"""
from fastapi import APIRouter, Depends, Query
from neo4j import Session
from app.db.neo4j_driver import get_session
from app.auth.dependencies import require_permission

router = APIRouter(dependencies=[Depends(require_permission("fraud:read"))])


def _records(session: Session, query: str, **params):
    return [dict(record) for record in session.run(query, **params)]


@router.get("/shared-devices", summary="Find devices shared across clients")
def shared_devices(min_clients: int = Query(2, ge=2, le=100), limit: int = Query(100, ge=1, le=500),
                   session: Session = Depends(get_session)):
    rows = _records(session, """
        MATCH (c:Client)-[:USED_DEVICE]->(d:Device)<-[:USED_DEVICE]-(other:Client)
        WITH d, collect(DISTINCT c) + collect(DISTINCT other) AS pairClients
        UNWIND pairClients AS client
        WITH d, collect(DISTINCT client) AS clients
        WHERE size(clients) >= $min_clients
        RETURN d.device_id AS deviceId, size(clients) AS numberOfClients,
               [c IN clients | c.client_id] AS clientIds,
               CASE WHEN coalesce(d.is_suspicious, false) THEN 'Device is marked suspicious and shared by multiple clients'
                    WHEN any(c IN clients WHERE coalesce(c.is_flagged, false)) THEN 'Shared device is connected to a flagged client'
                    ELSE 'Device is shared by multiple clients' END AS riskReason
        ORDER BY numberOfClients DESC, deviceId LIMIT $limit
    """, min_clients=min_clients, limit=limit)
    return rows


@router.get("/shared-locations", summary="Find locations connected to multiple clients or transactions")
def shared_locations(min_clients: int = Query(2, ge=2, le=100), min_transactions: int = Query(2, ge=2, le=1000),
                     limit: int = Query(100, ge=1, le=500), session: Session = Depends(get_session)):
    return _records(session, """
        MATCH (c:Client)-[:PERFORMED]->(t:Transaction)-[:ORIGINATED_FROM]->(l:Location)
        WITH l, collect(DISTINCT c) AS clients, collect(DISTINCT t) AS transactions
        WHERE size(clients) >= $min_clients OR size(transactions) >= $min_transactions
              OR coalesce(l.is_high_risk, false)
        RETURN l.location_id AS locationId, l.ip_address AS ipAddress,
               l.city AS city, l.country AS country,
               size(clients) AS numberOfClients, size(transactions) AS numberOfTransactions,
               [c IN clients | c.client_id] AS clientIds,
               [t IN transactions | {transactionId:t.transaction_id, amount:t.amount,
                   timestamp:t.timestamp, isFraud:t.is_fraud}] AS transactions,
               CASE WHEN coalesce(l.is_high_risk, false) THEN 'Location is marked high risk'
                    WHEN size(clients) >= $min_clients THEN 'Location is connected to multiple clients'
                    ELSE 'Location is used by multiple transactions' END AS riskReason
        ORDER BY numberOfClients DESC, numberOfTransactions DESC LIMIT $limit
    """, min_clients=min_clients, min_transactions=min_transactions, limit=limit)


@router.get("/multi-hop", summary="Find suspicious multi-hop transaction paths")
def multi_hop(limit: int = Query(50, ge=1, le=200), session: Session = Depends(get_session)):
    # Three directed transfers give a genuine six-edge Client -> Transaction -> Client traversal.
    return _records(session, """
        MATCH (a:Client)-[:PERFORMED]->(t1:Transaction)-[:TRANSFERRED_TO]->(b:Client)
              -[:PERFORMED]->(t2:Transaction)-[:TRANSFERRED_TO]->(c:Client)
              -[:PERFORMED]->(t3:Transaction)-[:TRANSFERRED_TO]->(d:Client)
        WHERE a <> b AND b <> c AND c <> d
          AND (coalesce(a.is_flagged,false) OR coalesce(b.is_flagged,false)
               OR coalesce(c.is_flagged,false) OR coalesce(d.is_flagged,false)
               OR coalesce(t1.is_fraud,false) OR coalesce(t2.is_fraud,false) OR coalesce(t3.is_fraud,false))
        RETURN a.client_id AS startClientId, d.client_id AS endClientId,
               [a.client_id,b.client_id,c.client_id,d.client_id] AS clientIds,
               [{transactionId:t1.transaction_id,amount:t1.amount,timestamp:t1.timestamp,
                 isFraud:t1.is_fraud,fraudScore:t1.fraud_score},
                {transactionId:t2.transaction_id,amount:t2.amount,timestamp:t2.timestamp,
                 isFraud:t2.is_fraud,fraudScore:t2.fraud_score},
                {transactionId:t3.transaction_id,amount:t3.amount,timestamp:t3.timestamp,
                 isFraud:t3.is_fraud,fraudScore:t3.fraud_score}] AS transactions,
               3 AS transactionHops,
               'Three-hop client transfer path contains a flagged client or fraudulent transaction' AS riskReason
        ORDER BY startClientId, endClientId LIMIT $limit
    """, limit=limit)


@router.get("/cycles", summary="Find circular transaction paths")
def cycle_detection(session: Session = Depends(get_session), limit: int = Query(100, ge=1, le=500)):
    rows = _records(session, """
        MATCH (a:Client)-[:PERFORMED]->(t1:Transaction)-[:TRANSFERRED_TO]->(b:Client)
              -[:PERFORMED]->(t2:Transaction)-[:TRANSFERRED_TO]->(c:Client)
              -[:PERFORMED]->(t3:Transaction)-[:TRANSFERRED_TO]->(a)
        WHERE a.client_id < b.client_id AND b.client_id < c.client_id
          AND (coalesce(a.is_flagged,false) OR coalesce(b.is_flagged,false) OR coalesce(c.is_flagged,false)
               OR coalesce(t1.is_fraud,false) OR coalesce(t2.is_fraud,false) OR coalesce(t3.is_fraud,false))
        RETURN [a.client_id,b.client_id,c.client_id] AS clientIds,
               [t1.transaction_id,t2.transaction_id,t3.transaction_id] AS transactionIds,
               [{transactionId:t1.transaction_id,amount:t1.amount,timestamp:t1.timestamp,isFraud:t1.is_fraud},
                {transactionId:t2.transaction_id,amount:t2.amount,timestamp:t2.timestamp,isFraud:t2.is_fraud},
                {transactionId:t3.transaction_id,amount:t3.amount,timestamp:t3.timestamp,isFraud:t3.is_fraud}] AS transactions,
               'Closed three-client transfer cycle contains a flagged client or a fraud-marked transaction' AS riskReason
        ORDER BY clientIds LIMIT $limit
    """, limit=limit)
    return rows


@router.get("/alerts", summary="Combine graph-derived fraud signals into alerts")
def fraud_alerts(limit: int = Query(100, ge=1, le=500), session: Session = Depends(get_session)):
    group_limit = max(1, limit // 5)
    device_group = []
    device_alerts = _records(session, """
        MATCH (c:Client)-[:USED_DEVICE]->(d:Device)<-[:USED_DEVICE]-(other:Client)
        WITH d, collect(DISTINCT c) + collect(DISTINCT other) AS paired
        UNWIND paired AS client
        WITH d, collect(DISTINCT client) AS clients
        WHERE size(clients) > 1 OR coalesce(d.is_suspicious,false)
        UNWIND clients AS client
        OPTIONAL MATCH (client)-[:PERFORMED]->(t:Transaction)
        WITH d, clients,
             collect(DISTINCT CASE WHEN t IS NULL THEN null ELSE
                 {transactionId:t.transaction_id,amount:t.amount,timestamp:t.timestamp,isFraud:t.is_fraud} END) AS txns
        RETURN d.device_id AS entityId, [c IN clients | c.client_id] AS connectedEntities,
               [c IN clients WHERE coalesce(c.is_flagged,false) | c.client_id] AS flaggedClients,
               txns AS txns
        LIMIT $limit
    """, limit=group_limit)
    for row in device_alerts:
        device_group.append({"entityType": "DEVICE", "entityId": row["entityId"],
                             "riskReason": "Shared or suspicious device links clients in the graph",
                             "connectedEntities": row["connectedEntities"], "relevantTransactions": row["txns"],
                             "evidence": {"flaggedClientIds": row["flaggedClients"]}})

    location_group = []
    location_alerts = _records(session, """
        MATCH (c:Client)-[:PERFORMED]->(t:Transaction)-[:ORIGINATED_FROM]->(l:Location)
        WITH l, collect(DISTINCT c) AS clients, collect(DISTINCT t) AS txns
        WHERE coalesce(l.is_high_risk,false) OR size(clients) > 1
        RETURN l.location_id AS entityId, l.ip_address AS ipAddress,
               [c IN clients | c.client_id] AS connectedEntities,
               [t IN txns | {transactionId:t.transaction_id,amount:t.amount,timestamp:t.timestamp,isFraud:t.is_fraud}] AS txns
        LIMIT $limit
    """, limit=group_limit)
    for row in location_alerts:
        location_group.append({"entityType": "LOCATION", "entityId": row["entityId"],
                               "riskReason": "High-risk or multi-client transaction location",
                               "connectedEntities": row["connectedEntities"], "relevantTransactions": row["txns"],
                               "evidence": {"ipAddress": row["ipAddress"]}})

    transaction_group = []
    fraud_txns = _records(session, """
        MATCH (sender:Client)-[:PERFORMED]->(t:Transaction)-[:TRANSFERRED_TO]->(receiver:Client)
        WHERE coalesce(t.is_fraud,false) OR coalesce(sender.is_flagged,false)
        OPTIONAL MATCH (t)-[:ORIGINATED_FROM]->(l:Location)
        RETURN t.transaction_id AS entityId, sender.client_id AS senderId, receiver.client_id AS receiverId,
               {transactionId:t.transaction_id,amount:t.amount,timestamp:t.timestamp,
                isFraud:t.is_fraud,fraudScore:t.fraud_score,locationId:l.location_id} AS transaction
        ORDER BY t.fraud_score DESC LIMIT $limit
    """, limit=group_limit)
    for row in fraud_txns:
        transaction_group.append({"entityType": "TRANSACTION", "entityId": row["entityId"],
                                  "riskReason": "Transaction is flagged as fraudulent or sent by a flagged client",
                                  "connectedEntities": [row["senderId"], row["receiverId"]],
                                  "relevantTransactions": [row["transaction"]], "evidence": {}})

    cycle_group = []
    cycles = cycle_detection(session=session, limit=group_limit)
    for cycle in cycles:
        cycle_group.append({"entityType": "CYCLE", "entityId": cycle["transactionIds"][0],
                            "riskReason": cycle["riskReason"], "connectedEntities": cycle["clientIds"],
                            "relevantTransactions": cycle["transactions"], "evidence": {}})

    multi_hop_group = []
    for path in multi_hop(limit=group_limit, session=session):
        multi_hop_group.append({"entityType": "MULTI_HOP", "entityId": path["transactions"][0]["transactionId"],
                                "riskReason": path["riskReason"], "connectedEntities": path["clientIds"],
                                "relevantTransactions": path["transactions"], "evidence": {}})

    # Round-robin the signal groups so common transaction flags can't crowd out
    # the graph-structure alerts in the response.
    groups = [device_group, location_group, cycle_group, multi_hop_group, transaction_group]
    alerts = []
    for index in range(max(map(len, groups), default=0)):
        for group in groups:
            if index < len(group) and len(alerts) < limit:
                alerts.append(group[index])
    return alerts


# ── 1. Fraud Alerts ───────────────────────────────────────────
@router.get("/legacy-alerts", summary="Get legacy fraud-flagged transaction results")
def legacy_fraud_alerts(
    limit: int = Query(50, le=200),
    session: Session = Depends(get_session)
):
    """Returns all transactions marked is_fraud=True with sender and location."""
    result = session.run("""
        MATCH (s:Client)-[:PERFORMED]->(t:Transaction {is_fraud: true})
        OPTIONAL MATCH (t)-[:TRANSFERRED_TO]->(r:Client)
        OPTIONAL MATCH (t)-[:ORIGINATED_FROM]->(loc:Location)
        RETURN t.transaction_id as txn_id,
               t.amount as amount,
               t.fraud_score as fraud_score,
               t.timestamp as timestamp,
               t.channel as channel,
               s.client_id as sender_id,
               s.name as sender_name,
               r.client_id as receiver_id,
               r.name as receiver_name,
               loc.city as city,
               loc.country as country,
               loc.is_high_risk as high_risk_location
        ORDER BY t.fraud_score DESC
        LIMIT $limit
    """, limit=limit)
    return [dict(r) for r in result]


# ── 2. Shared Device Detection (Ring Fraud) ───────────────────
@router.get("/shared-device", summary="Detect clients sharing the same device")
def shared_device_fraud(
    min_clients: int = Query(2, description="Minimum clients sharing a device"),
    session: Session = Depends(get_session)
):
    """
    Finds devices used by multiple clients — a key fraud ring signal.
    Graph pattern: (Client1)-[:USED_DEVICE]->(Device)<-[:USED_DEVICE]-(Client2)
    """
    result = session.run("""
        MATCH (c1:Client)-[:USED_DEVICE]->(d:Device)<-[:USED_DEVICE]-(c2:Client)
        WHERE c1.client_id < c2.client_id
        WITH d, collect(DISTINCT c1) + collect(DISTINCT c2) as clients
        WHERE size(clients) >= $min_clients
        RETURN d.device_id as device_id,
               d.ip_address as ip_address,
               d.device_type as device_type,
               d.is_suspicious as is_suspicious,
               size(clients) as shared_by_count,
               [c IN clients | c.client_id] as client_ids,
               [c IN clients | c.name] as client_names,
               [c IN clients | c.is_flagged] as flagged_status
        ORDER BY shared_by_count DESC
    """, min_clients=min_clients)
    rows = [dict(r) for r in result]
    return {
        "fraud_type": "shared_device",
        "description": "Multiple clients using the same device — indicates fraud ring",
        "count": len(rows),
        "results": rows
    }


# ── 3. Velocity Fraud ─────────────────────────────────────────
@router.get("/velocity", summary="Detect high-frequency transaction bursts")
def velocity_fraud(
    time_window_hours: int = Query(2, description="Time window in hours"),
    min_txn_count: int = Query(5, description="Minimum transactions in window"),
    session: Session = Depends(get_session)
):
    """
    Clients who performed many transactions in a short window.
    Graph pattern: (Client)-[:PERFORMED]->(Transaction)  [grouped by time window]
    """
    result = session.run("""
        MATCH (c:Client)-[:PERFORMED]->(t:Transaction)
        WHERE (t.timestamp IS NOT NULL AND datetime(t.timestamp) >= datetime() - duration({hours: $hours}))
        WITH c, count(t) as txn_count, sum(t.amount) as total_amount,
             collect(t.transaction_id)[..5] as sample_txns
        WHERE txn_count >= $min_count
        RETURN c.client_id as client_id,
               c.name as client_name,
               c.is_flagged as is_flagged,
               c.risk_score as risk_score,
               txn_count,
               round(total_amount, 2) as total_amount,
               sample_txns
        ORDER BY txn_count DESC
    """, hours=time_window_hours, min_count=min_txn_count)
    rows = [dict(r) for r in result]
    return {
        "fraud_type": "velocity_fraud",
        "description": f"Clients with >= {min_txn_count} transactions in the last {time_window_hours}h",
        "count": len(rows),
        "results": rows
    }


# ── 4. Money Cycle Detection ──────────────────────────────────
@router.get("/legacy-cycles", summary="Detect legacy money-cycle results")
def legacy_cycle_detection(session: Session = Depends(get_session)):
    """
    Detects circular money flows — a classic layering/structuring fraud pattern.
    Graph pattern: (A)-[:PERFORMED]->(:Transaction)-[:TRANSFERRED_TO]->(B)-...→(A)
    """
    result = session.run("""
        MATCH path = (c1:Client)-[:PERFORMED]->(:Transaction)-[:TRANSFERRED_TO]->
                     (c2:Client)-[:PERFORMED]->(:Transaction)-[:TRANSFERRED_TO]->
                     (c3:Client)-[:PERFORMED]->(:Transaction)-[:TRANSFERRED_TO]->(c1)
        WHERE c1.client_id <> c2.client_id
          AND c2.client_id <> c3.client_id
          AND c1.client_id <> c3.client_id
        RETURN DISTINCT
               c1.client_id as node1, c1.name as name1,
               c2.client_id as node2, c2.name as name2,
               c3.client_id as node3, c3.name as name3
        LIMIT 20
    """)
    rows = [dict(r) for r in result]
    return {
        "fraud_type": "money_cycle",
        "description": "3-hop circular money flows (A→B→C→A) — classic layering pattern",
        "count": len(rows),
        "results": rows
    }


# ── 5. High-Risk Location Transactions ───────────────────────
@router.get("/high-risk-locations", summary="Transactions from high-risk countries")
def high_risk_location_fraud(session: Session = Depends(get_session)):
    """Finds transactions originating from flagged high-risk locations."""
    result = session.run("""
        MATCH (t:Transaction)-[:ORIGINATED_FROM]->(l:Location {is_high_risk: true})
        MATCH (s:Client)-[:PERFORMED]->(t)
        OPTIONAL MATCH (t)-[:TRANSFERRED_TO]->(r:Client)
        RETURN l.city as city, l.country as country,
               count(t) as transaction_count,
               round(sum(t.amount), 2) as total_amount,
               sum(CASE WHEN t.is_fraud THEN 1 ELSE 0 END) as fraud_count,
               collect(DISTINCT s.client_id)[..5] as sample_senders
        ORDER BY transaction_count DESC
    """)
    rows = [dict(r) for r in result]
    return {
        "fraud_type": "geo_anomaly",
        "description": "Transactions from high-risk countries",
        "count": len(rows),
        "results": rows
    }


# ── 6. Explainable Risk Score ─────────────────────────────────
@router.get("/risk-score/{client_id}", summary="Legacy path for the Graph-Based Risk Score", include_in_schema=False)
def client_risk_score(client_id: str, session: Session = Depends(get_session)):
    from fastapi import HTTPException
    from app.services.risk_scoring import score_clients

    scores = score_clients(session, client_id)
    if not scores:
        raise HTTPException(status_code=404, detail=f"Client {client_id} not found")
    return scores[0]

# ── 7. Fraud Summary ──────────────────────────────────────────
@router.get("/summary", summary="Platform-wide fraud summary")
def fraud_summary(session: Session = Depends(get_session)):
    """Returns a dashboard-ready fraud summary."""
    r = session.run("""
        MATCH (t:Transaction)
        WITH count(t) as total_txns,
             sum(CASE WHEN t.is_fraud THEN 1 ELSE 0 END) as fraud_txns,
             round(sum(CASE WHEN t.is_fraud THEN t.amount ELSE 0 END), 2) as fraud_volume,
             round(sum(t.amount), 2) as total_volume

        MATCH (c:Client)
        WITH total_txns, fraud_txns, fraud_volume, total_volume,
             count(c) as total_clients,
             sum(CASE WHEN c.is_flagged THEN 1 ELSE 0 END) as flagged_clients

        MATCH (d:Device)
        WITH total_txns, fraud_txns, fraud_volume, total_volume,
             total_clients, flagged_clients,
             sum(CASE WHEN d.is_suspicious THEN 1 ELSE 0 END) as suspicious_devices

        RETURN total_txns, fraud_txns, fraud_volume, total_volume,
               total_clients, flagged_clients, suspicious_devices,
               round(toFloat(fraud_txns)/total_txns*100, 2) as fraud_rate_pct
    """).single()
    return dict(r)
