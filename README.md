# Real-Time Graph-Based Financial Fraud Detection & Risk Analysis Platform

**B.Tech CSE Capstone Project — Final Submission (Phase 11)**  
**Platform Version:** 3.0.0 (Production Hardened)  
**Verification:** 57/57 Automated Test Suites Passing (100% Pass Rate)

---

## 1. Project Overview

This platform is an enterprise-grade financial crime intelligence and fraud detection system powered by the **Neo4j** graph database, **FastAPI** asynchronous backend, and **React 19 + Vite** visual investigation interface. 

By modeling financial transactions, account holders, physical hardware devices, and geolocations as an interconnected property graph, the platform detects complex fraud topologies that relational databases (RDBMS) fail to uncover in real time. It combines deterministic Cypher graph traversals, explainable multi-factor risk scoring, a 17-feature Random Forest graph machine learning classifier, real-time authenticated WebSocket alert delivery, a forensic case management workbench, and zero-trust Role-Based Access Control (RBAC).

---

## 2. Key Architectural Features

- **Native Graph Data Modeling:** Neo4j property graph schema enforcing uniqueness constraints and index-free adjacency across `Client`, `Transaction`, `Device`, and `Location` nodes.
- **Topological Fraud Detection:**
  - **Shared Hardware Device Rings:** Detects rings of $\ge 2$ clients sharing physical devices or proxy terminals.
  - **Circular Layering Cycles:** Uncovers directed money-washing loops ($A \to B \to C \to A$).
  - **Velocity Burst Smurfing:** Flags rapid transaction bursts ($\ge 5$ transfers within 10 minutes).
  - **Impossible Geovelocity Travel:** Identifies rapid transfers across geographically incompatible coordinates.
- **Explainable Multi-Factor Risk Scoring:** Computes a deterministic 0–100 composite risk score with factor-level mathematical penalty breakdowns.
- **Graph Machine Learning Engine:** 17-feature topological extractor (`feature_extractor.py`), Random Forest classifier (`train_model.py`), joblib model persistence, and real-time inference API.
- **Real-Time Streaming & Alerts:** Asynchronous transaction simulator pushing instantaneous fraud alerts to investigator screens over authenticated WebSockets.
- **Forensic Case Management Workbench:** Complete finite state machine (`NEW_ALERT` $\to$ `UNDER_INVESTIGATION` $\to$ `CONFIRMED_FRAUD` / `DISMISSED_FALSE_POSITIVE` $\to$ `REOPENED`), optimistic concurrency version tracking, and immutable audit trails.
- **Zero-Trust Security & RBAC:** Bcrypt (12 salt rounds) password hashing, signed JWT access and refresh tokens (`HS256`), cryptographic JTI revocation cache, and route-level role authorization (`admin`, `fraud_analyst`, `compliance_officer`).

---

## 3. Technology Stack

| Layer | Primary Technologies |
| :--- | :--- |
| **Graph Database** | Neo4j Community / Enterprise 5.18.0 (Cypher, APOC extensions) |
| **Backend API Server**| Python 3.11, FastAPI 0.110.0, Pydantic v2, Starlette, Uvicorn |
| **Security & Auth** | PyJWT 2.10.1 (HS256 tokens), Bcrypt 4.3.0, HttpOnly Cookies |
| **Machine Learning** | scikit-learn 1.4.1, joblib 1.3.2, numpy 1.26.4 |
| **Frontend UI** | React 19.0.0, Vite 8.3.1, react-force-graph-2d, Axios, Lucide Icons |
| **DevOps & Deploy** | Docker Compose, Multi-Stage Dockerfiles, Alpine NGINX |

---

## 4. Repository Structure

```
nosql project/
├── docker-compose.yml              # Complete 3-tier containerization (Neo4j, Backend, Frontend)
├── .env.example                    # Externalized environment variables template
├── .env                            # Active environment configuration (gitignored)
├── README.md                       # Main capstone project documentation
│
├── final_submission/               # Final Capstone Deliverables Directory
│   ├── FINAL_IMPLEMENTATION_AUDIT.md     # Feature classification & audit log
│   ├── ACADEMIC_CAPSTONE_REPORT.md       # Complete 24-section formal engineering report
│   ├── ARCHITECTURE_AND_DESIGN_DIAGRAMS.md # 8 native Mermaid system diagrams
│   ├── EXPERIMENTAL_EVALUATION.md        # Benchmark methodology, latency, & empirical results
│   ├── CAPSTONE_PRESENTATION.md          # 13-slide defense presentation deck
│   ├── LIVE_DEMO_SCRIPT.md               # 11-step timed demonstration script
│   └── SUBMISSION_INVENTORY_AND_RISKS.md # Final deliverable inventory & submission risk matrix
│
├── backend/
│   ├── Dockerfile                  # Python 3.11 backend container
│   ├── requirements.txt            # Python dependencies (pyjwt, bcrypt, scikit-learn, neo4j)
│   ├── benchmark_evaluation.py     # Automated latency, throughput, & recovery benchmark
│   └── app/
│       ├── main.py                 # FastAPI application root & CORS middleware
│       ├── config.py               # Pydantic settings & externalized secrets
│       ├── auth/                   # Security engine, JWT claims, JTI blacklist, RBAC dependencies
│       ├── db/                     # Neo4j driver singleton & connection pool
│       ├── ml/                     # 17-feature extractor, training script, model artifacts
│       ├── routers/                # REST routers (auth, users, cases, stream, graph, fraud, risk, ml)
│       ├── schemas/                # Pydantic v2 domain schemas (auth, case, transaction, client)
│       └── services/               # Core engines (case_service, simulator, ml_service, risk_scoring)
│
├── database/
│   ├── schema.cypher               # Neo4j DDL constraints and performance indexes
│   ├── apply_schema.py             # Schema migration utility
│   ├── seed_data.py                # Synthetic dataset generator (60 clients, 4 fraud patterns)
│   ├── export_dump.py              # Database dump export script
│   └── dump/
│       └── fraud_detection_export.cypher # Reproducible database export
│
├── frontend/
│   ├── Dockerfile                  # Multi-stage production Nginx container
│   ├── nginx.conf                  # Production SPA proxy configuration
│   ├── package.json                # React 19 dependencies
│   ├── vite.config.js              # Vite bundler configuration
│   └── src/
│       ├── App.jsx                 # Topbar, role indicator, navigation, auth modal
│       ├── index.css               # Modern glassmorphic design system
│       ├── api/client.js           # Axios client with credentials & 401 interceptor
│       └── pages/                  # Dashboard, Cases, Clients, Transactions, FraudAnalysis, GraphView
│
└── tests/
    ├── test_security_phase10.py    # 23 Security, JWT, Bcrypt, & RBAC validation tests
    └── test_regression.py          # 34 Platform regression tests (Phases 1 through 9)
```

---

## 5. Getting Started

### Prerequisites
- **Docker Engine** v24+ and **Docker Compose** v2+
- Or **Python 3.11** and **Node.js 20+** for local development.

---

### Option 1: Quickstart with Docker Compose (Recommended)

1. **Clone repository and configure environment:**
   ```bash
   cp .env.example .env
   ```

2. **Launch all services in detached mode:**
   ```bash
   docker compose up --build -d
   ```

3. **Initialize database schema and seed synthetic data:**
   ```bash
   docker compose exec backend python database/apply_schema.py
   docker compose exec backend python database/seed_data.py
   ```

4. **Access the platform:**
   - **Frontend Investigation Console:** [http://localhost:3000](http://localhost:3000)
   - **FastAPI Interactive Swagger Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)
   - **Neo4j Browser:** [http://localhost:7474](http://localhost:7474) (Auth: `neo4j` / `fraud2024pass`)

5. **Shutdown the stack:**
   ```bash
   docker compose down
   ```

---

### Option 2: Local Development Setup

#### 1. Start Neo4j Database
Ensure Neo4j 5.x is active on port `7687`:
```bash
docker compose up -d neo4j
```

#### 2. Backend Setup
```bash
cd backend
python -m venv venv

# Activate virtual environment:
# Windows (cmd/powershell):
.\venv\Scripts\activate
# Linux / macOS:
source venv/bin/activate

# Install dependencies:
pip install -r requirements.txt

# Apply schema & seed synthetic graph:
python ../database/apply_schema.py
python ../database/seed_data.py

# Launch FastAPI ASGI server:
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

#### 3. Frontend Setup
In a separate terminal:
```bash
cd frontend
npm install
npm run dev
```
Navigate to [http://localhost:5173](http://localhost:5173).

---

## 6. Default Demo Credentials & Roles

The system is pre-configured with three role personas:

| Persona Role | Username | Password | Key Permissions |
| :--- | :--- | :--- | :--- |
| **Administrator** | `admin` | `Admin@FraudGraph2026!` | Full system access, simulator control, user CRUD |
| **Fraud Analyst** | `analyst_priya` | `AnalystPass2026!` | Case investigation, adding notes, graph exploration |
| **Compliance Officer** | `officer_chen` | `CompliancePass2026!` | Confirm/dismiss fraud, reopen cases, audit trails |

*Note: In the frontend UI, click **Sign In** and use the 1-click persona quick-fill buttons for instant authentication.*

---

## 7. Model Training & Evaluation

To re-train the 17-feature Random Forest classifier on fresh graph data:
```bash
# From backend directory with venv activated:
python -m app.ml.train_model
```
Outputs:
- Serialized model bundle: `backend/app/ml/model_artifacts.joblib`
- Metadata & evaluation scorecard: `backend/app/ml/metadata.json`

---

## 8. Automated Test Execution

Execute all test suites from the project root:

```bash
# 1. Run Security & RBAC Test Suite (23 tests):
backend\venv\Scripts\pytest tests/test_security_phase10.py

# 2. Run Full Platform Regression Suite (34 tests):
backend\venv\Scripts\pytest tests/test_regression.py

# 3. Run Empirical Performance Benchmark:
backend\venv\Scripts\python backend/benchmark_evaluation.py

# 4. Verify Frontend Production Build:
cd frontend && npm run build
```

---

## 9. Safe Database Reset Procedure

> [!CAUTION]
> **WARNING: DESTRUCTIVE ACTION**  
> Resetting the database completely purges all nodes, edges, case records, and transaction logs. Ensure any necessary investigative exports are saved before proceeding.

To perform a clean reset and re-seed:
```bash
# 1. Purge all nodes and relationships via cypher-shell or Python:
python -c "from app.db.neo4j_driver import get_driver; get_driver().execute_query('MATCH (n) DETACH DELETE n')"

# 2. Re-apply schema constraints and indexes:
python database/apply_schema.py

# 3. Re-seed clean synthetic graph topologies:
python database/seed_data.py
```

---

## 10. Troubleshooting & FAQ

1. **Neo4j Connection Refused (`bolt://localhost:7687`):**
   - Ensure the Neo4j container is running: `docker compose ps`.
   - If running FastAPI directly on host machine, verify `.env` contains `NEO4J_URI=bolt://localhost:7687`. Inside Docker, use `NEO4J_URI=bolt://neo4j:7687`.
2. **WebSocket 1008 Policy Rejection:**
   - The WebSocket alert channel requires authentication. Ensure you are signed in or have obtained a single-use ticket via `/api/v1/auth/ws-ticket`.
3. **403 Forbidden on Case Resolution:**
   - Only users with role `compliance_officer` or `admin` can confirm or dismiss cases. Switch to `officer_chen` or `admin`.
4. **Offline Resilience:**
   - If Neo4j is offline, the backend automatically utilizes an in-memory repository fallback. All API calls and case workflows continue operating without crashing.

---

## 11. Capstone Final Submission Deliverables

Comprehensive documentation artifacts for the final B.Tech capstone defense are located in `final_submission/`:

- [Final Implementation Audit](final_submission/FINAL_IMPLEMENTATION_AUDIT.md)
- [Academic Capstone Project Report](final_submission/ACADEMIC_CAPSTONE_REPORT.md)
- [Architecture & Design Diagrams](final_submission/ARCHITECTURE_AND_DESIGN_DIAGRAMS.md)
- [Experimental Evaluation & Benchmarks](final_submission/EXPERIMENTAL_EVALUATION.md)
- [Capstone Presentation Deck](final_submission/CAPSTONE_PRESENTATION.md)
- [Timed Live Demonstration Script](final_submission/LIVE_DEMO_SCRIPT.md)
- [Submission Inventory & Risk Matrix](final_submission/SUBMISSION_INVENTORY_AND_RISKS.md)
