"""ASGI entrypoint for hosts that import a module-level `app` (Vercel, gunicorn, etc.).

Local development keeps using the factory: `uvicorn app.main:create_app --factory`.
"""

from app.main import create_app

app = create_app()
