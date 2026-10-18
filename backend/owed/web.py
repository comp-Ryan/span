"""Serve the compiled Vite product without shadowing backend or hub routes."""
from pathlib import Path
import re

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

STATIC = Path(__file__).parent / 'static'


def install_frontend(app: FastAPI, directory: Path = STATIC):
    @app.middleware('http')
    async def page_navigation(request, call_next):
        path = request.url.path.rstrip('/')
        is_page = path in ('/home', '/get-paid', '/reports', '/customers') or bool(re.fullmatch(r'/customers/[^/]+', path))
        wants_html = request.headers.get('accept', '').split(',')[0].strip().startswith('text/html')
        if request.method in ('GET', 'HEAD') and is_page and wants_html:
            if not (directory / 'index.html').is_file():
                from fastapi.responses import JSONResponse
                return JSONResponse({'error': {'message': 'Build the frontend before opening a product page'}}, status_code=503)
            return FileResponse(directory / 'index.html', headers={'Cache-Control': 'no-cache', 'Vary': 'Accept'})
        response = await call_next(request)
        if is_page:
            response.headers['Vary'] = ', '.join(filter(None, [response.headers.get('Vary'), 'Accept']))
        return response

    @app.get('/', include_in_schema=False)
    def product():
        if not (directory / 'index.html').is_file():
            return RedirectResponse('/hub')
        return FileResponse(directory / 'index.html', headers={'Cache-Control': 'no-cache'})

    @app.get('/report/{report_id}', include_in_schema=False)
    def report_page(report_id: str):
        if not (directory / 'index.html').is_file():
            raise HTTPException(503, 'Build the frontend before opening a report page')
        return FileResponse(directory / 'index.html', headers={'Cache-Control': 'no-cache'})

    # API routes are registered first. Missing assets/API endpoints remain real 404s,
    # never a misleading 200 HTML SPA fallback. Only compiled files are exposed.
    if directory.is_dir():
        app.mount('/', StaticFiles(directory=directory), name='product-static')
