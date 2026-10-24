from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import shipments, events, agent_tasks, agent_actions, approvals, audit_logs
from api.routes.agent_run import router as agent_run_router
from api.routes.demo import router as demo_router
from documents.router import router as documents_router

app = FastAPI(
    title="Autonomous AI Customs Clearance API",
    version="1.0.0",
    description="Backend for the AI-driven customs clearance demo (synthetic data only).",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(shipments.router)
app.include_router(events.router)
app.include_router(agent_tasks.router)
app.include_router(agent_actions.router)
app.include_router(approvals.router)
app.include_router(audit_logs.router)
app.include_router(documents_router)
app.include_router(agent_run_router)
app.include_router(demo_router)


@app.get("/health")
def health():
    return {"status": "ok"}
