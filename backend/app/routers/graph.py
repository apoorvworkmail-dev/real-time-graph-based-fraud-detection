"""
Graph traversal and visualization endpoints
"""
from fastapi import APIRouter, Depends, Query
from neo4j import Session
from app.db.neo4j_driver import get_session
from app.auth.dependencies import require_permission

router = APIRouter(dependencies=[Depends(require_permission("graph:read"))])


@router.get("/neighbors/{client_id}", summary="Get 1-hop neighbors of a client")
def get_neighbors(
    client_id: str,
    hops: int = Query(1, ge=1, le=3),
    session: Session = Depends(get_session)
):
    """
    Returns all nodes connected to a client within N hops.
    Used for interactive graph visualization.
    """
    result = session.run(f"""
        MATCH path = (c:Client {{client_id: $cid}})-[*1..{hops}]-(neighbor)
        RETURN DISTINCT labels(neighbor) as labels,
               neighbor,
               type(relationships(path)[0]) as relationship_type,
               length(path) as hops
        LIMIT 100
    """, cid=client_id)

    nodes = []
    for r in result:
        node_data = dict(r["neighbor"])
        node_data["_labels"] = r["labels"]
        node_data["_relationship"] = r["relationship_type"]
        node_data["_hops"] = r["hops"]
        nodes.append(node_data)
    return {"client_id": client_id, "hops": hops, "neighbor_count": len(nodes), "nodes": nodes}


@router.get("/subgraph", summary="Get full graph for visualization")
def get_full_subgraph(
    limit_clients: int = Query(20, ge=1, le=50),
    session: Session = Depends(get_session)
):
    """Return a bounded, connected Neo4j subgraph with all four entity types."""
    clients = session.run("""
        MATCH (c:Client)
        RETURN c.client_id as id, c.name as label, 'Client' as type,
               c.risk_score as risk_score, c.is_flagged as is_flagged,
               c.email as email
        ORDER BY c.is_flagged DESC, c.risk_score DESC LIMIT $lim
    """, lim=limit_clients)
    client_nodes = [dict(r) for r in clients]
    client_ids = [n["id"] for n in client_nodes]
    nodes_by_id = {node["id"]: node for node in client_nodes}
    links = []

    txn_rows = session.run("""
        MATCH (sender:Client)-[:PERFORMED]->(t:Transaction)-[:TRANSFERRED_TO]->(receiver:Client)
        WHERE sender.client_id IN $client_ids OR receiver.client_id IN $client_ids
        OPTIONAL MATCH (t)-[:ORIGINATED_FROM]->(l:Location)
        RETURN sender, t, receiver, l
        ORDER BY t.timestamp DESC LIMIT $limit
    """, client_ids=client_ids, limit=limit_clients * 6)
    for row in txn_rows:
        sender, transaction, receiver, location = row["sender"], dict(row["t"]), row["receiver"], row["l"]
        sender_data = dict(sender)
        receiver_data = dict(receiver)
        for props, client in ((sender_data, sender), (receiver_data, receiver)):
            cid = client["client_id"]
            nodes_by_id.setdefault(cid, {"id": cid, "label": props.get("name", cid), "type": "Client",
                                         "risk_score": props.get("risk_score"), "is_flagged": props.get("is_flagged", False)})
        tid = transaction["transaction_id"]
        nodes_by_id[tid] = {"id": tid, "label": tid, "type": "Transaction", "amount": transaction.get("amount"),
                            "timestamp": transaction.get("timestamp"), "is_fraud": transaction.get("is_fraud", False),
                            "fraud_score": transaction.get("fraud_score"), "status": transaction.get("status")}
        links.append({"source": sender["client_id"], "target": tid, "type": "PERFORMED",
                      "is_fraud": transaction.get("is_fraud", False)})
        links.append({"source": tid, "target": receiver["client_id"], "type": "TRANSFERRED_TO",
                      "is_fraud": transaction.get("is_fraud", False)})
        if location:
            lid = location["location_id"]
            nodes_by_id[lid] = {"id": lid, "label": location.get("city", lid), "type": "Location",
                                "country": location.get("country"), "is_high_risk": location.get("is_high_risk", False)}
            links.append({"source": tid, "target": lid, "type": "ORIGINATED_FROM"})

    device_rows = session.run("""
        MATCH (c:Client)-[:USED_DEVICE]->(d:Device)
        WHERE c.client_id IN $client_ids
        RETURN c.client_id AS client_id, d.device_id AS id, d.ip_address AS label,
               d.is_suspicious AS is_suspicious, d.device_type AS device_type
    """, client_ids=client_ids)
    for row in device_rows:
        nodes_by_id[row["id"]] = {"id": row["id"], "label": row["label"] or row["id"], "type": "Device",
                                   "is_suspicious": row["is_suspicious"], "device_type": row["device_type"]}
        links.append({"source": row["client_id"], "target": row["id"], "type": "USED_DEVICE"})

    all_nodes = list(nodes_by_id.values())

    return {
        "nodes": all_nodes,
        "links": links,
        "stats": {
            "client_nodes": sum(node["type"] == "Client" for node in all_nodes),
            "transaction_nodes": sum(node["type"] == "Transaction" for node in all_nodes),
            "device_nodes": sum(node["type"] == "Device" for node in all_nodes),
            "location_nodes": sum(node["type"] == "Location" for node in all_nodes),
            "total_edges": len(links)
        }
    }


@router.get("/path", summary="Find shortest path between two clients")
def find_path(
    from_client: str,
    to_client: str,
    max_hops: int = Query(4, ge=1, le=6, description="Maximum traversal depth (1-6)"),
    session: Session = Depends(get_session)
):
    """
    Finds the shortest path between two clients through the transaction graph.
    Useful for detecting indirect associations between suspects.
    """
    safe_hops = max(1, min(int(max_hops), 6))
    query = f"""
        MATCH path = shortestPath(
            (a:Client {{client_id: $from_id}})-[*..{safe_hops}]-(b:Client {{client_id: $to_id}})
        )
        RETURN [node IN nodes(path) | {{
            labels: labels(node),
            id: CASE WHEN 'Client' IN labels(node) THEN node.client_id
                     WHEN 'Transaction' IN labels(node) THEN node.transaction_id
                     WHEN 'Device' IN labels(node) THEN node.device_id
                     ELSE node.location_id END,
            name: CASE WHEN 'Client' IN labels(node) THEN node.name
                       ELSE NULL END
        }}] as path_nodes,
        length(path) as path_length
        LIMIT 1
    """
    result = session.run(query, from_id=from_client, to_id=to_client)

    row = result.single()
    if not row:
        return {"found": False, "message": f"No path found between {from_client} and {to_client}"}
    return {
        "found": True,
        "from_client": from_client,
        "to_client": to_client,
        "path_length": row["path_length"],
        "path": row["path_nodes"]
    }
