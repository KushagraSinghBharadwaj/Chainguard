from fastapi import Request


def client_ip(request: Request, trust_proxy_headers: bool = False) -> str:
    """Best-effort client IP used only as an in-memory rate-limit key (never stored).

    X-Forwarded-For is ignored unless trust_proxy_headers is True, because a client
    can send any value and would otherwise bypass per-IP limits. When trusted, the
    LAST entry is used: that is the one appended by our own proxy.
    """
    if trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            last = forwarded.split(",")[-1].strip()
            if last:
                return last
    return request.client.host if request.client else "unknown"
