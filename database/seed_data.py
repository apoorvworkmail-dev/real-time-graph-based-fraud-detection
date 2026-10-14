"""
Phase 3 — Realistic synthetic fraud dataset
Seeds Neo4j with:
 - 60 Clients (10 flagged fraudsters)
 - 20 Devices (some shared between clients = ring signal)
 - 15 Locations
 - 200 Transactions (with fraud scenarios)

Fraud scenarios:
 1. Ring fraud — multiple clients share 1-2 devices
 2. Velocity fraud — same client does many txns in short window
 3. Geo anomaly — transaction from far-away location
 4. Cycle — A→B→C→A money chain
 5. Large amount sudden spike
"""
import sys, os, random, uuid
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
from neo4j import GraphDatabase

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "fraud2024pass")

random.seed(42)

# ── Helpers ───────────────────────────────────────────────────
def uid(): return str(uuid.uuid4())[:8].upper()
def ts(days_ago=0, hours_ago=0, minutes_ago=0):
    dt = datetime.utcnow() - timedelta(days=days_ago, hours=hours_ago, minutes=minutes_ago)
    return dt.isoformat() + "Z"

# ── Data Definitions ──────────────────────────────────────────
LOCATIONS = [
    {"location_id": "LOC001", "city": "Mumbai",    "country": "India",   "latitude": 19.0760, "longitude": 72.8777, "is_high_risk": False},
    {"location_id": "LOC002", "city": "Delhi",     "country": "India",   "latitude": 28.6139, "longitude": 77.2090, "is_high_risk": False},
    {"location_id": "LOC003", "city": "Bangalore", "country": "India",   "latitude": 12.9716, "longitude": 77.5946, "is_high_risk": False},
    {"location_id": "LOC004", "city": "Chennai",   "country": "India",   "latitude": 13.0827, "longitude": 80.2707, "is_high_risk": False},
    {"location_id": "LOC005", "city": "Hyderabad", "country": "India",   "latitude": 17.3850, "longitude": 78.4867, "is_high_risk": False},
    {"location_id": "LOC006", "city": "Lagos",     "country": "Nigeria", "latitude": 6.5244,  "longitude": 3.3792,  "is_high_risk": True},
    {"location_id": "LOC007", "city": "Accra",     "country": "Ghana",   "latitude": 5.6037,  "longitude": -0.1870, "is_high_risk": True},
    {"location_id": "LOC008", "city": "Dubai",     "country": "UAE",     "latitude": 25.2048, "longitude": 55.2708, "is_high_risk": False},
    {"location_id": "LOC009", "city": "Singapore", "country": "Singapore","latitude": 1.3521, "longitude": 103.8198,"is_high_risk": False},
    {"location_id": "LOC010", "city": "Colombo",   "country": "Sri Lanka","latitude": 6.9271, "longitude": 79.8612, "is_high_risk": False},
    {"location_id": "LOC011", "city": "Dhaka",     "country": "Bangladesh","latitude": 23.8103,"longitude": 90.4125,"is_high_risk": False},
    {"location_id": "LOC012", "city": "Moscow",    "country": "Russia",  "latitude": 55.7558, "longitude": 37.6173, "is_high_risk": True},
    {"location_id": "LOC013", "city": "Nairobi",   "country": "Kenya",   "latitude": -1.2921, "longitude": 36.8219, "is_high_risk": True},
    {"location_id": "LOC014", "city": "Pune",      "country": "India",   "latitude": 18.5204, "longitude": 73.8567, "is_high_risk": False},
    {"location_id": "LOC015", "city": "Kolkata",   "country": "India",   "latitude": 22.5726, "longitude": 88.3639, "is_high_risk": False},
]

DEVICES = [
    # Normal devices
    {"device_id": "DEV001", "device_type": "mobile",  "os": "Android", "ip_address": "192.168.1.10", "is_suspicious": False},
    {"device_id": "DEV002", "device_type": "mobile",  "os": "iOS",     "ip_address": "192.168.1.11", "is_suspicious": False},
    {"device_id": "DEV003", "device_type": "desktop", "os": "Windows", "ip_address": "10.0.0.5",    "is_suspicious": False},
    {"device_id": "DEV004", "device_type": "tablet",  "os": "Android", "ip_address": "10.0.0.6",    "is_suspicious": False},
    {"device_id": "DEV005", "device_type": "mobile",  "os": "iOS",     "ip_address": "172.16.0.1",  "is_suspicious": False},
    {"device_id": "DEV006", "device_type": "mobile",  "os": "Android", "ip_address": "172.16.0.2",  "is_suspicious": False},
    {"device_id": "DEV007", "device_type": "desktop", "os": "Linux",   "ip_address": "192.168.2.1",  "is_suspicious": False},
    {"device_id": "DEV008", "device_type": "mobile",  "os": "iOS",     "ip_address": "192.168.2.2",  "is_suspicious": False},
    {"device_id": "DEV009", "device_type": "tablet",  "os": "Windows", "ip_address": "10.1.0.1",    "is_suspicious": False},
    {"device_id": "DEV010", "device_type": "mobile",  "os": "Android", "ip_address": "10.1.0.2",    "is_suspicious": False},
    # Shared/suspicious devices (fraud ring signals)
    {"device_id": "DEV011", "device_type": "mobile",  "os": "Android", "ip_address": "45.33.32.156", "is_suspicious": True},
    {"device_id": "DEV012", "device_type": "desktop", "os": "Windows", "ip_address": "45.33.32.157", "is_suspicious": True},
    {"device_id": "DEV013", "device_type": "mobile",  "os": "iOS",     "ip_address": "104.21.14.100","is_suspicious": True},
    {"device_id": "DEV014", "device_type": "tablet",  "os": "Android", "ip_address": "104.21.14.101","is_suspicious": True},
    {"device_id": "DEV015", "device_type": "mobile",  "os": "Android", "ip_address": "198.51.100.1", "is_suspicious": True},
    # VPN/proxy IPs
    {"device_id": "DEV016", "device_type": "desktop", "os": "Linux",   "ip_address": "185.220.101.1","is_suspicious": True},
    {"device_id": "DEV017", "device_type": "mobile",  "os": "Android", "ip_address": "185.220.101.2","is_suspicious": True},
    {"device_id": "DEV018", "device_type": "mobile",  "os": "iOS",     "ip_address": "192.168.5.1",  "is_suspicious": False},
    {"device_id": "DEV019", "device_type": "desktop", "os": "Mac",     "ip_address": "192.168.5.2",  "is_suspicious": False},
    {"device_id": "DEV020", "device_type": "tablet",  "os": "iOS",     "ip_address": "10.2.0.1",    "is_suspicious": False},
]

NAMES = [
    "Aarav Shah","Priya Patel","Rohit Kumar","Ananya Singh","Vijay Mehta",
    "Neha Gupta","Ravi Sharma","Pooja Verma","Arjun Nair","Sneha Reddy",
    "Amit Joshi","Kavita Rao","Suresh Iyer","Meera Pillai","Kiran Bose",
    "Deepa Malhotra","Rajesh Sinha","Sunita Tiwari","Manoj Yadav","Leela Chandra",
    "Sanjay Kapoor","Anita Mishra","Vikram Das","Rekha Menon","Dilip Saxena",
    "Geeta Bhatt","Ajay Khanna","Rina Banerjee","Sunil Aggarwal","Poonam Dubey",
    # Fraudsters (indices 30-39)
    "Fraud Actor A","Fraud Actor B","Fraud Actor C","Fraud Actor D","Fraud Actor E",
    "Shell Corp X1","Shell Corp X2","Shell Corp X3","Mule Account M1","Mule Account M2",
    # More legitimate
    "Harish Naidu","Shyam Tata","Bindu Agarwal","Venkat Swamy","Lalita Prasad",
    "Gopal Hegde","Usha Krishnan","Tarun Bajaj","Pallavi Jain","Ramesh Ghosh",
    "Nandini Choudhury","Ajit Pandey","Suman Dey","Kartik Balasubramanian","Preethi Raghavan",
    "Dinesh Kulkarni","Vandana Tripathi","Bharat Solanki","Komal Rawat","Chetan Patil",
]

def make_clients():
    clients = []
    for i, name in enumerate(NAMES):
        cid = f"CLT{i+1:03d}"
        is_fraud = (30 <= i <= 39)
        clients.append({
            "client_id": cid,
            "name": name,
            "email": f"{name.lower().replace(' ','.')}.{cid.lower()}@example.com",
            "phone": f"+91-{random.randint(7000000000, 9999999999)}",
            "account_type": random.choice(["savings", "current", "business"]),
            "account_balance": round(random.uniform(1000 if is_fraud else 5000, 50000 if not is_fraud else 500000), 2),
            "risk_score": round(random.uniform(70, 99) if is_fraud else random.uniform(1, 30), 2),
            "is_flagged": is_fraud,
            "created_at": ts(days_ago=random.randint(30, 365)),
            "kyc_verified": not is_fraud,
        })
    return clients

def make_transactions(clients):
    txns = []
    legit_ids = [c["client_id"] for c in clients if not c["is_flagged"]]
    fraud_ids = [c["client_id"] for c in clients if c["is_flagged"]]
    all_ids   = [c["client_id"] for c in clients]

    # 130 normal transactions
    for i in range(130):
        sender = random.choice(legit_ids)
        receiver = random.choice([c for c in legit_ids if c != sender])
        txns.append({
            "transaction_id": f"TXN{i+1:04d}",
            "amount": round(random.uniform(100, 15000), 2),
            "currency": "INR",
            "timestamp": ts(days_ago=random.randint(0, 30), hours_ago=random.randint(0, 23)),
            "status": random.choices(["completed","failed","pending"], weights=[85,10,5])[0],
            "transaction_type": random.choice(["transfer","payment","withdrawal","deposit"]),
            "is_fraud": False,
            "fraud_score": round(random.uniform(0, 20), 2),
            "channel": random.choice(["mobile_app","web","upi","atm"]),
            "sender_id": sender,
            "receiver_id": receiver,
            "device_id": random.choice([d["device_id"] for d in DEVICES[:10]]),
            "location_id": random.choice(["LOC001","LOC002","LOC003","LOC004","LOC005","LOC014","LOC015"]),
        })

    # 30 velocity fraud — same fraudster, rapid transactions
    velocity_actor = fraud_ids[0]  # CLT031
    for i in range(30):
        receiver = random.choice(legit_ids)
        txns.append({
            "transaction_id": f"TXN{130+i+1:04d}",
            "amount": round(random.uniform(9500, 10000), 2),  # just under limit
            "currency": "INR",
            "timestamp": ts(hours_ago=random.randint(0, 2), minutes_ago=random.randint(0, 59)),
            "status": "completed",
            "transaction_type": "transfer",
            "is_fraud": True,
            "fraud_score": round(random.uniform(75, 95), 2),
            "channel": "mobile_app",
            "sender_id": velocity_actor,
            "receiver_id": receiver,
            "device_id": "DEV011",  # suspicious shared device
            "location_id": "LOC006",  # Lagos (high risk)
        })

    # 20 ring fraud — CLT032,CLT033,CLT034 cycling money
    ring = ["CLT032", "CLT033", "CLT034"]
    for i in range(20):
        s = ring[i % 3]
        r = ring[(i + 1) % 3]
        txns.append({
            "transaction_id": f"TXN{160+i+1:04d}",
            "amount": round(random.uniform(50000, 200000), 2),
            "currency": "INR",
            "timestamp": ts(days_ago=random.randint(1, 7), hours_ago=random.randint(0, 23)),
            "status": "completed",
            "transaction_type": "transfer",
            "is_fraud": True,
            "fraud_score": round(random.uniform(80, 98), 2),
            "channel": "web",
            "sender_id": s,
            "receiver_id": r,
            "device_id": random.choice(["DEV012", "DEV013"]),  # shared suspicious devices
            "location_id": random.choice(["LOC012", "LOC013"]),  # Russia/Kenya
        })

    # 20 geo-anomaly fraud — impossible travel
    geo_actor = fraud_ids[4]  # CLT035
    for i in range(20):
        receiver = random.choice(legit_ids)
        txns.append({
            "transaction_id": f"TXN{180+i+1:04d}",
            "amount": round(random.uniform(5000, 50000), 2),
            "currency": "INR",
            "timestamp": ts(days_ago=random.randint(0, 5), hours_ago=random.randint(0, 6)),
            "status": "completed",
            "transaction_type": "transfer",
            "is_fraud": True,
            "fraud_score": round(random.uniform(65, 90), 2),
            "channel": random.choice(["mobile_app","web"]),
            "sender_id": geo_actor,
            "receiver_id": receiver,
            "device_id": random.choice(["DEV015","DEV016","DEV017"]),
            "location_id": random.choice(["LOC006","LOC007","LOC012","LOC013"]),  # all high-risk
        })

    return txns


# ── Seed Functions ────────────────────────────────────────────
def clear_database(session):
    session.run("MATCH (n) DETACH DELETE n")
    print("🗑️  Cleared existing data")

def seed_locations(session, locations):
    for loc in locations:
        session.run("""
            MERGE (l:Location {location_id: $location_id})
            SET l += $props
        """, location_id=loc["location_id"], props=loc)
    print(f"✅ Seeded {len(locations)} locations")

def seed_devices(session, devices):
    for dev in devices:
        session.run("""
            MERGE (d:Device {device_id: $device_id})
            SET d += $props
        """, device_id=dev["device_id"], props=dev)
    print(f"✅ Seeded {len(devices)} devices")

def seed_clients(session, clients):
    for cli in clients:
        session.run("""
            MERGE (c:Client {client_id: $client_id})
            SET c += $props
        """, client_id=cli["client_id"], props=cli)
    print(f"✅ Seeded {len(clients)} clients")

def seed_transactions(session, transactions):
    for txn in transactions:
        sender_id  = txn.pop("sender_id")
        receiver_id = txn.pop("receiver_id")
        device_id  = txn.pop("device_id")
        location_id = txn.pop("location_id")
        session.run("""
            MATCH (sender:Client {client_id: $sender_id})
            MATCH (receiver:Client {client_id: $receiver_id})
            MATCH (device:Device {device_id: $device_id})
            MATCH (loc:Location {location_id: $location_id})
            MERGE (t:Transaction {transaction_id: $props.transaction_id})
            SET t += $props
            MERGE (sender)-[:PERFORMED]->(t)
            MERGE (t)-[:TRANSFERRED_TO]->(receiver)
            MERGE (sender)-[:USED_DEVICE]->(device)
            MERGE (t)-[:ORIGINATED_FROM]->(loc)
        """, sender_id=sender_id, receiver_id=receiver_id,
             device_id=device_id, location_id=location_id, props=txn)
    print(f"✅ Seeded {len(transactions)} transactions with relationships")

def verify_seed(session):
    stats = {}
    for label in ["Client","Transaction","Device","Location"]:
        count = session.run(f"MATCH (n:{label}) RETURN count(n) as c").single()["c"]
        stats[label] = count
    rel_count = session.run("MATCH ()-[r]->() RETURN count(r) as c").single()["c"]
    stats["Relationships"] = rel_count
    fraud_txns = session.run("MATCH (t:Transaction {is_fraud:true}) RETURN count(t) as c").single()["c"]
    stats["FraudTransactions"] = fraud_txns
    return stats

def main():
    print(f"Connecting to Neo4j at {NEO4J_URI}...")
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        driver.verify_connectivity()
        print("✅ Connected to Neo4j\n")
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        sys.exit(1)

    clients = make_clients()
    transactions = make_transactions(clients)

    with driver.session() as session:
        clear_database(session)
        seed_locations(session, LOCATIONS)
        seed_devices(session, DEVICES)
        seed_clients(session, clients)
        seed_transactions(session, transactions)

        stats = verify_seed(session)

    print("\n📊 Database Stats After Seeding:")
    for k, v in stats.items():
        print(f"  {k:25s}: {v}")
    print("\n✅ Dataset seeded successfully!")
    driver.close()

if __name__ == "__main__":
    main()
