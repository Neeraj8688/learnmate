from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError

from ..deps import Ctx, check_question_length, get_ctx, rate_limit
from ..schemas import AgentRequest, AgentResponse
from ..services import quiz, tools

router = APIRouter()


@router.post("/agent", response_model=AgentResponse, dependencies=[Depends(rate_limit("llm"))])
def agent(body: AgentRequest, ctx: Ctx = Depends(get_ctx)):
    check_question_length(ctx, body.message)
    try:
        intent, tool, result = tools.run_agent(ctx, body.message)
    except quiz.QuizError as e:
        raise HTTPException(e.status, e.message)
    except ValidationError as e:
        raise HTTPException(422, f"Invalid tool arguments: {e.errors()[0]['msg']}")
    return AgentResponse(intent=intent, tool=tool, result=result)
