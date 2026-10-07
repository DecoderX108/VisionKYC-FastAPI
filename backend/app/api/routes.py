from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.errors import KycError
from app.models.schemas import (DocumentResponse, LivenessRequest, LivenessResponse, SessionRequest,
                                VerificationResponse, VerifyDocumentRequest, VerifyFaceRequest)
from app.services.kyc_service import KycService

router = APIRouter(prefix="/api/v1/kyc", tags=["KYC"])
bearer = HTTPBearer(auto_error=False)


def service(request: Request) -> KycService:
    return request.app.state.kyc


def session_token(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> str:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise KycError("authorization_required", "Supply this session's Bearer token", 401)
    return credentials.credentials


Service = Annotated[KycService, Depends(service)]
Token = Annotated[str, Depends(session_token)]


@router.post("/verify-document", response_model=DocumentResponse)
def verify_document(payload: Annotated[VerifyDocumentRequest, Form()], kyc: Service) -> DocumentResponse:
    try:
        data = payload.image.file.read(kyc.settings.max_image_bytes + 1)
        return kyc.verify_document(data, payload.document_type)
    finally:
        payload.image.file.close()


@router.post("/liveness/start", response_model=LivenessResponse)
def start_challenge(payload: SessionRequest, kyc: Service, token: Token) -> LivenessResponse:
    return kyc.start_challenge(payload.document_id, token)


@router.post("/liveness-check", response_model=LivenessResponse)
def liveness_check(payload: LivenessRequest, kyc: Service, token: Token) -> LivenessResponse:
    return kyc.check_liveness(payload, token)


@router.post("/verify-face", response_model=VerificationResponse)
def verify_face(payload: VerifyFaceRequest, kyc: Service, token: Token) -> VerificationResponse:
    return kyc.verify_face(payload, token)


@router.delete("/sessions/{document_id}", status_code=204)
def delete_session(document_id: UUID, kyc: Service, token: Token) -> Response:
    with kyc.store.authorized(document_id, token) as current:
        kyc.store.delete(current)
    return Response(status_code=204)

