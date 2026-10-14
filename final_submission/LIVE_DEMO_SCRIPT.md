# Timed Live Demonstration Script

**Project:** Real-Time Graph-Based Financial Fraud Detection & Risk Analysis Platform  
**Target Duration:** 10 to 12 Minutes  
**Audience:** B.Tech CSE Final Evaluation Committee & Technical Reviewers  
**Purpose:** Step-by-step verified execution protocol for live system demonstration

---

## 1. Prerequisites and Setup Verification

Ensure the following runtimes and services are available before starting the demonstration:

| Prerequisite | Verified Requirement | Verification Command |
| :--- | :--- | :--- |
| **Docker & Docker Compose** | Docker v24+ / Compose v2+ | `docker compose version` |
| **Python Environment** | Python 3.11.5 with venv activated | `python --version` |
| **Node.js Environment** | Node.js v20+ & npm v10+ | `node -v` |
| **Port Availability** | Ports 3000, 7474, 7687, 8000 free | `netstat -ano | findstr "8000 7687 3000"` |

### Demo Credentials Catalog

| Role | Username | Password | Intended Demo Actions |
| :--- | :--- | :--- | :--- |
| **Administrator** | `admin` | `Admin@FraudGraph2026!` | Simulator controls, user management, unrestricted access |
| **Fraud Analyst** | `analyst_priya` | `AnalystPass2026!` | Case investigation, adding notes, graph exploration |
| **Compliance Officer** | `officer_chen` | `CompliancePass2026!` | Case confirmation/dismissal, audit trail inspection |

---

## 2. Timed Demonstration Walkthrough

```
Timeline Overview:
[00:00 - 01:00] Step 1 & 2: Start Stack & Verify Health
[01:00 - 02:30] Step 3 & 4: Dashboard Overview & Client Graph Inspection
[02:30 - 04:30] Step 5 & 6: Trigger Transaction Simulation & Live WebSocket Alert
[04:30 - 06:00] Step 7: Explore Suspicious Graph Pattern (Shared Device Ring)
[06:00 - 08:00] Step 8 & 9: Case Investigation & Authorization Boundary Test
[08:00 - 09:30] Step 10: Review Immutable Audit Trail & Actor Preservation
[09:30 - 11:00] Step 11: Present Benchmark Evidence & Automated Test Results
```

---

### Step 1: Starting the Docker Stack (00:00 - 00:30)
- **Action:** Open terminal in project root and execute:
  ```bash
  docker compose up -d neo4j
  ```
- **Expected Observation:** Docker pulls/starts `fraud_neo4j`. The container health check verifies Bolt port `7687` is accepting connections.

---

### Step 2: Checking Service Health (00:30 - 01:00)
- **Action:** Start the FastAPI backend or verify health via curl:
  ```bash
  curl http://localhost:8000/health
  ```
- **Expected Output:**
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

### Step 3: Opening the Dashboard (01:00 - 01:45)
- **Action:** Open browser at `http://localhost:3000`. Click the **Sign In** button in the top navigation bar. Click the 1-click quick-fill button for **Admin (`admin`)** and click **Authenticate**.
- **Expected Observation:** The dashboard authenticates immediately. The top-bar displays the green `Admin` role badge. Active summary cards display Total Clients (60), Flagged Accounts, Average Risk Score, and Simulator Status.

---

### Step 4: Inspecting a Client and Graph Neighborhood (01:45 - 02:30)
- **Action:** Click **Clients** in the sidebar. Select client **`CLT031`** (a known synthetic fraud syndicate actor).
- **Expected Observation:** The client profile drawer opens, displaying:
  - Account Risk Score: $92.5$ (`CRITICAL`)
  - Outgoing Volume: INR 85,000+
  - Connected Devices: `DEV011` (Proxy Terminal in Lagos, Nigeria)
  - Connected Entities: Direct transfers to `CLT032` and `CLT033`

---

### Step 5: Generating a Synthetic Transaction (02:30 - 03:30)
- **Action:** Navigate back to **Dashboard**. In the **Transaction Simulator Controls** panel, ensure Rate is set to `2 tx/s`. Click **Start Simulation**. Alternatively, inject a manual high-risk step by executing:
  ```bash
  curl -X POST http://localhost:8000/api/v1/stream/step \
    -H "Authorization: Bearer <ADMIN_TOKEN>"
  ```
- **Expected Observation:** The live transaction ticker starts streaming events into the real-time table. The simulator badge switches to green `ACTIVE`.

---

### Step 6: Showing the Live WebSocket Alert (03:30 - 04:30)
- **Action:** While the simulator is active, click the **Fraud Burst: Shared Device Ring** button.
- **Expected Observation:**
  1. A transaction event involving `CLT031` and `DEV011` is emitted.
  2. The risk scoring engine evaluates the event and computes a score of $92.5$ (`CRITICAL`).
  3. A high-priority red alert toast notification immediately pops up on screen:
     > *"NEW FRAUD ALERT — Transaction TXN_xxx flagged with Risk Score 92.5 (Shared Device + Circular Path)"*
  4. The **Active Alerts** count increments in real time without refreshing the browser page.

---

### Step 7: Exploring a Suspicious Graph Pattern (04:30 - 06:00)
- **Action:** Click **Graph View** in the sidebar. Select **Fraud Rings & Subgraphs**.
- **Expected Observation:** An interactive 2D force-directed graph canvas renders.
  - Red nodes indicate flagged fraud actors (`CLT031`, `CLT032`, `CLT033`, `CLT034`).
  - Purple square nodes represent shared devices (`DEV011`, `DEV012`).
  - Hovering over `DEV011` highlights edges connecting to three separate client accounts, visually proving the synthetic identity ring topology.

---

### Step 8: Opening and Updating an Investigation Case (06:00 - 07:15)
- **Action:** Click **Cases** in the sidebar. Switch persona to **Fraud Analyst** (`analyst_priya`).
- **Action Steps:**
  1. Open case **`CASE-2026-0001`** (currently `UNDER_INVESTIGATION`).
  2. In the **Analyst Notes** box, type:
     > *"Subpoena response confirmed unauthorized SIM swap. Proceeding with account freeze."*
  3. Click **Add Note**.
  4. Under **Assign Analyst**, assign the case to `analyst_priya`.
- **Expected Observation:** The note is appended immediately with author `analyst_priya` and the current UTC timestamp. The case version increments from 2 to 3.

---

### Step 9: Demonstrating an Authorization Boundary (07:15 - 08:00)
- **Action:** While logged in as `analyst_priya`:
  1. Attempt to resolve the case by clicking **Confirm Fraud**.
  2. Attempt to click **Start Simulator** on the Dashboard.
- **Expected Observation:**
  1. The resolution button displays a disabled warning or clicking it triggers an HTTP `403 Forbidden` notification:
     > *"Action Denied: Role 'fraud_analyst' lacks 'cases:resolve' permission. Compliance Officer approval required."*
  2. The simulator controls display a banner: *"Simulator controls are restricted to administrators."*
  *This conclusively demonstrates backend-enforced RBAC independent of the UI.*

---

### Step 10: Reviewing Immutable Audit History (08:00 - 09:30)
- **Action:** Log in as **Compliance Officer** (`officer_chen`). Open case **`CASE-2026-0001`**. Click **Resolve Case** $\to$ **Confirm Fraud**.
  - Resolution Category: `TRUE_POSITIVE_FRAUD`
  - Explanation: *"Verified coordinated mule account layering across proxy device DEV011."*
  - Click **Submit Resolution**.
- **Action:** Click the **Audit Trail** tab.
- **Expected Observation:** The full chronological audit trail displays:
  - Record 1: Created by `admin` (Version 1)
  - Record 2: Assigned to `analyst_priya` by `analyst_priya` (Version 2)
  - Record 3: Note added by `analyst_priya`
  - Record 4: Status transitioned from `UNDER_INVESTIGATION` to `CONFIRMED_FRAUD` by `officer_chen` (Version 3)
  *Every record proves immutable actor identity preservation.*

---

### Step 11: Showing Evaluation Results and Test Evidence (09:30 - 11:00)
- **Action:** Open terminal and run the automated test suite:
  ```bash
  backend\venv\Scripts\pytest tests/test_security_phase10.py
  backend\venv\Scripts\pytest tests/test_regression.py
  ```
- **Expected Output:**
  - `test_security_phase10.py`: **23 passed in ~72s** (100% pass)
  - `test_regression.py`: **34 passed in ~126s** (100% pass)
  - Total: **57/57 automated tests passed**.

---

## 3. Fallback Instructions & Troubleshooting

### Scenario A: Local Neo4j Container is Offline
- **Automatic Fallback:** The backend is built with an automatic thread-safe in-memory repository fallback. All API calls, case mutations, and risk scoring continue functioning seamlessly without crashing.
- **Recovery Action:** Restart container: `docker compose restart neo4j`. Wait 15 seconds for the health check probe to turn green.

### Scenario B: Expired Browser Session
- **Symptom:** UI displays `401 Unauthorized` toast banner.
- **Recovery Action:** Click **Sign In**, select **Admin Quick-Fill**, and re-authenticate. The app preserves the current page view.
