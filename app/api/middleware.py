from __future__ import annotations

import time
import uuid
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.config.settings import Settings
from app.domain.models.category import CategoryClassificationResult
from app.domain.models.validated_bill import BillValidationResult


def apply_production_middleware(app: FastAPI, settings: Settings) -> None:
    origins = settings.cors_origins_list
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestContextMiddleware)


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        started = time.perf_counter()
        response: Response = await call_next(request)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time-Ms"] = str(elapsed_ms)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response


def build_support_gate(
    *,
    validation: BillValidationResult,
    classification: CategoryClassificationResult,
) -> dict[str, Any]:
    """
    Soft→hard product gate for Karnataka/BESCOM domestic pipeline.

    Returns whether money engines (tariff/savings/solar/VNM/GNM) should be offered.
    """
    not_bescom = any(
        i.code == "NOT_BESCOM_BILL" for i in validation.issues
    ) or (validation.bill.is_bescom_bill.value is False)

    domestic_ok = classification.can_continue_domestic_pipeline
    supported = (not not_bescom) and domestic_ok

    reasons: list[str] = []
    if not_bescom:
        reasons.append(
            "This document does not appear to be a BESCOM / Karnataka bill. "
            "Tariff, Gruha Jyothi, solar, VNM and GNM engines are Karnataka-only in v1."
        )
    if not domestic_ok:
        reasons.append(
            classification.user_message
            or "Category is not supported for the domestic analysis pipeline."
        )

    return {
        "supported_for_money_engines": supported,
        "is_bescom_bill": (
            None
            if validation.bill.is_bescom_bill.value is None
            else bool(validation.bill.is_bescom_bill.value)
        ),
        "can_continue_domestic_analysis": domestic_ok,
        "block_reasons": reasons,
        "user_guidance": _user_guidance(
            supported=supported,
            not_bescom=not_bescom,
            domestic_ok=domestic_ok,
            validation=validation,
        ),
    }


def _user_guidance(
    *,
    supported: bool,
    not_bescom: bool,
    domestic_ok: bool,
    validation: BillValidationResult,
) -> str:
    if supported:
        return "Bill appears eligible for BESCOM domestic analysis engines."
    bill = validation.bill
    discom = (bill.discom.value or bill.utility.value or "").upper()
    bescom_hint = (
        not not_bescom
        or bill.is_bescom_bill.value is True
        or "BESCOM" in discom
    )
    if bescom_hint and not domestic_ok:
        return (
            "BESCOM appears on this bill, but category or tariff could not be "
            "confirmed automatically (common with partial photos). Complete the "
            "review form — enter tariff code, account/RR, and confirm domestic category."
        )
    if bescom_hint and not_bescom:
        return (
            "This may be a BESCOM bill with incomplete extraction. Set "
            "'BESCOM Bill' to Yes and fill missing required fields in the review form."
        )
    return (
        "Continue with Karnataka BESCOM domestic bills only for savings / VNM / GNM."
    )
