from __future__ import annotations

import os
from datetime import timedelta

from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes", "on"}


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "development-only-change-me-please")
    DATABASE_PATH = os.getenv("DATABASE_PATH", "data/app.db")
    STORAGE_ROOT = os.getenv("STORAGE_ROOT", "storage")
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_UPLOAD_MB", "25")) * 1024 * 1024
    SESSION_COOKIE_SECURE = _bool("COOKIE_SECURE", True)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Strict"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    SESSION_IDLE_SECONDS = 30 * 60
    LOGIN_WINDOW_SECONDS = 15 * 60
    LOGIN_MAX_FAILURES = 5
    LOGIN_LOCK_SECONDS = 30 * 60
    BEDROCK_ENABLED = _bool("BEDROCK_ENABLED", False)
    AWS_REGION = os.getenv("AWS_REGION", "ap-southeast-2")
    BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "au.anthropic.claude-sonnet-4-6")
    PROMPT_VERSION = os.getenv("PROMPT_VERSION", "2026-08-poc-v1")
    REPORT_TEMPLATE = os.getenv("REPORT_TEMPLATE", "templates/adhd_report_template.docx")
    LIBREOFFICE_BIN = os.getenv("LIBREOFFICE_BIN", "soffice")
    PUBLIC_ORIGIN = os.getenv("PUBLIC_ORIGIN", "https://localhost")
    WORKER_POLL_SECONDS = float(os.getenv("WORKER_POLL_SECONDS", "2"))
