# FraudGraph dashboard

Minimal React + Vite dashboard for the FastAPI and Neo4j fraud graph.

Start the backend and Neo4j from the project root, then run the frontend:

```powershell
docker compose up -d neo4j backend
cd frontend
npm install
npm run dev
```

Vite serves the dashboard at `http://localhost:5173`. It connects to FastAPI at `http://localhost:8000` by default. To use another backend address, set `VITE_API_BASE_URL` in `frontend/.env.local` before starting Vite.

The dashboard reads all counts, alerts, risks, investigations, and graph nodes from FastAPI; it does not contain seeded dashboard values.
