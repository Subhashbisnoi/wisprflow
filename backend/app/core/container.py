"""Process-wide singletons, built once at startup and stored on `app.state.container`."""

from dataclasses import dataclass

from fastapi import Request
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.security import PasswordHasher, TokenService
from app.features.extraction.providers.base import LLMProvider
from app.infrastructure.jobs.base import JobQueue
from app.infrastructure.storage.base import FileStorage


@dataclass
class Container:
    settings: Settings
    session_factory: sessionmaker[Session]
    storage: FileStorage
    job_queue: JobQueue
    llm_provider: LLMProvider
    token_service: TokenService
    password_hasher: PasswordHasher


def get_container(request: Request) -> Container:
    container: Container = request.app.state.container
    return container
