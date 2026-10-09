"""
Backwards-compatible study router entrypoint.
All sub-domain routes have been modularized under study/routers/ (Item 10).
"""
import study as study_service
from study.routers import study_router

__all__ = ["study_router", "study_service"]
