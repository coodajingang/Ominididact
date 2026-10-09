from fastapi import APIRouter, Depends
from auth import verify_api_token
from study.routers import documents, translate, chat, flashcards, notes, export, providers

# Main study router with unified authentication dependency (Item 01 & Item 10)
study_router = APIRouter(dependencies=[Depends(verify_api_token)])

study_router.include_router(documents.router)
study_router.include_router(translate.router)
study_router.include_router(chat.router)
study_router.include_router(flashcards.router)
study_router.include_router(notes.router)
study_router.include_router(export.router)
study_router.include_router(providers.router)

__all__ = ["study_router"]
