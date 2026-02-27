# openimis-be-biometric_verification

Biometric identity verification module for [openIMIS](https://openimis.org). Verifies an insuree's identity at point of service by comparing a live webcam capture against the reference photo stored at enrollment.

Built with a **provider pattern** — DeepFace is the default local engine, but any external licensed API can be swapped in via configuration.

---

## Features

- 1:1 face verification (probe vs. stored reference photo)
- Pre-computed embedding storage for fast point-of-service verification
- Pluggable provider architecture: local (DeepFace) or external (AWS, Azure, custom licensed SDK)
- GraphQL API — no new REST endpoints, integrates with existing openIMIS stack
- Configurable model and threshold per deployment context

---

## Quick Start

```bash
pip install openimis-be-biometric_verification
```

Add to `openimis.json`:
```json
{
  "modules": ["biometric_verification"]
}
```

Configure in `settings.py`:
```python
BIOMETRIC_VERIFICATION = {
    "PROVIDER": "deepface",
    "PROVIDER_CONFIG": {
        "model_name": "ArcFace",
        "detector_backend": "opencv"
    },
    "STORE_EMBEDDINGS": True,
    "SIMILARITY_THRESHOLD": 0.68,
}
```

Run migrations:
```bash
python manage.py migrate biometric_verification
```

---

## Usage

**At enrollment** — pre-compute and store the insuree's face embedding:
```graphql
mutation {
  computeInsureeEmbedding(insureeUuid: "...") {
    success
    model
  }
}
```

**At point of service** — verify identity from a webcam frame:
```graphql
mutation {
  verifyFace(insureeUuid: "...", frameB64: "data:image/jpeg;base64,...") {
    verified
    confidence
    provider
  }
}
```

---

## Switching Providers

Change `PROVIDER` in `settings.py` — no code changes needed:

| Value | Description |
|---|---|
| `deepface` | Local inference via DeepFace (default) |
| `aws_rekognition` | AWS Rekognition cloud API |
| `azure_face` | Azure Face API |
| Custom | Any class implementing `BaseBiometricProvider` |

See `CLAUDE.md` for full provider implementation guide.

---

## Requirements

- Python 3.8+
- openIMIS backend (Django)
- `deepface`, `opencv-python-headless`, `tf-keras`

---

## TODO / Known Limitations (POC)

### Claim Code Mutability
**Current implementation uses `claim_code` to link facial audits to claims during the verification flow.**

⚠️ **POC Limitation:** The claim code (`claim.code`) can potentially be modified during the claim processing workflow. If the code changes after facial audits are created, those audits will remain linked via the foreign key to the claim record (by ID), but the code used for lookup during WebSocket verification will no longer match.

**Production recommendation:** Switch to using `claim.uuid` instead of `claim.code` for linking facial audits, as UUIDs are immutable and more reliable for foreign key relationships. The current implementation prioritizes the QR code workflow where the claim code is more user-visible, but this comes at the cost of potential lookup failures if codes are reassigned.

**Affected files:**
- `consumers/biometric_consumer.py` — `_create_facial_audit()` method
- Frontend QR code dialog and verification page

---

## License

LGPL-3.0 — consistent with openIMIS module licensing.
