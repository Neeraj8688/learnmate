from fastapi import APIRouter, Depends

from ..deps import Ctx, check_question_length, get_ctx, rate_limit
from ..schemas import ChatRequest, ChatResponse
from ..services.answer import build_grounded_prompt, clean_answer, number_sources
from ..services.retrieval import retrieve

router = APIRouter()


@router.post("/chat", response_model=ChatResponse, dependencies=[Depends(rate_limit("llm"))])
def chat(body: ChatRequest, ctx: Ctx = Depends(get_ctx)):
    check_question_length(ctx, body.question)
    sources = number_sources(retrieve(ctx.store, body.question, ctx.settings.top_k, ctx.settings.min_relevance))
    if not sources:
        return ChatResponse(
            status="insufficient_evidence",
            answer="I could not find enough evidence in your uploaded notes to answer this.", sources=[])
    if not ctx.llm.configured:
        return ChatResponse(
            status="llm_not_configured",
            answer="No AI is available right now. Connect your own Gemini API key to get written answers. "
                   "The most relevant passages from your notes are listed below.",
            sources=sources)
    # LLMError subclasses are turned into coded JSON errors by the app-level handler.
    text = ctx.llm.generate(build_grounded_prompt(body.question, sources))
    return ChatResponse(status="answered", answer=clean_answer(text, sources), sources=sources)
