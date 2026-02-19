import uuid
import logging

from django.db import models

logger = logging.getLogger(__name__)


class BiometricEmbedding(models.Model):
    """
    Stores a pre-computed face embedding for one insuree.

    One row per insuree (OneToOneField). When a new embedding is computed
    for an insuree who already has one, the existing row is replaced
    (upsert via services.py).

    The embedding vector is stored as a JSON array of floats. Its dimension
    depends on the model used (e.g. ArcFace → 512 floats, Facenet512 → 512,
    SFace → 128).

    validity_to is set when the embedding is superseded or invalidated
    (e.g. the insuree's reference photo was updated). NULL means currently
    active. This mirrors the soft-delete convention used across openIMIS.
    """

    id = models.AutoField(primary_key=True)
    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_index=True,
    )

    # Lazy FK — avoids a hard import-time dependency on the insuree module.
    insuree = models.OneToOneField(
        "insuree.Insuree",
        on_delete=models.CASCADE,
        related_name="biometric_embedding",
        db_index=True,
    )

    # The embedding vector produced by the model.
    embedding = models.JSONField(
        help_text="Float vector produced by the face recognition model.",
    )

    # Provenance — which model and provider produced this embedding.
    model_name = models.CharField(
        max_length=64,
        help_text="Model used to compute the embedding (e.g. ArcFace, Facenet512).",
    )
    provider = models.CharField(
        max_length=64,
        help_text="Provider that computed the embedding (e.g. deepface, aws_rekognition).",
    )

    # Timestamps
    computed_at = models.DateTimeField(
        auto_now=True,
        help_text="Last time this embedding was (re)computed.",
    )
    validity_from = models.DateTimeField(
        auto_now_add=True,
        help_text="When this embedding became active.",
    )
    validity_to = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="When this embedding was superseded or invalidated. NULL = active.",
    )

    class Meta:
        db_table = "biometric_embedding"
        verbose_name = "Biometric Embedding"
        verbose_name_plural = "Biometric Embeddings"

    def __str__(self):
        return (
            f"BiometricEmbedding(insuree={self.insuree_id}, "
            f"model={self.model_name}, provider={self.provider})"
        )

    @property
    def is_active(self):
        return self.validity_to is None
