from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging
from neo4j.exceptions import Neo4jError, DriverError, ServiceUnavailable

from app.config import get_settings
from app.db.neo4j_driver import get_driver, close_driver, verify_connectivity

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting up — connecting to Neo4j...")
    try:
        info = verify_connectivity()
        logger.info(f"Neo4j connected: {info}")
    except Exception as e:
        logger.error(f"Neo4j connection failed: {e}")
    yield
    # Shutdown
    try:
        from app.services.simulator import simulator
        await simulator.stop()
    except Exception as e:
        logger.warning(f"Simulator stop failed: {e}")
    close_driver()
    logger.info("Neo4j driver closed.")


app = FastAPI(
    title="Fraud Detection Platform API",
    description=(
        "Real-Time Graph-Based Financial Fraud Detection & Risk Analysis Platform. "
        "B.Tech CSE NoSQL Database Project — Review 2. "
        "Uses Neo4j graph database with FastAPI for fraud analytics."
    ),
    version="2.0.0",
    contact={"name": "23BCE0159"},
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)


@app.exception_handler(Neo4jError)
@app.exception_handler(DriverError)
@app.exception_handler(ServiceUnavailable)
async def neo4j_error_handler(request, exc: Exception):
    logger.error("Neo4j database operation failed: %s (%s)", type(exc).__name__, exc)
    return JSONResponse(status_code=503, content={"detail": "Database operation failed"})


@app.exception_handler(ValueError)
async def value_error_handler(request, exc: ValueError):
    err_str = str(exc)
    if "Cannot resolve address" in err_str or "neo4j" in err_str:
        logger.error("Neo4j host address resolution failed: %s", exc)
        return JSONResponse(status_code=503, content={"detail": "Database operation failed"})
    return JSONResponse(status_code=400, content={"detail": err_str})


settings = get_settings()
cors_origins_list = [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]
if not cors_origins_list:
    cors_origins_list = ["http://localhost:5173", "http://localhost:3000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)



# ── Health Check ──────────────────────────────────────────────
@app.get("/", tags=["Health"])
def root():
    return {
        "project": "Fraud Detection Platform",
        "version": "2.0.0",
        "review": "Review 2 — Neo4j Implementation",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health", tags=["Health"])
def health_check():
    try:
        info = verify_connectivity()
        return {"status": "healthy", "neo4j": info}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


# ── Routers (Standardized /api/v1 routes) ────────────────────
from app.routers import auth, cases, clients, devices, fraud, graph, locations, ml, risk, stream, transactions, users

app.include_router(auth.router,         prefix="/api/v1",              tags=["Authentication"])
app.include_router(users.router,        prefix="/api/v1",              tags=["User Administration"])
app.include_router(cases.router,        prefix="/api/v1",              tags=["Case Management"])
app.include_router(clients.router,      prefix="/api/v1/clients",      tags=["Clients"])
app.include_router(transactions.router, prefix="/api/v1/transactions",  tags=["Transactions"])
app.include_router(devices.router,      prefix="/api/v1/devices",       tags=["Devices"])
app.include_router(locations.router,    prefix="/api/v1/locations",     tags=["Locations"])
app.include_router(fraud.router,        prefix="/api/v1/fraud",         tags=["Fraud Detection"])
app.include_router(risk.router,         prefix="/api/v1/risk",          tags=["Risk Scoring"])
app.include_router(graph.router,        prefix="/api/v1/graph",         tags=["Graph Analytics"])
app.include_router(stream.router,       prefix="/api/v1/stream",        tags=["Stream Simulator"])
app.include_router(ml.router,           prefix="/api/v1/ml",            tags=["Machine Learning"])

# Root alias for WebSocket alerts
@app.websocket("/ws/alerts")
async def root_websocket_alerts(websocket: stream.WebSocket):
    await stream.websocket_alerts_endpoint(websocket)



