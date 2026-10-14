"""
Phase 2 — Apply Neo4j schema: constraints + indexes
Run: python database/apply_schema.py
"""
import sys
import os

# Allow running from project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from neo4j import GraphDatabase

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "fraud2024pass")

SCHEMA_STATEMENTS = [
    # ── Uniqueness Constraints ──────────────────────────────────
    "CREATE CONSTRAINT client_id_unique IF NOT EXISTS FOR (c:Client) REQUIRE c.client_id IS UNIQUE",
    "CREATE CONSTRAINT transaction_id_unique IF NOT EXISTS FOR (t:Transaction) REQUIRE t.transaction_id IS UNIQUE",
    "CREATE CONSTRAINT device_id_unique IF NOT EXISTS FOR (d:Device) REQUIRE d.device_id IS UNIQUE",
    "CREATE CONSTRAINT location_id_unique IF NOT EXISTS FOR (l:Location) REQUIRE l.location_id IS UNIQUE",
    "CREATE CONSTRAINT location_ip_unique IF NOT EXISTS FOR (l:Location) REQUIRE l.ip_address IS UNIQUE",

    # ── Indexes ─────────────────────────────────────────────────
    "CREATE INDEX client_email_idx IF NOT EXISTS FOR (c:Client) ON (c.email)",
    "CREATE INDEX client_risk_idx IF NOT EXISTS FOR (c:Client) ON (c.risk_score)",
    "CREATE INDEX transaction_amount_idx IF NOT EXISTS FOR (t:Transaction) ON (t.amount)",
    "CREATE INDEX transaction_timestamp_idx IF NOT EXISTS FOR (t:Transaction) ON (t.timestamp)",
    "CREATE INDEX transaction_status_idx IF NOT EXISTS FOR (t:Transaction) ON (t.status)",
    "CREATE INDEX transaction_is_fraud_idx IF NOT EXISTS FOR (t:Transaction) ON (t.is_fraud)",
    "CREATE INDEX device_ip_idx IF NOT EXISTS FOR (d:Device) ON (d.ip_address)",
    "CREATE INDEX location_country_idx IF NOT EXISTS FOR (l:Location) ON (l.country)",

    # ── Phase 9: Case Management Constraints & Indexes ───────────
    "CREATE CONSTRAINT case_id_unique IF NOT EXISTS FOR (c:FraudCase) REQUIRE c.case_id IS UNIQUE",
    "CREATE INDEX case_status_idx IF NOT EXISTS FOR (c:FraudCase) ON (c.status)",
    "CREATE INDEX case_priority_idx IF NOT EXISTS FOR (c:FraudCase) ON (c.priority)",
    "CREATE INDEX case_entity_idx IF NOT EXISTS FOR (c:FraudCase) ON (c.entity_id)",
]


def apply_schema():
    print(f"Connecting to Neo4j at {NEO4J_URI}...")
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    try:
        driver.verify_connectivity()
        print("✅ Connected to Neo4j")
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        sys.exit(1)

    with driver.session() as session:
        for stmt in SCHEMA_STATEMENTS:
            try:
                session.run(stmt)
                label = stmt.split("IF NOT EXISTS")[0].strip().replace("CREATE ", "")
                print(f"  ✅ Applied: {label}")
            except Exception as e:
                print(f"  ⚠️  {stmt[:60]}... → {e}")

        # Verify
        constraints = session.run("SHOW CONSTRAINTS").data()
        indexes = session.run("SHOW INDEXES WHERE type <> 'LOOKUP'").data()
        print(f"\n📊 Schema Summary:")
        print(f"  Constraints : {len(constraints)}")
        print(f"  Custom Idx  : {len(indexes)}")
        for c in constraints:
            print(f"    CONSTRAINT {c.get('name')} ON {c.get('labelsOrTypes')} ({c.get('properties')})")
        for i in indexes:
            print(f"    INDEX {i.get('name')} ON {i.get('labelsOrTypes')} ({i.get('properties')})")

    driver.close()
    print("\n✅ Schema applied successfully!")


if __name__ == "__main__":
    apply_schema()
