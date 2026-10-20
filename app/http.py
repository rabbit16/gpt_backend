from fastapi.responses import JSONResponse, StreamingResponse

CORS_HEADERS = {
    "Access-Control-Expose-Headers": "x-set-cookie",
    "Access-Control-Allow-Credentials": "true",
    "Access-Control-Allow-Origin": "*",
}


def json_response(content, extra_headers=None, status_code=200):
    headers = dict(CORS_HEADERS)
    if extra_headers:
        headers.update(extra_headers)
    return JSONResponse(content=content, headers=headers, status_code=status_code)


def event_stream(generator):
    response = StreamingResponse(generator, media_type="text/event-stream")
    response.headers["Content-Type"] = "text/event-stream"
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["X-Accel-Buffering"] = "no"
    response.headers["Connection"] = "keep-alive"
    return response
