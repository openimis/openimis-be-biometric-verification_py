import graphene
from django.core.exceptions import PermissionDenied
from django.utils.translation import gettext as _

from .apps import BiometricVerificationConfig


# ---------------------------------------------------------------------------
# Output types
# ---------------------------------------------------------------------------

class VerificationResultType(graphene.ObjectType):
    """Returned by verifyFace — result of a 1:1 face comparison."""
    verified = graphene.Boolean(required=True)
    confidence = graphene.Float(
        description="Match confidence as a percentage (0–100)."
    )
    distance = graphene.Float(
        description="Raw embedding distance — lower means more similar."
    )
    provider = graphene.String(
        description="Name of the biometric provider that performed the check."
    )
    error = graphene.String(
        description="Error message if verification could not be completed."
    )


class EmbeddingResultType(graphene.ObjectType):
    """Returned by computeInsureeEmbedding — result of pre-computing a face embedding."""
    success = graphene.Boolean(required=True)
    model = graphene.String(
        description="Model name used to compute the embedding (e.g. ArcFace)."
    )
    provider = graphene.String(
        description="Name of the biometric provider that computed the embedding."
    )
    error = graphene.String(
        description="Error message if the embedding could not be computed."
    )


# ---------------------------------------------------------------------------
# Mutations
# ---------------------------------------------------------------------------

class VerifyFaceMutation(graphene.Mutation):
    """
    Compare a live webcam frame (base64 JPEG) against the reference photo
    stored for the given insuree.

    When STORE_EMBEDDINGS is True the reference side uses the pre-computed
    embedding — only the probe (webcam frame) goes through model inference,
    making point-of-service checks significantly faster.
    """

    class Arguments:
        insuree_uuid = graphene.String(
            required=True,
            description="UUID of the insuree whose identity is being verified.",
        )
        frame_b64 = graphene.String(
            required=True,
            description="Base64-encoded JPEG frame captured from the webcam "
                        "(data:image/jpeg;base64,… prefix is accepted).",
        )

    Output = VerificationResultType

    @classmethod
    def mutate(cls, root, info, insuree_uuid, frame_b64):
        user = info.context.user
        if user.is_anonymous:
            raise PermissionDenied(_("unauthorized"))
        if BiometricVerificationConfig.gql_mutation_verify_face_perms:
            if not user.has_perms(BiometricVerificationConfig.gql_mutation_verify_face_perms):
                raise PermissionDenied(_("unauthorized"))

        # Import deferred — service layer may not be available yet during
        # early module loading.
        from .services import BiometricService  # noqa: PLC0415
        return BiometricService.verify_face(
            insuree_uuid=insuree_uuid,
            frame_b64=frame_b64,
            user=user,
        )


class ComputeInsureeEmbeddingMutation(graphene.Mutation):
    """
    Pre-compute and store the face embedding for an insuree's reference photo.
    Call this once at enrollment so that point-of-service verifyFace calls
    only need to run inference on the probe frame.
    """

    class Arguments:
        insuree_uuid = graphene.String(
            required=True,
            description="UUID of the insuree whose embedding should be computed.",
        )

    Output = EmbeddingResultType

    @classmethod
    def mutate(cls, root, info, insuree_uuid):
        user = info.context.user
        if user.is_anonymous:
            raise PermissionDenied(_("unauthorized"))
        if BiometricVerificationConfig.gql_mutation_compute_embedding_perms:
            if not user.has_perms(
                BiometricVerificationConfig.gql_mutation_compute_embedding_perms
            ):
                raise PermissionDenied(_("unauthorized"))

        from .services import BiometricService  # noqa: PLC0415
        return BiometricService.compute_insuree_embedding(
            insuree_uuid=insuree_uuid,
            user=user,
        )


# ---------------------------------------------------------------------------
# Root types — registered by the openIMIS schema aggregator
# ---------------------------------------------------------------------------

class Query(graphene.ObjectType):
    pass


class Mutation(graphene.ObjectType):
    verify_face = VerifyFaceMutation.Field()
    compute_insuree_embedding = ComputeInsureeEmbeddingMutation.Field()
