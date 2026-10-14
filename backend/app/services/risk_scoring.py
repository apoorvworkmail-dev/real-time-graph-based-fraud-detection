"""Configurable explainable graph risk scoring (not a probability model)."""
from typing import Any

# Keep the complete weighting and calibration in this single service module.
WEIGHTS = {
    "shared_device": 20,
    "shared_location": 15,
    "multi_hop_path": 20,
    "cycle_participation": 20,
    "high_transaction_velocity": 15,
    "suspicious_connections": 10,
}
VELOCITY_WINDOW_HOURS = 2
VELOCITY_FULL_SCORE_AT = 5
SUSPICIOUS_CONNECTIONS_FULL_SCORE_AT = 3
RISK_LEVEL_THRESHOLDS = {"MEDIUM": 25, "HIGH": 50, "CRITICAL": 75}

CLIENT_FACTORS_QUERY = """
MATCH (c:Client)
WHERE $entity_id IS NULL OR c.client_id = $entity_id
CALL {
  WITH c
  OPTIONAL MATCH (c)-[:USED_DEVICE]->(d:Device)<-[:USED_DEVICE]-(other:Client)
  WHERE other <> c
  RETURN count(DISTINCT d) AS shared_device
}
CALL {
  WITH c
  OPTIONAL MATCH (c)-[:PERFORMED]->(:Transaction)-[:ORIGINATED_FROM]->(l:Location)
                 <-[:ORIGINATED_FROM]-(:Transaction)<-[:PERFORMED]-(other:Client)
  WHERE other <> c AND (coalesce(l.is_high_risk,false) OR other IS NOT NULL)
  RETURN count(DISTINCT l) AS shared_location
}
CALL {
  WITH c
  MATCH (a:Client)-[:PERFORMED]->(t1:Transaction)-[:TRANSFERRED_TO]->(b:Client)
        -[:PERFORMED]->(t2:Transaction)-[:TRANSFERRED_TO]->(middle:Client)
        -[:PERFORMED]->(t3:Transaction)-[:TRANSFERRED_TO]->(d:Client)
  WHERE c IN [a,b,middle,d]
    AND (coalesce(a.is_flagged,false) OR coalesce(b.is_flagged,false)
         OR coalesce(middle.is_flagged,false) OR coalesce(d.is_flagged,false)
         OR coalesce(t1.is_fraud,false) OR coalesce(t2.is_fraud,false) OR coalesce(t3.is_fraud,false))
  RETURN count(DISTINCT [t1.transaction_id,t2.transaction_id,t3.transaction_id]) AS multi_hop_path
}
CALL {
  WITH c
  MATCH (a:Client)-[:PERFORMED]->(t1:Transaction)-[:TRANSFERRED_TO]->(b:Client)
        -[:PERFORMED]->(t2:Transaction)-[:TRANSFERRED_TO]->(middle:Client)
        -[:PERFORMED]->(t3:Transaction)-[:TRANSFERRED_TO]->(a)
  WHERE c IN [a,b,middle]
    AND a.client_id < b.client_id AND b.client_id < middle.client_id
    AND (coalesce(a.is_flagged,false) OR coalesce(b.is_flagged,false) OR coalesce(middle.is_flagged,false)
         OR coalesce(t1.is_fraud,false) OR coalesce(t2.is_fraud,false) OR coalesce(t3.is_fraud,false))
  RETURN count(DISTINCT [t1.transaction_id,t2.transaction_id,t3.transaction_id]) AS cycle_participation
}
CALL {
  WITH c
  OPTIONAL MATCH (c)-[:PERFORMED]->(t:Transaction)
  WHERE t.timestamp IS NOT NULL AND datetime(t.timestamp) >= datetime() - duration({hours:$velocity_hours})
  RETURN count(DISTINCT t) AS high_transaction_velocity
}
CALL {
  WITH c
  OPTIONAL MATCH (c)--(neighbor)
  WHERE (neighbor:Client AND coalesce(neighbor.is_flagged,false))
     OR (neighbor:Device AND coalesce(neighbor.is_suspicious,false))
     OR (neighbor:Location AND coalesce(neighbor.is_high_risk,false))
     OR (neighbor:Transaction AND coalesce(neighbor.is_fraud,false))
  WITH c, count(DISTINCT neighbor) AS neighbor_count
  RETURN neighbor_count + CASE WHEN coalesce(c.is_flagged,false) THEN 1 ELSE 0 END AS suspicious_connections
}
RETURN c.client_id AS entityId, shared_device, shared_location, multi_hop_path,
       cycle_participation, high_transaction_velocity, suspicious_connections
"""

TRANSACTION_FACTORS_QUERY = """
MATCH (t:Transaction)
WHERE $entity_id IS NULL OR t.transaction_id = $entity_id
OPTIONAL MATCH (sender:Client)-[:PERFORMED]->(t)
CALL {
  WITH sender
  OPTIONAL MATCH (sender)-[:USED_DEVICE]->(d:Device)<-[:USED_DEVICE]-(other:Client)
  WHERE other <> sender
  RETURN count(DISTINCT d) AS shared_device
}
CALL {
  WITH t, sender
  OPTIONAL MATCH (t)-[:ORIGINATED_FROM]->(l:Location)<-[:ORIGINATED_FROM]-(other_tx:Transaction)
                 <-[:PERFORMED]-(other:Client)
  WHERE other <> sender AND (coalesce(l.is_high_risk,false) OR other IS NOT NULL)
  RETURN count(DISTINCT l) AS shared_location
}
CALL {
  WITH t
  MATCH (a:Client)-[:PERFORMED]->(t1:Transaction)-[:TRANSFERRED_TO]->(b:Client)
        -[:PERFORMED]->(t2:Transaction)-[:TRANSFERRED_TO]->(middle:Client)
        -[:PERFORMED]->(t3:Transaction)-[:TRANSFERRED_TO]->(d:Client)
  WHERE t IN [t1,t2,t3]
    AND (coalesce(a.is_flagged,false) OR coalesce(b.is_flagged,false)
         OR coalesce(middle.is_flagged,false) OR coalesce(d.is_flagged,false)
         OR coalesce(t1.is_fraud,false) OR coalesce(t2.is_fraud,false) OR coalesce(t3.is_fraud,false))
  RETURN count(DISTINCT [t1.transaction_id,t2.transaction_id,t3.transaction_id]) AS multi_hop_path
}
CALL {
  WITH t
  MATCH (a:Client)-[:PERFORMED]->(t1:Transaction)-[:TRANSFERRED_TO]->(b:Client)
        -[:PERFORMED]->(t2:Transaction)-[:TRANSFERRED_TO]->(middle:Client)
        -[:PERFORMED]->(t3:Transaction)-[:TRANSFERRED_TO]->(a)
  WHERE t IN [t1,t2,t3] AND a.client_id < b.client_id AND b.client_id < middle.client_id
    AND (coalesce(a.is_flagged,false) OR coalesce(b.is_flagged,false) OR coalesce(middle.is_flagged,false)
         OR coalesce(t1.is_fraud,false) OR coalesce(t2.is_fraud,false) OR coalesce(t3.is_fraud,false))
  RETURN count(DISTINCT [t1.transaction_id,t2.transaction_id,t3.transaction_id]) AS cycle_participation
}
CALL {
  WITH sender
  OPTIONAL MATCH (sender)-[:PERFORMED]->(recent:Transaction)
  WHERE recent.timestamp IS NOT NULL
    AND datetime(recent.timestamp) >= datetime() - duration({hours:$velocity_hours})
  RETURN count(DISTINCT recent) AS high_transaction_velocity
}
CALL {
  WITH t
  OPTIONAL MATCH (t)--(neighbor)
  WHERE (neighbor:Client AND coalesce(neighbor.is_flagged,false))
     OR (neighbor:Device AND coalesce(neighbor.is_suspicious,false))
     OR (neighbor:Location AND coalesce(neighbor.is_high_risk,false))
     OR (neighbor:Transaction AND coalesce(neighbor.is_fraud,false))
  WITH t, count(DISTINCT neighbor) AS neighbor_count
  RETURN neighbor_count + CASE WHEN coalesce(t.is_fraud,false) THEN 1 ELSE 0 END AS suspicious_connections
}
RETURN t.transaction_id AS entityId, shared_device, shared_location, multi_hop_path,
       cycle_participation, high_transaction_velocity, suspicious_connections
"""

_FACTORS = (
    ("shared_device", 1, "Shared device(s) connect this entity to other clients."),
    ("shared_location", 1, "Shared or high-risk transaction location(s) connect this entity to other clients."),
    ("multi_hop_path", 1, "Participates in a suspicious path of at least three transfers."),
    ("cycle_participation", 1, "Participates in a suspicious circular transfer path."),
    ("high_transaction_velocity", VELOCITY_FULL_SCORE_AT, "High transaction activity in the last two hours."),
    ("suspicious_connections", SUSPICIOUS_CONNECTIONS_FULL_SCORE_AT,
     "Connected to flagged clients, fraud-marked transactions, suspicious devices, or high-risk locations."),
)


def score_factors(entity_id: str, values: dict[str, Any]) -> dict[str, Any]:
    reasons = []
    total = 0.0
    for factor, saturation, description in _FACTORS:
        observed = int(values.get(factor) or 0)
        if observed <= 0:
            continue
        weight = WEIGHTS[factor]
        contribution = round(weight * min(observed / saturation, 1.0), 2)
        total += contribution
        reasons.append({"factor": factor, "observed": observed, "weight": weight,
                        "contribution": contribution, "explanation": description})
    score = round(min(total, 100.0), 2)
    if score >= RISK_LEVEL_THRESHOLDS["CRITICAL"]:
        level = "CRITICAL"
    elif score >= RISK_LEVEL_THRESHOLDS["HIGH"]:
        level = "HIGH"
    elif score >= RISK_LEVEL_THRESHOLDS["MEDIUM"]:
        level = "MEDIUM"
    else:
        level = "LOW"
    return {"scoreName": "Graph-Based Risk Score", "entityId": entity_id,
            "riskScore": score, "riskLevel": level, "reasons": reasons}


def score_clients(session, entity_id: str | None = None) -> list[dict[str, Any]]:
    records = session.run(CLIENT_FACTORS_QUERY, entity_id=entity_id,
                          velocity_hours=VELOCITY_WINDOW_HOURS)
    return [score_factors(record["entityId"], dict(record)) for record in records]


def score_transactions(session, entity_id: str | None = None) -> list[dict[str, Any]]:
    records = session.run(TRANSACTION_FACTORS_QUERY, entity_id=entity_id,
                          velocity_hours=VELOCITY_WINDOW_HOURS)
    return [score_factors(record["entityId"], dict(record)) for record in records]
