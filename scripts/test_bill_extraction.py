from __future__ import annotations

import json
import mimetypes
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python scripts/test_bill_extraction.py <bill.jpg|png|pdf>")
        return 1

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"File not found: {path}")
        return 1

    from app.application.use_cases.extract_bill import ExtractBillUseCase
    from app.application.use_cases.upload_bill import UploadBillCommand
    from app.config.settings import get_settings

    settings = get_settings()
    content_type = mimetypes.guess_type(path.name)[0]
    data = path.read_bytes()

    print("=" * 60)
    print("MILESTONE 3 — LIVE BILL EXTRACTION")
    print("=" * 60)
    print(f"file     : {path}")
    print(f"provider : {settings.bill_extraction_provider}")
    print(f"pipeline : {settings.mistral_ocr_model if settings.bill_extraction_provider == 'mistral_ocr' else settings.gemini_model}")
    print(f"bytes    : {len(data)}")

    use_case = ExtractBillUseCase(settings)
    result = use_case.execute(
        UploadBillCommand(
            filename=path.name,
            content_type=content_type,
            data=data,
        )
    )

    payload = {
        "model": result.model_name,
        "document_id": str(result.document.id),
        "needs_confirmation": result.needs_confirmation,
        "confidence_summary": result.extraction.confidence_summary,
        "units_consumed": result.extraction.units_consumed.model_dump(mode="json"),
        "total_amount": result.extraction.total_amount.model_dump(mode="json"),
        "tariff_code": result.extraction.tariff_code.model_dump(mode="json"),
        "consumer_category": result.extraction.consumer_category.model_dump(mode="json"),
        "rr_number": result.extraction.rr_number.model_dump(mode="json"),
        "is_bescom_bill": result.extraction.is_bescom_bill.model_dump(mode="json"),
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    print("=" * 60)
    print("Done. Full extraction also stored in API response via POST /bills/extract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
