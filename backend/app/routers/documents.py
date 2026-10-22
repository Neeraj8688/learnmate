import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from ..deps import Ctx, get_ctx, rate_limit
from ..schemas import DocumentInfo, SearchRequest, SearchResponse, UploadResponse
from ..services.chunking import chunk_pages
from ..services.extraction import ExtractionError, extract
from ..services.retrieval import retrieve

router = APIRouter()


@router.post("/documents", response_model=UploadResponse, status_code=201,
             dependencies=[Depends(rate_limit("upload"))])
async def upload(file: UploadFile = File(...), ctx: Ctx = Depends(get_ctx)):
    s = ctx.settings
    name = file.filename or ""
    if not name.lower().endswith((".pdf", ".txt")):
        raise HTTPException(415, "Unsupported file type. Only .pdf and .txt are allowed.")
    if len(ctx.store.list_documents()) >= s.max_docs_per_user:
        raise HTTPException(409, f"Document limit reached ({s.max_docs_per_user}). Delete one first.")
    limit = s.upload_max_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, f"File exceeds {s.upload_max_mb} MB limit.")
    try:
        pages = extract(name, data)
    except ExtractionError as exc:
        raise HTTPException(422, str(exc))
    doc_id = uuid.uuid4().hex[:12]
    chunks = chunk_pages(doc_id, pages, s.chunk_size, s.chunk_overlap)
    if len(chunks) > s.max_chunks_per_doc:
        raise HTTPException(413, f"Document too large ({len(chunks)} chunks; max {s.max_chunks_per_doc}).")
    ctx.store.add_document(doc_id, name, chunks)
    return UploadResponse(document_id=doc_id, filename=name, pages=len(pages), chunks=len(chunks))


@router.get("/documents", response_model=list[DocumentInfo])
def list_documents(ctx: Ctx = Depends(get_ctx)):
    return ctx.store.list_documents()


@router.delete("/documents/{doc_id}")
def delete_document(doc_id: str, ctx: Ctx = Depends(get_ctx)):
    if ctx.store.delete_document(doc_id) == 0:
        raise HTTPException(404, "Document not found.")
    return {"deleted": doc_id}


@router.post("/search", response_model=SearchResponse)
def search(body: SearchRequest, ctx: Ctx = Depends(get_ctx)):
    return SearchResponse(query=body.query,
                          results=retrieve(ctx.store, body.query, body.top_k, ctx.settings.min_relevance))
