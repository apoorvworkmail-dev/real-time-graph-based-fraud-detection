"""
Phase 8 — Leakage-Safe Graph Feature Engineering.
Extracts topological graph features and behavioral metrics for financial accounts
and transactions while strictly preventing target leakage:
  - NEVER includes ground truth labels: is_flagged, is_fraud, fraud_score, scenario
  - Only uses structural topology and historical operational statistics
"""

from typing import Any, Dict, List, Optional
import math
from datetime import datetime

# Documented feature definitions available at prediction time
CLIENT_FEATURE_NAMES = [
    "out_degree",               # Count of outgoing transactions initiated by this account
    "in_degree",                # Count of incoming transfers received by this account
    "total_out_volume",         # Total monetary sum transferred out
    "total_in_volume",          # Total monetary sum transferred in
    "net_flow",                 # Net monetary balance flow (incoming - outgoing)
    "avg_out_amount",           # Average amount per outgoing transaction
    "max_out_amount",           # Peak outgoing transaction amount
    "unique_receivers",         # Distinct recipient accounts
    "unique_senders",           # Distinct sender accounts
    "counterparty_ratio",       # Ratio of distinct counterparties to total transaction count
    "device_count",             # Number of unique devices used
    "shared_device_count",      # Number of other accounts that share hardware with this account
    "location_count",           # Number of distinct geographical locations observed
    "high_risk_loc_tx_count",   # Number of transactions originating from high-risk locations
    "high_risk_loc_ratio",      # Proportion of transactions from high-risk jurisdictions
    "velocity_burst_count",     # Transactions concentrated in rapid burst windows
    "cycle_member",             # Graph topological flag: member of a directed closed transfer loop
]

TRANSACTION_FEATURE_NAMES = [
    "amount",                   # Transaction amount
    "sender_out_degree",        # Historical outgoing count of the sender
    "sender_avg_out_amount",    # Historical average transaction amount of the sender
    "amount_to_avg_ratio",      # Ratio of current amount to sender's historic average
    "device_shared_with_others",# Number of other clients using the transaction's device
    "is_location_high_risk",    # 1.0 if location is a high-risk jurisdiction, else 0.0
    "channel_is_wire",          # 1.0 if channel is wire transfer, else 0.0
    "channel_is_web",           # 1.0 if channel is web portal, else 0.0
    "channel_is_mobile",        # 1.0 if channel is mobile app, else 0.0
]


def extract_client_features_from_graph(client_id: str, graph_data: Dict[str, Any]) -> Dict[str, float]:
    """
    Extracts topological features for a client from an in-memory graph dictionary.
    Guarantees zero target leakage.
    """
    clients = graph_data.get("clients", {})
    transactions = graph_data.get("transactions", [])
    devices = graph_data.get("devices", {})
    locations = graph_data.get("locations", {})

    out_txs = [t for t in transactions if t.get("sender_id") == client_id]
    in_txs = [t for t in transactions if t.get("receiver_id") == client_id]

    out_degree = float(len(out_txs))
    in_degree = float(len(in_txs))
    total_out_volume = float(sum(t.get("amount", 0.0) for t in out_txs))
    total_in_volume = float(sum(t.get("amount", 0.0) for t in in_txs))
    net_flow = total_in_volume - total_out_volume

    avg_out_amount = total_out_volume / out_degree if out_degree > 0 else 0.0
    max_out_amount = float(max((t.get("amount", 0.0) for t in out_txs), default=0.0))

    receivers = set(t.get("receiver_id") for t in out_txs if t.get("receiver_id"))
    senders = set(t.get("sender_id") for t in in_txs if t.get("sender_id"))
    unique_receivers = float(len(receivers))
    unique_senders = float(len(senders))

    total_tx_count = out_degree + in_degree
    total_counterparties = len(receivers.union(senders))
    counterparty_ratio = float(total_counterparties / total_tx_count) if total_tx_count > 0 else 0.0

    # Device features (topological co-occurrence without fraud labels)
    client_devices = set(t.get("device_id") for t in out_txs if t.get("device_id"))
    device_count = float(len(client_devices))

    other_clients_sharing_devices = set()
    for d_id in client_devices:
        for t in transactions:
            if t.get("device_id") == d_id and t.get("sender_id") and t.get("sender_id") != client_id:
                other_clients_sharing_devices.add(t.get("sender_id"))
    shared_device_count = float(len(other_clients_sharing_devices))

    # Location features
    client_locations = set(t.get("location_id") for t in out_txs if t.get("location_id"))
    location_count = float(len(client_locations))

    high_risk_loc_ids = set(l_id for l_id, l in locations.items() if l.get("is_high_risk"))
    high_risk_tx_count = float(sum(1 for t in out_txs if t.get("location_id") in high_risk_loc_ids))
    high_risk_loc_ratio = (high_risk_tx_count / out_degree) if out_degree > 0 else 0.0

    # Velocity: count of transactions occurring within 2 hours of each other
    velocity_burst_count = 0.0
    if len(out_txs) >= 2:
        # Sort timestamps
        sorted_txs = []
        for t in out_txs:
            ts = t.get("timestamp")
            if ts:
                try:
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    sorted_txs.append(dt)
                except Exception:
                    pass
        sorted_txs.sort()
        for i in range(len(sorted_txs) - 1):
            diff_hours = (sorted_txs[i + 1] - sorted_txs[i]).total_seconds() / 3600.0
            if diff_hours <= 2.0:
                velocity_burst_count += 1.0

    # Directed Cycle participation: A -> B -> C -> A
    cycle_member = 0.0
    for r1 in receivers:
        r1_out_txs = [t for t in transactions if t.get("sender_id") == r1]
        r1_receivers = set(t.get("receiver_id") for t in r1_out_txs if t.get("receiver_id"))
        for r2 in r1_receivers:
            if r2 == client_id:
                cycle_member = 1.0
                break
            r2_out_txs = [t for t in transactions if t.get("sender_id") == r2]
            r2_receivers = set(t.get("receiver_id") for t in r2_out_txs if t.get("receiver_id"))
            if client_id in r2_receivers:
                cycle_member = 1.0
                break
        if cycle_member > 0:
            break

    return {
        "out_degree": out_degree,
        "in_degree": in_degree,
        "total_out_volume": total_out_volume,
        "total_in_volume": total_in_volume,
        "net_flow": net_flow,
        "avg_out_amount": avg_out_amount,
        "max_out_amount": max_out_amount,
        "unique_receivers": unique_receivers,
        "unique_senders": unique_senders,
        "counterparty_ratio": counterparty_ratio,
        "device_count": device_count,
        "shared_device_count": shared_device_count,
        "location_count": location_count,
        "high_risk_loc_tx_count": high_risk_tx_count,
        "high_risk_loc_ratio": high_risk_loc_ratio,
        "velocity_burst_count": velocity_burst_count,
        "cycle_member": cycle_member,
    }


def extract_client_features_from_session(client_id: str, session) -> Dict[str, float]:
    """
    Extracts topological features for a client by executing parameterized Cypher queries in Neo4j.
    """
    cypher = """
    MATCH (c:Client {client_id: $cid})
    OPTIONAL MATCH (c)-[:PERFORMED]->(out_t:Transaction)
    OPTIONAL MATCH (out_t)-[:TRANSFERRED_TO]->(rec:Client)
    OPTIONAL MATCH (out_t)-[:ORIGINATED_FROM]->(out_l:Location)
    OPTIONAL MATCH (c)-[:USED_DEVICE]->(d:Device)
    OPTIONAL MATCH (other_c:Client)-[:USED_DEVICE]->(d) WHERE other_c <> c
    OPTIONAL MATCH (in_t:Transaction)-[:TRANSFERRED_TO]->(c)
    OPTIONAL MATCH (snd:Client)-[:PERFORMED]->(in_t)
    RETURN
        count(DISTINCT out_t) AS out_degree,
        count(DISTINCT in_t) AS in_degree,
        coalesce(sum(out_t.amount), 0.0) AS total_out_volume,
        coalesce(sum(in_t.amount), 0.0) AS total_in_volume,
        coalesce(avg(out_t.amount), 0.0) AS avg_out_amount,
        coalesce(max(out_t.amount), 0.0) AS max_out_amount,
        count(DISTINCT rec) AS unique_receivers,
        count(DISTINCT snd) AS unique_senders,
        count(DISTINCT d) AS device_count,
        count(DISTINCT other_c) AS shared_device_count,
        count(DISTINCT out_l) AS location_count,
        count(DISTINCT CASE WHEN coalesce(out_l.is_high_risk, false) THEN out_t END) AS high_risk_loc_tx_count
    """
    record = session.run(cypher, cid=client_id).single()
    if not record:
        return {feat: 0.0 for feat in CLIENT_FEATURE_NAMES}

    d = dict(record)
    out_degree = float(d.get("out_degree") or 0.0)
    in_degree = float(d.get("in_degree") or 0.0)
    total_out = float(d.get("total_out_volume") or 0.0)
    total_in = float(d.get("total_in_volume") or 0.0)
    net_flow = total_in - total_out
    avg_out = float(d.get("avg_out_amount") or 0.0)
    max_out = float(d.get("max_out_amount") or 0.0)
    uniq_rec = float(d.get("unique_receivers") or 0.0)
    uniq_snd = float(d.get("unique_senders") or 0.0)
    tot_tx = out_degree + in_degree
    counterparty_ratio = float((uniq_rec + uniq_snd) / tot_tx) if tot_tx > 0 else 0.0
    dev_count = float(d.get("device_count") or 0.0)
    shared_dev = float(d.get("shared_device_count") or 0.0)
    loc_count = float(d.get("location_count") or 0.0)
    high_risk_tx = float(d.get("high_risk_loc_tx_count") or 0.0)
    high_risk_ratio = float(high_risk_tx / out_degree) if out_degree > 0 else 0.0

    # Velocity and cycle checks
    vel_rec = session.run("""
        MATCH (c:Client {client_id: $cid})-[:PERFORMED]->(t:Transaction)
        WHERE t.timestamp IS NOT NULL AND datetime(t.timestamp) >= datetime() - duration({hours: 2})
        RETURN count(DISTINCT t) AS velocity_burst
    """, cid=client_id).single()
    velocity_burst = float(vel_rec["velocity_burst"] if vel_rec else 0.0)

    cyc_rec = session.run("""
        MATCH (c:Client {client_id: $cid})-[:PERFORMED]->(:Transaction)-[:TRANSFERRED_TO]->(b:Client)
              -[:PERFORMED]->(:Transaction)-[:TRANSFERRED_TO]->(mid:Client)
              -[:PERFORMED]->(:Transaction)-[:TRANSFERRED_TO]->(c)
        RETURN count(*) AS cycle_cnt
    """, cid=client_id).single()
    cycle_member = 1.0 if (cyc_rec and cyc_rec["cycle_cnt"] > 0) else 0.0

    return {
        "out_degree": out_degree,
        "in_degree": in_degree,
        "total_out_volume": total_out,
        "total_in_volume": total_in,
        "net_flow": net_flow,
        "avg_out_amount": avg_out,
        "max_out_amount": max_out,
        "unique_receivers": uniq_rec,
        "unique_senders": uniq_snd,
        "counterparty_ratio": counterparty_ratio,
        "device_count": dev_count,
        "shared_device_count": shared_dev,
        "location_count": loc_count,
        "high_risk_loc_tx_count": high_risk_tx,
        "high_risk_loc_ratio": high_risk_ratio,
        "velocity_burst_count": velocity_burst,
        "cycle_member": cycle_member,
    }
