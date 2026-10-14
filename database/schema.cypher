// ============================================================
// Neo4j Schema — Fraud Detection Platform
// B.Tech CSE NoSQL Project — Review 2
// Run this AFTER Neo4j is started
// ============================================================

// ── Constraints (enforce uniqueness + existence) ─────────────

CREATE CONSTRAINT client_id_unique IF NOT EXISTS
FOR (c:Client) REQUIRE c.client_id IS UNIQUE;

CREATE CONSTRAINT transaction_id_unique IF NOT EXISTS
FOR (t:Transaction) REQUIRE t.transaction_id IS UNIQUE;

CREATE CONSTRAINT device_id_unique IF NOT EXISTS
FOR (d:Device) REQUIRE d.device_id IS UNIQUE;

CREATE CONSTRAINT location_id_unique IF NOT EXISTS
FOR (l:Location) REQUIRE l.location_id IS UNIQUE;

CREATE CONSTRAINT location_ip_unique IF NOT EXISTS
FOR (l:Location) REQUIRE l.ip_address IS UNIQUE;

// ── Indexes (speed up lookups) ───────────────────────────────

CREATE INDEX client_email_idx IF NOT EXISTS
FOR (c:Client) ON (c.email);

CREATE INDEX client_risk_idx IF NOT EXISTS
FOR (c:Client) ON (c.risk_score);

CREATE INDEX transaction_amount_idx IF NOT EXISTS
FOR (t:Transaction) ON (t.amount);

CREATE INDEX transaction_timestamp_idx IF NOT EXISTS
FOR (t:Transaction) ON (t.timestamp);

CREATE INDEX transaction_status_idx IF NOT EXISTS
FOR (t:Transaction) ON (t.status);

CREATE INDEX transaction_is_fraud_idx IF NOT EXISTS
FOR (t:Transaction) ON (t.is_fraud);

CREATE INDEX device_ip_idx IF NOT EXISTS
FOR (d:Device) ON (d.ip_address);

CREATE INDEX location_country_idx IF NOT EXISTS
FOR (l:Location) ON (l.country);

// ── Phase 9: Fraud Investigation & Case Management ───────────

CREATE CONSTRAINT case_id_unique IF NOT EXISTS
FOR (c:FraudCase) REQUIRE c.case_id IS UNIQUE;

CREATE INDEX case_status_idx IF NOT EXISTS
FOR (c:FraudCase) ON (c.status);

CREATE INDEX case_priority_idx IF NOT EXISTS
FOR (c:FraudCase) ON (c.priority);

CREATE INDEX case_entity_idx IF NOT EXISTS
FOR (c:FraudCase) ON (c.entity_id);

// ── Verify ───────────────────────────────────────────────────
SHOW CONSTRAINTS;
SHOW INDEXES;
