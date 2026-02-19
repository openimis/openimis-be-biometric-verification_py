# CLAUDE.md — openimis-be-biometric_verification

## Project Summary

This module adds **biometric identity verification** to openIMIS using face recognition. The primary use case is verifying an insuree's identity at point of service by comparing a live webcam frame against the reference photo stored at enrollment.

The architecture uses a **provider pattern**: DeepFace is the default local provider, but any external licensed API (AWS Rekognition, Azure Face API, Neurotechnology, etc.) can be plugged in via configuration without touching the module code.

---

## Key Decisions

- **Module name**: `openimis-be-biometric_verification` 
- **Default local provider**: DeepFace with ArcFace model
  - Actively maintained (2024 research publication)
  - Wraps multiple best-in-class models: ArcFace, Facenet512, GhostFaceNet, Buffalo_L (InsightFace's model), SFace
  - Pure pip install, no separate service needed
  - **InsightFace pip package was rejected** — last PyPI release December 2022, stale for production use
- **Video stream strategy**: Single frame capture + GraphQL mutation (no WebSocket needed for openIMIS point-of-service use case)
- **Embedding storage**: Pre-compute and store face embeddings at enrollment in a `JSONField` on the insuree record — verification at service point becomes a vector comparison, not a full model inference
- **No FastAPI**: Uses Django views + GraphQL mutations (existing openIMIS stack)

---

## Module Structure

```
openimis-be-biometric_verification_py/
├── biometric_verification/
│   ├── apps.py
│   ├── schema.py              # GraphQL mutations: VerifyFace, ComputeEmbedding
│   ├── services.py            # Facade: routes to active provider
│   ├── registry.py            # Provider registry (auto-registers built-ins)
│   ├── providers/
│   │   ├── base.py            # Abstract interface ALL providers must implement
│   │   ├── deepface_provider.py
│   │   └── external/
│   │       ├── aws_provider.py
│   │       ├── azure_provider.py
│   │       └── custom_provider.py   # Template for licensed 3rd-party SDKs
│   ├── models.py              # BiometricEmbedding model (stores embeddings per insuree)
│   ├── migrations/
│   └── urls.py
├── requirements.txt
├── README.md
└── setup.py
```

---

## Provider Interface Contract

Every provider must implement `base.BaseBiometricProvider`:

```python
class BaseBiometricProvider(ABC):

    provider_name: str

    @abstractmethod
    def verify(probe_image, reference_image, threshold=None) -> VerificationResult:
        # Returns: verified (bool), confidence (0-100), distance (float), provider (str)
        pass

    @abstractmethod
    def get_embedding(image) -> BiometricEmbedding:
        # Returns: vector (list[float]), model (str), provider (str)
        pass

    def verify_from_embedding(probe_image, reference_embedding) -> VerificationResult:
        # Default: recomputes probe embedding and does cosine distance
        # Override if the provider has a native optimized path
        pass

    def health_check() -> bool:
        pass
```

`VerificationResult` fields: `verified`, `confidence`, `distance`, `provider`, `metadata`, `error`

---

## DeepFace Provider Configuration

DeepFace wraps multiple models — configure via `settings.py`:

| Model | Accuracy | Speed (CPU) | Notes |
|---|---|---|---|
| `ArcFace` | ⭐⭐⭐⭐⭐ | Medium | **Recommended default** |
| `Facenet512` | ⭐⭐⭐⭐ | Medium | Good balance |
| `Buffalo_L` | ⭐⭐⭐⭐⭐ | Medium | InsightFace model via DeepFace |
| `GhostFaceNet` | ⭐⭐⭐⭐ | Fast | Best for CPU-constrained deployments |
| `SFace` | ⭐⭐⭐ | Very fast | Minimum viable, edge devices |

```python
# settings.py
BIOMETRIC_VERIFICATION = {
    "PROVIDER": "deepface",
    "PROVIDER_CONFIG": {
        "model_name": "ArcFace",          # swap model here, no code change
        "detector_backend": "opencv",     # opencv | retinaface | mtcnn
    },
    "STORE_EMBEDDINGS": True,             # pre-compute at enrollment
    "SIMILARITY_THRESHOLD": 0.68,        # tune per deployment context
    "MAX_IMAGE_SIZE_PX": 1024,
}
```

**Important**: DeepFace loads the model into memory on first call (~3-5s). This happens once at worker startup — not on every request.

---

## GraphQL API

### Mutation: `verifyFace`
Compares a base64 webcam frame against the stored reference for an insuree.

```graphql
mutation {
  verifyFace(insureeUuid: "...", frameB64: "data:image/jpeg;base64,...") {
    verified
    confidence
    provider
    error
  }
}
```

### Mutation: `computeEmbedding`
Pre-computes and stores the embedding for an insuree photo (call at enrollment).

```graphql
mutation {
  computeInsureeEmbedding(insureeUuid: "...") {
    success
    model
    error
  }
}
```

---

## Data Model

```python
class BiometricEmbedding(models.Model):
    insuree = models.OneToOneField("insuree.Insuree", on_delete=models.CASCADE)
    embedding = models.JSONField()          # float vector
    model_name = models.CharField(max_length=64)
    provider = models.CharField(max_length=64)
    computed_at = models.DateTimeField(auto_now=True)
    validity_from = models.DateTimeField(auto_now_add=True)
    validity_to = models.DateTimeField(null=True, blank=True)
```

When `STORE_EMBEDDINGS=True`, `verifyFace` uses the stored embedding for the reference side — model inference only runs on the probe (webcam frame). This is significantly faster at scale.

---

## Frontend Integration (React)

The browser captures a single JPEG frame from the webcam and sends it as base64 via Apollo GraphQL mutation. No WebSocket, no streaming infrastructure needed.

```jsx
// Capture frame from <video> element
const canvas = document.createElement("canvas");
canvas.getContext("2d").drawImage(videoRef.current, 0, 0);
const frameB64 = canvas.toDataURL("image/jpeg", 0.8);

// Send via Apollo
await verifyFace({ variables: { insureeUuid, frameB64 } });
```

---

## Adding a New Provider (External / Licensed)

1. Create `providers/external/my_provider.py`
2. Extend `BaseBiometricProvider`, implement `verify()` and `get_embedding()`
3. Register in `registry.py`:
   ```python
   ProviderRegistry.register("my_provider", MyProvider)
   ```
4. Update `settings.py`:
   ```python
   BIOMETRIC_VERIFICATION = {
       "PROVIDER": "my_provider",
       "PROVIDER_CONFIG": { ... }
   }
   ```

No other code changes required.

---

## Dependencies

```
# requirements.txt
deepface>=0.0.93
opencv-python-headless>=4.9.0
tf-keras                        # or tensorflow
numpy

# Optional — only if using external providers
boto3                           # AWS Rekognition
azure-cognitiveservices-vision-face  # Azure
```

---

## Performance Notes

- **Enrollment**: `computeEmbedding` runs once per insuree, stores the vector. ~1-3s per photo.
- **Verification**: With stored embeddings, only the probe frame goes through model inference. ~200-500ms on CPU.
- **Model warmup**: Add a management command or `AppConfig.ready()` hook to pre-load the DeepFace model at startup and avoid cold-start latency on the first real request.
- **Deployment context**: For CPU-only servers (common in LMIC), prefer `GhostFaceNet` or `SFace` over `ArcFace` if latency is a concern. Tune `SIMILARITY_THRESHOLD` per country — lighting conditions and photo quality at enrollment vary significantly.
