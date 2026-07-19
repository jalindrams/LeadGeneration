"""
Micraft Growth Engine - FastAPI Application
Main entry point for the API server.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.utils.logger import setup_logging
from app.api import health, leads, metrics, calling, pages, admin, auth, feedback, outreach, settings_api, command
from fastapi.staticfiles import StaticFiles

# Initialize logging
setup_logging()

# Create FastAPI app
app = FastAPI(
    title="Micraft Growth Engine",
    description="B2B Lead Generation & Revenue Engine for Micraft Solutions",
    version="1.0.0-phase1.5",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS (allow local development)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Register routers
app.include_router(health.router)
app.include_router(leads.router)
app.include_router(metrics.router)
app.include_router(calling.router)
app.include_router(pages.router)
app.include_router(admin.router)
app.include_router(auth.router)
app.include_router(feedback.router)
app.include_router(outreach.router)
app.include_router(settings_api.router)
app.include_router(command.router)


@app.get("/")
def root():
    return {
        "name": "Micraft Growth Engine",
        "version": "1.0.0-phase1.5",
        "status": "running",
        "docs": "/docs",
        "calling_ui": "/calling/",
        "health": "/health",
    }
