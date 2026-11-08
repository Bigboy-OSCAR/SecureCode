from fastapi import FastAPI, APIRouter

app = FastAPI(title="SecureCode Context Service")

@app.get("/source/read")
def read_source(pointer: str = "", start_line: int = 1, end_line: int = 100):
    return {"pointer": pointer, "start_line": start_line, "end_line": end_line, "content": ""}

@app.post("/context/select")
def select_context(payload: dict = None):
    return {"selected": [], "used_tokens": 0, "omitted": []}

@app.post("/pdf/parse")
def parse_pdf(pointer: str = ""):
    return {"pointer": pointer, "status": "COMPLETED"}

@app.get("/health")
def health():
    return {"status": "ok"}
