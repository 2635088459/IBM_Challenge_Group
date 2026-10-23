# Member 4 Spec — Document Processing & OCR Lead
**Timeline: 8 hours | Demo: 10:00 AM**

---

## Your Goal
Deliver a document ingestion pipeline that accepts uploaded files, hashes them, extracts fields via OCR, runs a D2 field-level consistency check (quantity/SKU/price across Invoice and Packing List), and exposes evidence-classified results to M1's agent and M3's dashboard.

---

## Hour-by-Hour Tasks

### Hour 0–1 — Setup
- [ ] Clone repo, confirm Python 3.12 + virtual env
- [ ] Install: `pytesseract`, `Pillow`, `pdf2image`, `fastapi`, `pydantic`, `hashlib` (stdlib)
- [ ] Confirm Tesseract binary is installed: `tesseract --version`
  - macOS: `brew install tesseract`
  - Ubuntu: `apt-get install tesseract-ocr`
- [ ] Agree with M2 on the `documents` table schema and the `evidence_store` structure

### Hour 1–3 — Document Ingestion Endpoint

#### `POST /api/documents/upload`
- [ ] Accept multipart file upload (`doc_type` field required: `INVOICE` | `PACKING_LIST` | `BILL_OF_LADING`)
- [ ] Compute **SHA-256 hash** of raw file bytes
- [ ] Check `documents` table (via M2's DB) for existing hash — if match found, return existing record (deduplication)
- [ ] Save raw file to `evidence_store/raw/{shipment_id}/{doc_type}_{hash[:8]}.pdf`
- [ ] Insert record into `documents` table with `status = "raw"`, `version = 1`
- [ ] Return: `{ doc_id, file_hash, doc_type, version, status }`

#### SHA-256 Versioning
- [ ] If same `doc_type` for same `shipment_id` already exists, increment `version`
- [ ] Old version stays in DB — new version becomes `current`

### Hour 1–3 — OCR Extraction

#### `POST /api/documents/{doc_id}/extract`
- [ ] Load file from `evidence_store/raw/`
- [ ] Convert PDF pages to images with `pdf2image`
- [ ] Run `pytesseract.image_to_data()` on each page
- [ ] Parse extracted text to pull key fields:

**For `INVOICE`:**
```
line_sku, line_quantity, unit_price, total_amount, invoice_number, shipper_name
```

**For `PACKING_LIST`:**
```
line_sku, line_quantity, package_count, gross_weight
```

**For `BILL_OF_LADING`:**
```
bl_number, vessel_name, port_of_loading, port_of_discharge, shipper_name
```

- [ ] Save extracted fields to `evidence_store/extracted/{doc_id}.json`
- [ ] Update `documents.status = "extracted"` in DB
- [ ] Return: `{ doc_id, extracted_fields, confidence_scores }`

### Hour 3–6 — D2 Field-Level Consistency Check

#### `POST /api/documents/consistency-check`
Request body: `{ shipment_id, invoice_doc_id, packing_list_doc_id }`

- [ ] Load extracted fields for both documents
- [ ] Compare these D2 fields line-by-line:

| Field | Invoice value | Packing List value | Match? |
|-------|---------------|-------------------|--------|
| `line_sku` | from invoice | from packing list | must match |
| `line_quantity` | from invoice | from packing list | must match |
| `unit_price` | from invoice | — | N/A for PL |

- [ ] For each mismatch, produce a `discrepancy` object:
  ```json
  {
    "field": "line_quantity",
    "invoice_value": 500,
    "packing_list_value": 480,
    "delta": 20,
    "severity": "HIGH"
  }
  ```
- [ ] If any mismatches found: emit an `DOCUMENT_DISCREPANCY_DETECTED` event via `POST /api/events` (M2's endpoint)
- [ ] Save consistency report to `evidence_store/verified/{shipment_id}_consistency.json`
- [ ] Update document status to `"verified"` for both docs
- [ ] Return: `{ shipment_id, mismatches: [...], overall_status: "PASS" | "FAIL" }`

### Hour 3–6 — Synthetic Test Documents (for Demo Seed)

Create synthetic test files that produce the C01 and C02 scenarios:

- [ ] `test_data/SHP-001/invoice_missing.txt` — placeholder showing "no invoice uploaded"
- [ ] `test_data/SHP-002/invoice_qty500.pdf` — synthetic invoice with `line_quantity: 500`
- [ ] `test_data/SHP-002/packing_list_qty480.pdf` — synthetic PL with `line_quantity: 480`

Since real OCR on synthetic PDFs can be unreliable, also create **pre-extracted JSON fixtures**:
- [ ] `test_data/SHP-002/invoice_extracted.json`
- [ ] `test_data/SHP-002/packing_list_extracted.json`

The consistency check endpoint should accept `use_fixture=true` param for demo mode.

### Hour 6–7.5 — Evidence Store API

#### `GET /api/evidence/{shipment_id}`
- [ ] Return evidence chain for all documents of a shipment:
  ```json
  {
    "shipment_id": "...",
    "documents": [
      {
        "doc_id": "...",
        "doc_type": "INVOICE",
        "chain": [
          { "stage": "raw",       "file_hash": "abc123", "timestamp": "..." },
          { "stage": "extracted", "fields": {...},        "timestamp": "..." },
          { "stage": "verified",  "consistency": "FAIL",  "timestamp": "..." }
        ]
      }
    ]
  }
  ```
- [ ] This is what M3's **Evidence Trail panel** displays

### Hour 7.5–8 — Demo Rehearsal
- [ ] Run C02 consistency check manually: Invoice 500 vs PL 480 → discrepancy detected
- [ ] Confirm `DOCUMENT_DISCREPANCY_DETECTED` event is created and visible via M2's audit log
- [ ] Confirm M3's evidence trail panel shows the 3-stage chain for SHP-002

---

## Key Files to Create

```
documents/
  router.py              # FastAPI routes: upload, extract, consistency-check, evidence
  ocr.py                 # Tesseract extraction logic per doc_type
  hasher.py              # SHA-256 file hash + deduplication logic
  consistency.py         # D2 field-level compare logic
  evidence_store.py      # Read/write raw/extracted/verified files
test_data/
  SHP-001/               # Missing invoice fixture
  SHP-002/
    invoice_extracted.json
    packing_list_extracted.json
tests/
  test_consistency.py    # Unit tests: qty match, qty mismatch, sku mismatch
  test_hasher.py         # Hash deduplication test
```

---

## Interfaces You Expose (consumed by M1 and M3)

| Endpoint | Purpose |
|----------|---------|
| `POST /api/documents/upload` | Upload + hash a document |
| `POST /api/documents/{doc_id}/extract` | Run OCR extraction |
| `POST /api/documents/consistency-check` | D2 field comparison |
| `GET /api/evidence/{shipment_id}` | Evidence chain for M3 dashboard |

---

## Interfaces You Depend On (from M2)

| What | How |
|------|-----|
| Insert document record | Direct DB write via shared SQLAlchemy session |
| Emit discrepancy event | `POST /api/events` with `event_type: DOCUMENT_DISCREPANCY_DETECTED` |

---

## Definition of Done
- [ ] File upload computes and stores SHA-256 hash
- [ ] Duplicate upload (same hash) returns existing record, does not create duplicate
- [ ] OCR extraction runs on a PDF and returns structured fields (or fixture fields in demo mode)
- [ ] D2 consistency check correctly detects qty=500 vs qty=480 mismatch for SHP-002
- [ ] `DOCUMENT_DISCREPANCY_DETECTED` event is created in DB on mismatch
- [ ] `GET /api/evidence/SHP-002` returns 3-stage chain (raw → extracted → verified)
- [ ] `pytest tests/test_consistency.py` passes
