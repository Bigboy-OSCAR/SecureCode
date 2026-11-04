from fastapi import FastAPI

from securecode_context.api.pointers import router as pointers_router

app = FastAPI(
    title="SecureCode Context Service",
    version="0.1.0",
)

app.include_router(pointers_router)


@app.get("/api/v1/health")
def health():
    return {"status": "ok"}
