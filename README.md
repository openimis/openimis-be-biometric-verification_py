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

## License

LGPL-3.0 — consistent with openIMIS module licensing.
