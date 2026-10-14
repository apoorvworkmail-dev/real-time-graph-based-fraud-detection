"""
Database Export Script — Generates reproducible Cypher dump
Exports constraints, indexes, and synthetic nodes & relationships into database/dump/fraud_detection_export.cypher
"""
import os
import sys

# Add project root and backend directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from database.seed_data import LOCATIONS, DEVICES, make_clients, make_transactions

def generate_cypher_export(output_path: str):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    clients = make_clients()
    transactions = make_transactions(clients)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("// ============================================================\n")
        f.write("// Neo4j Reproducible Export — Financial Fraud Detection Platform\n")
        f.write("// B.Tech CSE NoSQL Project — Review 2\n")
        f.write("// ============================================================\n\n")

        # Constraints
        f.write("// ── Schema Constraints ──────────────────────────────────────\n")
        f.write("CREATE CONSTRAINT client_id_unique IF NOT EXISTS FOR (c:Client) REQUIRE c.client_id IS UNIQUE;\n")
        f.write("CREATE CONSTRAINT transaction_id_unique IF NOT EXISTS FOR (t:Transaction) REQUIRE t.transaction_id IS UNIQUE;\n")
        f.write("CREATE CONSTRAINT device_id_unique IF NOT EXISTS FOR (d:Device) REQUIRE d.device_id IS UNIQUE;\n")
        f.write("CREATE CONSTRAINT location_id_unique IF NOT EXISTS FOR (l:Location) REQUIRE l.location_id IS UNIQUE;\n\n")

        # Indexes
        f.write("// ── Schema Indexes ──────────────────────────────────────────\n")
        f.write("CREATE INDEX client_email_idx IF NOT EXISTS FOR (c:Client) ON (c.email);\n")
        f.write("CREATE INDEX client_risk_idx IF NOT EXISTS FOR (c:Client) ON (c.risk_score);\n")
        f.write("CREATE INDEX transaction_amount_idx IF NOT EXISTS FOR (t:Transaction) ON (t.amount);\n")
        f.write("CREATE INDEX transaction_timestamp_idx IF NOT EXISTS FOR (t:Transaction) ON (t.timestamp);\n")
        f.write("CREATE INDEX transaction_status_idx IF NOT EXISTS FOR (t:Transaction) ON (t.status);\n")
        f.write("CREATE INDEX transaction_is_fraud_idx IF NOT EXISTS FOR (t:Transaction) ON (t.is_fraud);\n")
        f.write("CREATE INDEX device_ip_idx IF NOT EXISTS FOR (d:Device) ON (d.ip_address);\n")
        f.write("CREATE INDEX location_country_idx IF NOT EXISTS FOR (l:Location) ON (l.country);\n\n")

        # Locations
        f.write("// ── Location Nodes ──────────────────────────────────────────\n")
        for loc in LOCATIONS:
            ip_val = f"'{loc.get('ip_address')}'" if loc.get('ip_address') else "null"
            f.write(
                f"MERGE (l:Location {{location_id: '{loc['location_id']}'}}) "
                f"SET l.city = '{loc['city']}', l.country = '{loc['country']}', "
                f"l.latitude = {loc['latitude']}, l.longitude = {loc['longitude']}, "
                f"l.is_high_risk = {str(loc['is_high_risk']).lower()};\n"
            )
        f.write("\n")

        # Devices
        f.write("// ── Device Nodes ────────────────────────────────────────────\n")
        for dev in DEVICES:
            f.write(
                f"MERGE (d:Device {{device_id: '{dev['device_id']}'}}) "
                f"SET d.device_type = '{dev['device_type']}', d.os = '{dev['os']}', "
                f"d.ip_address = '{dev['ip_address']}', d.is_suspicious = {str(dev['is_suspicious']).lower()};\n"
            )
        f.write("\n")

        # Clients
        f.write("// ── Client Nodes ────────────────────────────────────────────\n")
        for cli in clients:
            f.write(
                f"MERGE (c:Client {{client_id: '{cli['client_id']}'}}) "
                f"SET c.name = '{cli['name']}', c.email = '{cli['email']}', c.phone = '{cli['phone']}', "
                f"c.account_type = '{cli['account_type']}', c.account_balance = {cli['account_balance']}, "
                f"c.risk_score = {cli['risk_score']}, c.is_flagged = {str(cli['is_flagged']).lower()}, "
                f"c.created_at = '{cli['created_at']}', c.kyc_verified = {str(cli['kyc_verified']).lower()};\n"
            )
        f.write("\n")

        # Transactions and Relationships
        f.write("// ── Transaction Nodes & Graph Relationships ─────────────────\n")
        for txn in transactions:
            tid = txn["transaction_id"]
            sid = txn["sender_id"]
            rid = txn["receiver_id"]
            did = txn["device_id"]
            lid = txn["location_id"]
            f.write(
                f"MATCH (s:Client {{client_id: '{sid}'}}), (r:Client {{client_id: '{rid}'}}), "
                f"(d:Device {{device_id: '{did}'}}), (l:Location {{location_id: '{lid}'}}) "
                f"CREATE (t:Transaction {{transaction_id: '{tid}', amount: {txn['amount']}, currency: '{txn['currency']}', "
                f"status: '{txn['status']}', transaction_type: '{txn['transaction_type']}', "
                f"is_fraud: {str(txn['is_fraud']).lower()}, fraud_score: {txn['fraud_score']}, "
                f"channel: '{txn['channel']}', timestamp: '{txn['timestamp']}'}}) "
                f"CREATE (s)-[:PERFORMED]->(t) "
                f"CREATE (t)-[:TRANSFERRED_TO]->(r) "
                f"CREATE (s)-[:USED_DEVICE]->(d) "
                f"CREATE (t)-[:ORIGINATED_FROM]->(l);\n"
            )

    print(f"Export generated successfully at: {output_path}")

if __name__ == "__main__":
    out_file = os.path.join(os.path.dirname(__file__), "dump", "fraud_detection_export.cypher")
    generate_cypher_export(out_file)
