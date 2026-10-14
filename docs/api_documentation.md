# REST API Documentation

**Project:** Real-Time Graph-Based Financial Fraud Detection & Risk Analysis Platform  
**Version:** 2.0.0 (Standardized `/api/v1` Prefix)  
**Base URL:** `http://localhost:8000`  
**Interactive Docs:** `http://localhost:8000/docs` (Swagger UI) / `http://localhost:8000/redoc` (ReDoc)  

---

## 1. System & Health Endpoints

### `GET /`
Returns root project metadata and API version.
- **Response `200 OK`**:
```json
{
  "project": "Fraud Detection Platform",
  "version": "2.0.0",
  "review": "Review 2 — Neo4j Implementation",
  "status": "running",
  "docs": "/docs"
}
```

### `GET /health`
Verifies live connectivity to the Neo4j graph database.
- **Response `200 OK`**:
```json
{
  "status": "healthy",
  "neo4j": {
    "status": "connected",
    "address": "localhost:7687",
    "agent": "Neo4j/5.18.0",
    "protocol_version": "5.4"
  }
}
```

---

## 2. Client Endpoints (`/api/v1/clients`)

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/clients/` | List clients with pagination (`skip`, `limit`, `is_flagged`) |
| `GET` | `/api/v1/clients/stats` | Aggregated client counts, flagged counts, average risk score |
| `GET` | `/api/v1/clients/{client_id}` | Retrieve client profile with transaction and device counts |
| `POST` | `/api/v1/clients/` | Create a new Client node |
| `PUT` | `/api/v1/clients/{client_id}` | Update mutable client fields |
| `DELETE` | `/api/v1/clients/{client_id}` | Detach and delete a Client node |
| `GET` | `/api/v1/clients/{client_id}/transactions` | List all outgoing transactions performed by client |

---

## 3. Transaction Endpoints (`/api/v1/transactions`)

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/transactions/` | List transactions with filters (`skip`, `limit`, `is_fraud`, `min_amount`) |
| `GET` | `/api/v1/transactions/stats` | Total volume, fraud counts, average transaction amounts |
| `GET` | `/api/v1/transactions/{transaction_id}` | Retrieve transaction with sender, receiver, device, and location |
| `POST` | `/api/v1/transactions/` | Create a Transaction node and link relationships |
| `PUT` | `/api/v1/transactions/{transaction_id}` | Update transaction status / fraud score |
| `DELETE` | `/api/v1/transactions/{transaction_id}` | Detach and delete a Transaction node |

---

## 4. Device Endpoints (`/api/v1/devices`)

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/devices/` | List devices with optional `is_suspicious` filter |
| `GET` | `/api/v1/devices/{device_id}` | Retrieve device with list of connected clients and usage count |
| `POST` | `/api/v1/devices/` | Register a new Device node |
| `PUT` | `/api/v1/devices/{device_id}` | Update device properties |
| `DELETE` | `/api/v1/devices/{device_id}` | Detach and delete a Device node |

---

## 5. Location Endpoints (`/api/v1/locations`)

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/locations/` | List locations with optional `is_high_risk` filter |
| `GET` | `/api/v1/locations/{location_id}` | Retrieve location with transaction and fraud volume stats |
| `POST` | `/api/v1/locations/` | Register a new Location node |
| `PUT` | `/api/v1/locations/{location_id}` | Update location attributes |
| `DELETE` | `/api/v1/locations/{location_id}` | Detach and delete a Location node |

---

## 6. Fraud Detection Endpoints (`/api/v1/fraud`)

### `GET /api/v1/fraud/alerts`
Aggregated, round-robin balanced fraud signals across device sharing, high-risk locations, transaction flags, cycles, and multi-hop paths.
- **Parameters:** `limit` (default: 100)

### `GET /api/v1/fraud/shared-devices`
Finds devices shared across multiple client accounts (fraud rings).
- **Parameters:** `min_clients` (default: 2), `limit` (default: 100)

### `GET /api/v1/fraud/cycles`
Detects circular money transfer patterns (e.g. A → B → C → A).
- **Parameters:** `limit` (default: 100)

### `GET /api/v1/fraud/multi-hop`
Identifies suspicious 3-hop money transfer chains involving flagged entities.
- **Parameters:** `limit` (default: 50)

### `GET /api/v1/fraud/velocity`
Detects high-frequency transaction bursts from the same sender in short time windows.
- **Parameters:** `time_window_hours` (default: 2), `min_txn_count` (default: 5)

### `GET /api/v1/fraud/high-risk-locations`
Lists transactions originating from flagged high-risk jurisdictions.

### `GET /api/v1/fraud/summary`
Platform-wide executive fraud KPI statistics.

---

## 7. Risk Scoring Endpoints (`/api/v1/risk`)

### `GET /api/v1/risk/client/{clientId}`
Computes deterministic, explainable Graph-Based Risk Score (0–100) and factor contributions.

### `GET /api/v1/risk/transaction/{txId}`
Computes transaction risk score based on sender graph neighborhood factors.

### `GET /api/v1/risk/high-risk`
Lists entities with risk scores above threshold (default: High ≥ 50).

---

## 8. Graph Analytics Endpoints (`/api/v1/graph`)

### `GET /api/v1/graph/neighbors/{client_id}`
Traverses N-hop subgraph neighborhood around a given client (parameters: `hops=1..3`).

### `GET /api/v1/graph/subgraph`
Fetches a bounded, interconnected graph containing Clients, Transactions, Devices, and Locations formatted for `react-force-graph-2d`.

### `GET /api/v1/graph/path`
Finds the shortest graph path between two clients (`from_client`, `to_client`, `max_hops=1..6`).

---

## 9. Real-Time Streaming & WebSocket Endpoints (`/api/v1/stream` & `/ws`)

### `GET /api/v1/stream/status`
Returns real-time simulator status, running state, current fraud pattern, total generated transactions, and active WebSocket client count.

### `POST /api/v1/stream/start`
Starts the asynchronous background event loop that continuously generates configurable transactions and persists them into Neo4j.

### `POST /api/v1/stream/stop`
Stops the background transaction stream simulator.

### `POST /api/v1/stream/config`
Updates stream simulation settings:
- `interval_seconds`: generation delay (0.5s to 30.0s)
- `active_pattern`: `"random"`, `"normal"`, `"velocity"`, `"ring"`, `"cycle"`, `"geo_anomaly"`, `"multi_hop"`

### `POST /api/v1/stream/step`
Triggers immediate execution of a single simulated transaction and broadcasts the result.

### `WS /ws/alerts` & `/api/v1/stream/ws/alerts`
Bi-directional WebSocket connection. Broadcasts:
- `NEW_TRANSACTION`: Live transaction event payload
- `FRAUD_ALERT`: Real-time graph fraud alert with risk score, risk level, and factor breakdown

---

## 10. Machine Learning & Graph Analytics Endpoints (`/api/v1/ml`)

### `GET /api/v1/ml/info`
Returns model architecture, version, training date, leakage-safe feature definitions, evaluation scorecard comparing Random Forest, Logistic Regression baseline, and Rule-Based engine, confusion matrix, and feature importances.

### `GET /api/v1/ml/predict/client/{client_id}`
Extracts graph topological features for an account and returns:
- `mlFraudProbability`: Statistical probability from the trained Random Forest classifier
- `mlPrediction`: `PREDICTED_FRAUD` or `PREDICTED_LEGITIMATE`
- `ruleBasedScore`: Deterministic graph score (0–100)
- `combinedRiskScore`: Weighted ensemble index (60% rule score + 40% ML probability)
- `topContributingFeatures`: Key features driving the model prediction
- `rawFeatures`: Normalized numerical feature vector
- `disclaimer`: Compliance and investigative note

### `GET /api/v1/ml/communities`
Returns detected suspicious graph clusters:
- Device-sharing rings
- Circular fund layering chains ($A \to B \to C \to A$)
- Shell corporation multi-hop structuring chains

---

## 11. Fraud Investigation & Case Management Endpoints (`/api/v1/cases`)

### `GET /api/v1/cases`
List and filter fraud cases with pagination support.
- **Query Parameters**:
  - `status`: Optional filter by case status (`NEW_ALERT`, `UNDER_INVESTIGATION`, `CONFIRMED_FRAUD`, `DISMISSED_FALSE_POSITIVE`, `ESCALATED`, `REOPENED`)
  - `priority`: Optional filter by priority (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`)
  - `analyst`: Optional filter by assigned analyst
  - `entity_type`: Optional filter by entity type (`Transaction`, `Client`, `Device`, `Location`)
  - `search`: Case ID, entity ID, or title text search
  - `limit`: Page limit (default 50, max 200)
  - `skip`: Pagination offset (default 0)
- **Response**: `{ "total": int, "cases": [FraudCase, ...] }`

### `GET /api/v1/cases/{case_id}`
Retrieves complete case record including:
- Core metadata, title, summary, status, priority, assigned analyst, risk score
- Associated entity details and optimistic concurrency version
- Resolution category and explanation
- Linked `graph_context` (counterparties, connected devices, locations, and transactions)
- Analyst `notes` and immutable `audit_trail`

### `POST /api/v1/cases`
Idempotently creates a new fraud case or returns existing active investigation for the entity.
- **Request Body**:
  ```json
  {
    "entity_id": "TXN_041",
    "entity_type": "Transaction",
    "alert_id": "ALT_12345",
    "title": "Suspicious rapid layering burst",
    "summary": "Transfer to mule account via proxy IP",
    "priority": "HIGH",
    "assigned_analyst": "analyst_priya",
    "risk_score": 85.0
  }
  ```
- **Response**: `FraudCase` (Status 201 Created or 200 OK for idempotent return)

### `PATCH /api/v1/cases/{case_id}/assign`
Assigns or reassigns an analyst to the case.
- **Request Body**: `{ "assigned_analyst": "analyst_priya", "actor": "supervisor" }`
- **Response**: Updated `FraudCase` (increments version and appends audit record)

### `PATCH /api/v1/cases/{case_id}/priority`
Adjusts case severity priority.
- **Request Body**: `{ "priority": "CRITICAL", "actor": "analyst_priya" }`
- **Response**: Updated `FraudCase` (increments version and appends audit record)

### `POST /api/v1/cases/{case_id}/transition`
Executes validated lifecycle status transitions with optimistic concurrency and resolution checks.
- **Request Body**:
  ```json
  {
    "target_status": "CONFIRMED_FRAUD",
    "actor": "analyst_priya",
    "resolution_category": "TRUE_POSITIVE_FRAUD",
    "resolution_explanation": "Investigation verified synthetic account takeover and coordinated layering.",
    "expected_version": 2
  }
  ```
- **Validation Rules**:
  - `NEW_ALERT` &rarr; `UNDER_INVESTIGATION`, `DISMISSED_FALSE_POSITIVE`, `ESCALATED`
  - `UNDER_INVESTIGATION` &rarr; `CONFIRMED_FRAUD`, `DISMISSED_FALSE_POSITIVE`, `ESCALATED`
  - `ESCALATED` &rarr; `UNDER_INVESTIGATION`, `CONFIRMED_FRAUD`, `DISMISSED_FALSE_POSITIVE`
  - `CONFIRMED_FRAUD` / `DISMISSED_FALSE_POSITIVE` &rarr; `REOPENED` (requires justification)
  - `CONFIRMED_FRAUD` and `DISMISSED_FALSE_POSITIVE` strictly require `resolution_category` and `resolution_explanation` (&ge; 5 characters).
  - Version mismatch returns HTTP 409 Conflict.

### `POST /api/v1/cases/{case_id}/notes`
Appends a timestamped investigator observation.
- **Request Body**: `{ "note": "Subpoena response received confirming fraudulent IP location.", "author": "analyst_priya" }`
- **Response**: Created `CaseNote` (Status 201 Created)

### `GET /api/v1/cases/{case_id}/history`
Returns the append-only chronological audit trail recording all actions, actors, timestamps, previous vs new values, and reasons.

---

## 11. Authentication & Security Endpoints (`/api/v1/auth`)

| Method | Endpoint | Description | Permissions |
|---|---|---|---|
| `POST` | `/api/v1/auth/login` | Authenticate with username/password, returns tokens + sets HttpOnly cookies | Public |
| `POST` | `/api/v1/auth/refresh` | Rotate access & refresh tokens | Active User |
| `POST` | `/api/v1/auth/logout` | Revoke tokens & clear auth cookies | Active User |
| `GET` | `/api/v1/auth/me` | Retrieve profile and granted permissions of authenticated user | Active User |
| `POST` | `/api/v1/auth/ws-ticket` | Generate single-use, 30s ticket for WebSocket authentication | Active User |

---

## 12. User Administration Endpoints (`/api/v1/users`)

*Restricted strictly to users with role `admin` (`admin:users` permission).*

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/users` | List all system users |
| `POST` | `/api/v1/users` | Create new system user (hashes password with Bcrypt) |
| `GET` | `/api/v1/users/{user_id}` | Retrieve user profile by UUID |
| `PATCH` | `/api/v1/users/{user_id}` | Update user role, status (`is_active`), email, or password |
| `DELETE` | `/api/v1/users/{user_id}` | Delete system user |



