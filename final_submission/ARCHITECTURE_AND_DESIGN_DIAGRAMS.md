# Architecture and System Design Diagrams

**Project:** Real-Time Graph-Based Financial Fraud Detection & Risk Analysis Platform  
**Document:** System Architecture, Workflows & Data Models  
**Format:** Native Mermaid (Markdown Reproducible)

---

## 1. Overall System Architecture

The high-level architecture separates concerns into a Presentation & Visualization Layer (React 19), a Security & API Gateway Layer, an Asynchronous Backend Engine (FastAPI), and a Persistence & Analytics Tier (Neo4j, Joblib, In-Memory Store).

```mermaid
flowchart TB
    subgraph UI_Tier["1. Presentation & Visualization Layer"]
        Dashboard["Dashboard View<br/>(Metrics & Live Stream)"]
        CasesView["Case Investigation UI<br/>(FSM & Audit History)"]
        GraphCanvas["Force-Directed Graph View<br/>(HTML5 Canvas Engine)"]
        AuthModal["Auth & Persona Selector<br/>(Admin, Analyst, Officer)"]
    end

    subgraph Security_Perimeter["2. Security & Gateway Perimeter"]
        TokenExtractor["Token Extractor<br/>(Bearer Header / HttpOnly Cookie)"]
        JWTEngine["PyJWT Security Engine<br/>(HS256 Signature & Expiration)"]
        JTIBlacklist["Revocation Blacklist<br/>(In-Memory TTL Cache)"]
        RBACGuard["RBAC Permission Gate<br/>(Route-Level Dependencies)"]
    end

    subgraph Backend_Core["3. FastAPI Asynchronous Core"]
        AuthRouter["Auth Router<br/>/api/v1/auth & /users"]
        CasesRouter["Cases Router<br/>/api/v1/cases"]
        StreamRouter["Stream Router<br/>/api/v1/stream"]
        AnalyticsRouter["Analytics Router<br/>/graph, /fraud, /risk, /ml"]

        CaseEngine["Case Management Engine<br/>(Version Check & FSM)"]
        WSManager["WebSocket Manager<br/>(Ticket & Cookie Handshake)"]
        Simulator["Transaction Simulator<br/>(Rate & Burst Injection)"]
        RiskEngine["Rule-Based Risk Engine<br/>(Composite 0-100 Score)"]
        MLService["Machine Learning Service<br/>(RandomForest Inference)"]
    end

    subgraph Storage_Tier["4. Persistence & Data Tier"]
        Neo4j[("Neo4j 5.18.0 Graph DB<br/>Bolt Port 7687")]
        MemFallback[("Thread-Safe In-Memory Store<br/>(Testing & Offline Mode)")]
        MLArtifacts["Model Artifacts<br/>(model_artifacts.joblib)"]
    end

    Dashboard --> TokenExtractor
    CasesView --> TokenExtractor
    GraphCanvas --> TokenExtractor
    AuthModal --> TokenExtractor

    TokenExtractor --> JWTEngine
    JWTEngine --> JTIBlacklist
    JTIBlacklist --> RBACGuard

    RBACGuard --> AuthRouter
    RBACGuard --> CasesRouter
    RBACGuard --> StreamRouter
    RBACGuard --> AnalyticsRouter

    CasesRouter --> CaseEngine
    StreamRouter --> WSManager
    StreamRouter --> Simulator
    AnalyticsRouter --> RiskEngine
    AnalyticsRouter --> MLService

    CaseEngine --> Neo4j
    CaseEngine -.-> MemFallback
    RiskEngine --> Neo4j
    RiskEngine -.-> MemFallback
    MLService --> MLArtifacts
    Simulator --> WSManager
```

---

## 2. Transaction Ingestion & Real-Time Fraud Alert Data Flow

Shows how financial transaction events are ingested, scored against multi-factor graph rules, and broadcast to investigator interfaces.

```mermaid
sequenceDiagram
    autonumber
    actor Generator as Transaction Generator / REST Ingestion
    participant StreamRoute as FastAPI /api/v1/stream
    participant RiskService as Risk Scoring Engine
    participant GraphDB as Neo4j Graph DB
    participant WSManager as WebSocket Connection Manager
    actor Analyst as Investigator (React Dashboard)

    Generator->>StreamRoute: POST /api/v1/stream/transactions (or Simulator Loop)
    StreamRoute->>RiskService: calculate_risk(transaction_data)
    RiskService->>GraphDB: Query velocity, shared devices, and circular paths
    GraphDB-->>RiskService: Node & Edge metrics
    RiskService->>RiskService: Calculate composite score (0-100) + explanations
    alt Score >= 75.0 (High or Critical Risk)
        RiskService-->>StreamRoute: High-Risk Alert Qualified
        StreamRoute->>WSManager: broadcast_alert(alert_payload)
        WSManager-->>Analyst: WebSocket Frame: {type: "NEW_ALERT", case_id, score, factors}
        Analyst->>Analyst: Update active alerts badge & render alert banner
    else Score < 75.0 (Low or Medium Risk)
        RiskService-->>StreamRoute: Normal / Low Risk Transaction
    end
    StreamRoute-->>Generator: HTTP 201 Created {transaction_id, risk_score}
```

---

## 3. Neo4j Property Graph Data Model

The data model captures relationships between Clients, Transactions, physical Devices, and Geolocation nodes.

```mermaid
classDiagram
    class Client {
        +String client_id [UNIQUE]
        +String name
        +String email [INDEX]
        +Float risk_score [INDEX]
        +Boolean is_flagged
        +String created_at
    }

    class Transaction {
        +String transaction_id [UNIQUE]
        +Float amount [INDEX]
        +String timestamp [INDEX]
        +String status
        +Boolean is_fraud [INDEX]
        +String channel
        +Int step
    }

    class Device {
        +String device_id [UNIQUE]
        +String device_type
        +String ip_address [INDEX]
        +String browser
        +Boolean is_compromised
    }

    class Location {
        +String location_id [UNIQUE]
        +String city
        +String country [INDEX]
        +Float latitude
        +Float longitude
        +Boolean is_high_risk
    }

    Client "1" --> "0..*" Transaction : PERFORMED
    Transaction "1" --> "1" Client : BENEFICIARY
    Client "0..*" --> "0..*" Client : TRANSFERRED_TO
    Client "0..*" --> "1..*" Device : USES_DEVICE
    Client "0..*" --> "1" Location : LOCATED_IN
    Transaction "0..*" --> "1" Location : EXECUTED_AT
```

---

## 4. Fraud Detection and Risk-Scoring Workflow

The deterministic rule engine evaluates 4 distinct risk dimensions and calculates an explainable composite score.

```mermaid
flowchart TD
    StartTx([Incoming Transaction Event]) --> CheckVelocity{Check Velocity<br/>>= 5 tx in 10 mins?}
    
    CheckVelocity -- Yes --> PenVel[Add Velocity Penalty +25<br/>Record factor explanation]
    CheckVelocity -- No --> CheckDevice{Check Device<br/>Shared by >= 3 clients?}
    PenVel --> CheckDevice

    CheckDevice -- Yes --> PenDev[Add Shared Device Penalty +25<br/>Record factor explanation]
    CheckDevice -- No --> CheckLocation{Check Location<br/>Sanctioned / High-Risk?}
    PenDev --> CheckLocation

    CheckLocation -- Yes --> PenLoc[Add High-Risk Location Penalty +30<br/>Record factor explanation]
    CheckLocation -- No --> CheckCycle{Check Cycles<br/>Member of directed cycle?}
    PenLoc --> CheckCycle

    CheckCycle -- Yes --> PenCyc[Add Cycle Penalty +35<br/>Record factor explanation]
    CheckCycle -- No --> Aggregate[Sum Penalties & Bound at 100]
    PenCyc --> Aggregate

    Aggregate --> Classify{Score Threshold}
    Classify -- "0 - 39" --> RiskLow[Classification: LOW]
    Classify -- "40 - 69" --> RiskMed[Classification: MEDIUM]
    Classify -- "70 - 84" --> RiskHigh[Classification: HIGH]
    Classify -- "85 - 100" --> RiskCrit[Classification: CRITICAL]

    RiskHigh --> GenAlert[Trigger Real-Time WebSocket Alert]
    RiskCrit --> GenAlert
```

---

## 5. Machine Learning Training and Inference Workflow

Shows the feature extraction, model serialization, and real-time client inference flow.

```mermaid
flowchart LR
    subgraph TrainingPipeline["1. Offline Model Training Pipeline"]
        RawGraph[(Neo4j Graph / Synthetic Dataset)] --> Extractor[17-Feature Graph Extractor<br/>feature_extractor.py]
        Extractor --> Splitter[Stratified Train/Test Split<br/>75% Train / 25% Test]
        Splitter --> RFModel[Random Forest Classifier<br/>train_model.py]
        RFModel --> Evaluator[Evaluation & Confusion Matrix<br/>F1, PR-AUC, ROC-AUC]
        Evaluator --> Serializer[joblib.dump<br/>model_artifacts.joblib & metadata.json]
    end

    subgraph ServingPipeline["2. Real-Time Inference Pipeline"]
        APIClient[Client / Investigator Request] --> MLRouter["GET /api/v1/ml/predict/client/{id}"]
        MLRouter --> OnDemandExt[Extract 17 Features from Live Graph]
        Serializer -. Load Artifact .-> ModelInstance[In-Memory RF Model Instance]
        OnDemandExt --> ModelInstance
        ModelInstance --> Formatter[Format Probability & Top Features]
        Formatter --> Response[Return Inference JSON with Explanations]
    end
```

---

## 6. Investigator Case Lifecycle (Finite State Machine)

The state machine enforcing valid transitions, concurrency version checks, and mandatory justifications.

```mermaid
stateDiagram-v2
    [*] --> NEW_ALERT : Automatic Alert Creation
    
    NEW_ALERT --> UNDER_INVESTIGATION : Analyst Claims Case<br/>(Permission: cases:investigate)
    NEW_ALERT --> DISMISSED_FALSE_POSITIVE : Immediate Dismissal<br/>(Permission: cases:resolve)
    NEW_ALERT --> ESCALATED : Escalate for Senior Attention
    
    UNDER_INVESTIGATION --> CONFIRMED_FRAUD : Confirm Fraud<br/>(Mandatory category & explanation)
    UNDER_INVESTIGATION --> DISMISSED_FALSE_POSITIVE : Dismiss as False Positive<br/>(Mandatory category & explanation)
    UNDER_INVESTIGATION --> ESCALATED : Request Compliance Review
    
    ESCALATED --> UNDER_INVESTIGATION : Return with Notes
    ESCALATED --> CONFIRMED_FRAUD : Final Confirmation
    ESCALATED --> DISMISSED_FALSE_POSITIVE : Final Dismissal
    
    CONFIRMED_FRAUD --> REOPENED : New Evidence Reopening<br/>(Permission: cases:reopen)
    DISMISSED_FALSE_POSITIVE --> REOPENED : New Evidence Reopening<br/>(Permission: cases:reopen)
    
    REOPENED --> UNDER_INVESTIGATION : Resume Review
```

---

## 7. Authentication and Authorization Protocol Flow

Shows user login, dual token issuance (cookies + JSON), request authentication, and token revocation.

```mermaid
sequenceDiagram
    autonumber
    actor User as User / Browser
    participant API as FastAPI /api/v1/auth
    participant Security as Security Service (PyJWT & Bcrypt)
    participant Blacklist as In-Memory JTI Blacklist
    participant Resource as Protected Case Endpoint

    User->>API: POST /api/v1/auth/login {username, password}
    API->>Security: verify_password(password, hashed_password)
    Security-->>API: Password Valid & User Active
    API->>Security: Issue Access Token (30m) & Refresh Token (7d)
    API-->>User: 200 OK + Set-Cookie (HttpOnly, SameSite) + JSON Body

    Note over User, Resource: Authenticated Request
    User->>Resource: GET /api/v1/cases (Cookie or Bearer Header)
    Resource->>Security: Validate Signature, Expiration, Issuer, Audience
    Resource->>Blacklist: Check if token JTI is blacklisted
    alt Token Blacklisted or Expired
        Resource-->>User: 401 Unauthorized
    else Valid & Active
        Resource->>Resource: Check Role Permissions (e.g., cases:read)
        alt Insufficient Permission
            Resource-->>User: 403 Forbidden
        else Authorized
            Resource-->>User: 200 OK Case Records
        end
    end

    Note over User, API: Logout Flow
    User->>API: POST /api/v1/auth/logout
    API->>Blacklist: Add access & refresh token JTIs to Blacklist (with TTL)
    API-->>User: 200 OK + Clear Cookies
```

---

## 8. Deployment and Infrastructure Architecture

Shows the containerized Docker Compose network isolating the database, application server, and web client.

```mermaid
flowchart TD
    subgraph Host["Host Machine (Windows / Linux)"]
        UserBrowser["Web Browser<br/>http://localhost:3000"]
        APICaller["Developer / API Client<br/>http://localhost:8000"]
        Neo4jBrowser["Neo4j Browser Client<br/>http://localhost:7474"]
    end

    subgraph DockerBridge["Docker Bridge Network: fraud_net"]
        subgraph FrontContainer["Container: fraud_frontend"]
            Nginx["Alpine NGINX Server<br/>Port 80 (Mapped to Host 3000)"]
            StaticFiles["React 19 Minified Production Build<br/>(/usr/share/nginx/html)"]
            Nginx --> StaticFiles
        end

        subgraph BackContainer["Container: fraud_backend"]
            Uvicorn["Uvicorn ASGI Server<br/>Port 8000 (Mapped to Host 8000)"]
            FastAPIApp["FastAPI Application Core<br/>(Python 3.11-slim)"]
            Uvicorn --> FastAPIApp
        end

        subgraph DBContainer["Container: fraud_neo4j"]
            Neo4jEngine["Neo4j 5.18.0 Community<br/>Bolt Port 7687 / HTTP Port 7474"]
            APOCProc["APOC Procedures Extension"]
            DataVol[("neo4j_data<br/>Docker Volume")]
            LogsVol[("neo4j_logs<br/>Docker Volume")]
            Neo4jEngine --> APOCProc
            Neo4jEngine --> DataVol
            Neo4jEngine --> LogsVol
        end
    end

    UserBrowser --> Nginx
    Nginx -. Reverse Proxy /api .-> Uvicorn
    APICaller --> Uvicorn
    Neo4jBrowser --> Neo4jEngine
    FastAPIApp -->|Bolt Protocol 7687| Neo4jEngine
```
