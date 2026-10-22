from fastapi import APIRouter, Request

from ..deps import client_ip, is_https

router = APIRouter()


@router.get("/health")
def health(request: Request):
    """Public, secret-free. `https_detected` and `client_ip` let you verify proxy settings after deploying:
    open https://YOUR-BACKEND/health in a browser; https_detected should be true and client_ip should be YOUR
    public IP (if it is a private/proxy address, adjust TRUST_PROXY_HEADERS / TRUSTED_PROXY_HOPS)."""
    st = request.app.state
    return {"status": "ok", "registration_open": st.settings.allow_registration,
            "server_llm_available": st.llm.configured,
            "ephemeral_storage": st.settings.ephemeral_storage_notice,
            "https_detected": is_https(request), "client_ip": client_ip(request)}
