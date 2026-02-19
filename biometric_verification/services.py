import base64
import logging
import os

from .providers.base import VerificationResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# GraphQL adapter objects
# schema.py declares Output = VerificationResultType / EmbeddingResultType.
# Graphene resolves those types by reading attributes — plain objects with the
# right attribute names are enough; no need to import the graphene type here.
# ---------------------------------------------------------------------------

class _VerifyFaceResult:
    __slots__ = ("verified", "confidence", "distance", "provider", "error")

    def __init__(self, result: VerificationResult):
        self.verified = result.verified
        self.confidence = result.confidence
        self.distance = result.distance
        self.provider = result.provider
        self.error = result.error


class _EmbeddingResult:
    __slots__ = ("success", "model", "provider", "error")

    def __init__(self, success: bool, model=None, provider=None, error=None):
        self.success = success
        self.model = model
        self.provider = provider
        self.error = error


# ---------------------------------------------------------------------------
# BiometricService
# ---------------------------------------------------------------------------

class BiometricService:
    """
    Facade between the GraphQL mutations and the provider layer.

    All business logic lives here so that schema.py stays thin and
    providers stay stateless (pure image-in / result-out).
    """

    # ------------------------------------------------------------------
    # Public API — called by schema.py mutations
    # ------------------------------------------------------------------

    @staticmethod
    def verify_face(insuree_uuid: str, frame_b64: str, user) -> _VerifyFaceResult:
        """
        Verify an insuree's identity from a webcam frame.

        Fast path (STORE_EMBEDDINGS=True):
            Uses the stored embedding for the reference side.
            Only the probe (webcam frame) goes through model inference.

        Slow path (no stored embedding or STORE_EMBEDDINGS=False):
            Full image-vs-image comparison via provider.verify().
        """
        try:
            from .registry import ProviderRegistry
            from .apps import BiometricVerificationConfig
            from insuree.models import Insuree

            provider = ProviderRegistry.get_active_provider()
            probe_bytes = BiometricService._decode_frame(frame_b64)

            insuree = Insuree.objects.get(uuid=insuree_uuid, validity_to__isnull=True)

            # Fast path — stored embedding present and active
            if BiometricVerificationConfig.store_embeddings:
                try:
                    stored = insuree.biometric_embedding  # OneToOne reverse accessor
                    if stored.is_active:
                        result = provider.verify_from_embedding(
                            probe_image=probe_bytes,
                            reference_embedding=stored.embedding,
                        )
                        return _VerifyFaceResult(result)
                except Exception:
                    # No stored embedding yet — fall through to slow path
                    logger.debug(
                        "No active embedding for insuree %s, falling back to image comparison.",
                        insuree_uuid,
                    )

            # Slow path — full image-vs-image comparison
            reference_bytes = BiometricService._fetch_insuree_photo(insuree)
            result = provider.verify(
                probe_image=probe_bytes,
                reference_image=reference_bytes,
            )
            return _VerifyFaceResult(result)

        except Exception as exc:
            logger.exception("verify_face failed for insuree %s", insuree_uuid)
            return _VerifyFaceResult(
                VerificationResult(verified=False, error=str(exc))
            )

    @staticmethod
    def compute_insuree_embedding(insuree_uuid: str, user) -> _EmbeddingResult:
        """
        Pre-compute and persist the face embedding for an insuree.

        Invalidates any existing active embedding before storing the new one
        (soft-delete: sets validity_to on the old row).
        """
        try:
            from .registry import ProviderRegistry
            from .models import BiometricEmbedding
            from insuree.models import Insuree
            from django.utils import timezone

            provider = ProviderRegistry.get_active_provider()
            insuree = Insuree.objects.get(uuid=insuree_uuid, validity_to__isnull=True)
            photo_bytes = BiometricService._fetch_insuree_photo(insuree)

            embedding_vector = provider.get_embedding(photo_bytes)
            model_name = getattr(provider, "model_name", "unknown")

            # Invalidate previous active embedding (soft-delete)
            BiometricEmbedding.objects.filter(
                insuree=insuree,
                validity_to__isnull=True,
            ).update(validity_to=timezone.now())

            # Persist new embedding
            BiometricEmbedding.objects.create(
                insuree=insuree,
                embedding=embedding_vector,
                model_name=model_name,
                provider=provider.provider_name,
            )

            logger.info(
                "Computed and stored embedding for insuree %s (model=%s, provider=%s)",
                insuree_uuid,
                model_name,
                provider.provider_name,
            )
            return _EmbeddingResult(
                success=True,
                model=model_name,
                provider=provider.provider_name,
            )

        except Exception as exc:
            logger.exception(
                "compute_insuree_embedding failed for insuree %s", insuree_uuid
            )
            return _EmbeddingResult(success=False, error=str(exc))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _decode_frame(frame_b64: str) -> bytes:
        """
        Decode a base64 image string to raw bytes.
        Strips the optional data URI prefix (data:image/jpeg;base64,…).
        """
        if "," in frame_b64:
            frame_b64 = frame_b64.split(",", 1)[1]
        return base64.b64decode(frame_b64)

    @staticmethod
    def _fetch_insuree_photo(insuree) -> bytes:
        """
        Read the insuree's current reference photo from disk and return raw bytes.

        Uses the same path convention as the insuree module:
            InsureeConfig.insuree_photos_root_path / photo.folder / photo.filename
        """
        from insuree.apps import InsureeConfig

        photo = getattr(insuree, "photo", None)
        if photo is None:
            raise ValueError(
                f"Insuree {insuree.uuid} has no reference photo attached."
            )

        root = InsureeConfig.insuree_photos_root_path
        if not root:
            raise ValueError(
                "InsureeConfig.insuree_photos_root_path is not configured. "
                "Set insuree_photos_root_path in ModuleConfiguration or "
                "the PHOTO_ROOT_PATH environment variable."
            )

        photo_path = os.path.join(root, photo.folder or "", photo.filename or "")
        if not os.path.isfile(photo_path):
            raise FileNotFoundError(
                f"Reference photo not found on disk: {photo_path}"
            )

        with open(photo_path, "rb") as fh:
            return fh.read()
