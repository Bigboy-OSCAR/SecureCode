from fastapi import APIRouter

router = APIRouter(prefix="/pdf", tags=["pdf"])

@router.post("/parse")
def parse_pdf(pointer: str):
    return {"pointer": pointer, "status": "COMPLETED"}

@router.get("/read_pages")
def read_pdf_pages(pointer: str, start_page: int = 1, end_page: int = 1):
    return {"pointer": pointer, "pages": []}
