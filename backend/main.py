from fastapi import FastAPI

from backend.api.routes.research import router as research_router


app = FastAPI(
    title="FinResearch AI",
    version="0.1.0",
)


@app.get("/health")
def health_check():
    return {"status": "ok"}


app.include_router(research_router)