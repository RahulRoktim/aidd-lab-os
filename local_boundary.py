"""Local single-operator boundary, not a hosted authentication system."""
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import JSONResponse

ORIGINS = [f'http://{host}:{port}' for host in ('localhost', '127.0.0.1') for port in (8000, 8001)]


def install_local_boundary(app):
    app.add_middleware(CORSMiddleware, allow_origins=ORIGINS,
                       allow_credentials=False, allow_methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'],
                       allow_headers=['Content-Type'])
    app.add_middleware(TrustedHostMiddleware,
                       allowed_hosts=['localhost', '127.0.0.1', '[::1]', 'aidd-worker', 'aidd-app', 'testserver'])

    @app.middleware('http')
    async def reject_foreign_origin(request, call_next):
        origin = request.headers.get('origin')
        if origin and origin not in ORIGINS:
            return JSONResponse({'detail': 'Only the local application origin is allowed'}, status_code=403)
        if request.method in ('POST', 'PUT', 'PATCH'):
            from aidd_worker.config import MAX_UPLOAD_SIZE_BYTES
            total = 0
            chunks = []
            async for chunk in request.stream():
                total += len(chunk)
                if total > MAX_UPLOAD_SIZE_BYTES:
                    return JSONResponse({'detail': 'Request body exceeds the local upload limit'}, status_code=413)
                chunks.append(chunk)
            request._body = b''.join(chunks)
        return await call_next(request)
