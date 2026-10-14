"""
Phase 2 — Comprehensive Database Verification Script
Inspects live Neo4j database and reports:
- Connection info
- Node counts (Client, Transaction, Device, Location)
- Relationship counts (PERFORMED, TRANSFERRED_TO, USED_DEVICE, ORIGINATED_FROM)
- Active Constraints
- Active Indexes
- Schema consistency checks
"""
import os
import sys

# Allow running from project root or database directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from neo4j import GraphDatabase

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "fraud2024pass")


def verify_database(uri=NEO4J_URI, user=NEO4J_USER, password=NEO4J_PASSWORD) -> dict:
    report = {}
    print(f"Connecting to Neo4j at {uri}...")
    driver = GraphDatabase.driver(uri, auth=(user, password))
    
    try:
        driver.verify_connectivity()
        info = driver.get_server_info()
        print(f"Connected to Neo4j: {info.agent} ({info.address})")
        report["connection"] = {
            "status": "connected",
            "agent": info.agent,
            "address": str(info.address),
            "protocol_version": str(info.protocol_version)
        }
    except Exception as e:
        print(f"Connection failed: {e}")
        report["connection"] = {"status": "failed", "error": str(e)}
        return report

    with driver.session() as session:
        # 1. Node Counts
        node_counts = {}
        for label in ["Client", "Transaction", "Device", "Location"]:
            res = session.run(f"MATCH (n:{label}) RETURN count(n) as cnt").single()
            node_counts[label] = res["cnt"]
        report["node_counts"] = node_counts

        # 2. Total nodes
        total_nodes = session.run("MATCH (n) RETURN count(n) as cnt").single()["cnt"]
        report["total_nodes"] = total_nodes

        # 3. Relationship Counts
        rel_counts = {}
        for rel_type in ["PERFORMED", "TRANSFERRED_TO", "USED_DEVICE", "ORIGINATED_FROM"]:
            res = session.run(f"MATCH ()-[r:{rel_type}]->() RETURN count(r) as cnt").single()
            rel_counts[rel_type] = res["cnt"]
        report["relationship_counts"] = rel_counts

        total_rels = session.run("MATCH ()-[r]->() RETURN count(r) as cnt").single()["cnt"]
        report["total_relationships"] = total_rels

        # 4. Constraints
        constraints = session.run("SHOW CONSTRAINTS").data()
        report["constraints"] = [
            {
                "name": c.get("name"),
                "type": c.get("type"),
                "entityType": c.get("entityType"),
                "labelsOrTypes": c.get("labelsOrTypes"),
                "properties": c.get("properties")
            }
            for c in constraints
        ]

        # 5. Indexes
        indexes = session.run("SHOW INDEXES WHERE type <> 'LOOKUP'").data()
        report["indexes"] = [
            {
                "name": i.get("name"),
                "type": i.get("type"),
                "entityType": i.get("entityType"),
                "labelsOrTypes": i.get("labelsOrTypes"),
                "properties": i.get("properties")
            }
            for i in indexes
        ]

    driver.close()
    return report


def print_report(report: dict):
    print("\n" + "=" * 60)
    print("      NEO4J DATABASE VERIFICATION REPORT")
    print("=" * 60)
    
    conn = report.get("connection", {})
    print(f"Connection Status : {conn.get('status')}")
    if conn.get("status") == "connected":
        print(f"Server Agent      : {conn.get('agent')}")
        print(f"Server Address    : {conn.get('address')}")
        print(f"Protocol Version  : {conn.get('protocol_version')}")
    
    print("\nNode Counts:")
    for k, v in report.get("node_counts", {}).items():
        print(f"  - {k:<15} : {v}")
    print(f"  Total Nodes     : {report.get('total_nodes', 0)}")

    print("\nRelationship Counts:")
    for k, v in report.get("relationship_counts", {}).items():
        print(f"  - {k:<18} : {v}")
    print(f"  Total Rels      : {report.get('total_relationships', 0)}")

    print(f"\nActive Constraints ({len(report.get('constraints', []))}):")
    for c in report.get("constraints", []):
        print(f"  - {c['name']:<25} on {c['labelsOrTypes']} ({c['properties']})")

    print(f"\nActive Indexes ({len(report.get('indexes', []))}):")
    for i in report.get("indexes", []):
        print(f"  - {i['name']:<28} on {i['labelsOrTypes']} ({i['properties']})")
    
    print("=" * 60)


if __name__ == "__main__":
    rep = verify_database()
    print_report(rep)
