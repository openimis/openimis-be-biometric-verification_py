"""
Unit tests for schema.py

Covers:
- VerifyFaceMutation.mutate():
    - Anonymous user → PermissionDenied
    - Authenticated user, no perms required (empty list) → service called
    - Authenticated user, perms required + user has them → service called
    - Authenticated user, perms required + user lacks them → PermissionDenied
- ComputeInsureeEmbeddingMutation.mutate():
    - Same four permission variants
- Service result forwarded as-is to GraphQL caller
"""
from unittest.mock import MagicMock, patch

from django.core.exceptions import PermissionDenied
from django.test import TestCase

from biometric_verification.schema import (
    ComputeInsureeEmbeddingMutation,
    VerifyFaceMutation,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_info(user):
    """Minimal GraphQL ResolveInfo stub with a .context.user."""
    info = MagicMock()
    info.context.user = user
    return info


def _anon_user():
    user = MagicMock()
    user.is_anonymous = True
    return user


def _auth_user(has_perms=True):
    user = MagicMock()
    user.is_anonymous = False
    user.has_perms.return_value = has_perms
    return user


def _mock_verify_result(verified=True):
    result = MagicMock()
    result.verified = verified
    result.confidence = 95.0
    result.distance = 0.05
    result.provider = "stub"
    result.error = None
    return result


def _mock_embedding_result(success=True):
    result = MagicMock()
    result.success = success
    result.model = "ArcFace"
    result.provider = "deepface"
    result.error = None
    return result


# ---------------------------------------------------------------------------
# VerifyFaceMutation
# ---------------------------------------------------------------------------

class TestVerifyFaceMutation(TestCase):

    # --- permission guard ---

    def test_anonymous_user_raises_permission_denied(self):
        with self.assertRaises(PermissionDenied):
            VerifyFaceMutation.mutate(
                None,
                _make_info(_anon_user()),
                insuree_uuid="some-uuid",
                frame_b64="abc123",
            )

    @patch("biometric_verification.schema.BiometricVerificationConfig")
    @patch("biometric_verification.services.BiometricService")
    def test_authenticated_no_perms_required_calls_service(
        self, mock_service, mock_cfg
    ):
        mock_cfg.gql_mutation_verify_face_perms = []  # no perms required
        mock_service.verify_face.return_value = _mock_verify_result()

        user = _auth_user()
        result = VerifyFaceMutation.mutate(
            None,
            _make_info(user),
            insuree_uuid="insuree-uuid",
            frame_b64="abc123",
        )

        mock_service.verify_face.assert_called_once_with(
            insuree_uuid="insuree-uuid",
            frame_b64="abc123",
            user=user,
        )
        self.assertTrue(result.verified)

    @patch("biometric_verification.schema.BiometricVerificationConfig")
    @patch("biometric_verification.services.BiometricService")
    def test_authenticated_with_required_perms_calls_service(
        self, mock_service, mock_cfg
    ):
        mock_cfg.gql_mutation_verify_face_perms = ["biometric.verify"]
        mock_service.verify_face.return_value = _mock_verify_result()

        user = _auth_user(has_perms=True)
        result = VerifyFaceMutation.mutate(
            None,
            _make_info(user),
            insuree_uuid="insuree-uuid",
            frame_b64="abc123",
        )

        user.has_perms.assert_called_once_with(["biometric.verify"])
        mock_service.verify_face.assert_called_once()
        self.assertTrue(result.verified)

    @patch("biometric_verification.schema.BiometricVerificationConfig")
    def test_authenticated_missing_perms_raises_permission_denied(self, mock_cfg):
        mock_cfg.gql_mutation_verify_face_perms = ["biometric.verify"]

        user = _auth_user(has_perms=False)
        with self.assertRaises(PermissionDenied):
            VerifyFaceMutation.mutate(
                None,
                _make_info(user),
                insuree_uuid="insuree-uuid",
                frame_b64="abc123",
            )

    # --- result forwarding ---

    @patch("biometric_verification.schema.BiometricVerificationConfig")
    @patch("biometric_verification.services.BiometricService")
    def test_service_error_result_forwarded(self, mock_service, mock_cfg):
        mock_cfg.gql_mutation_verify_face_perms = []
        error_result = _mock_verify_result(verified=False)
        error_result.error = "insuree not found"
        mock_service.verify_face.return_value = error_result

        result = VerifyFaceMutation.mutate(
            None,
            _make_info(_auth_user()),
            insuree_uuid="bad-uuid",
            frame_b64="abc123",
        )

        self.assertFalse(result.verified)
        self.assertEqual(result.error, "insuree not found")


# ---------------------------------------------------------------------------
# ComputeInsureeEmbeddingMutation
# ---------------------------------------------------------------------------

class TestComputeInsureeEmbeddingMutation(TestCase):

    # --- permission guard ---

    def test_anonymous_user_raises_permission_denied(self):
        with self.assertRaises(PermissionDenied):
            ComputeInsureeEmbeddingMutation.mutate(
                None,
                _make_info(_anon_user()),
                insuree_uuid="some-uuid",
            )

    @patch("biometric_verification.schema.BiometricVerificationConfig")
    @patch("biometric_verification.services.BiometricService")
    def test_authenticated_no_perms_required_calls_service(
        self, mock_service, mock_cfg
    ):
        mock_cfg.gql_mutation_compute_embedding_perms = []
        mock_service.compute_insuree_embedding.return_value = _mock_embedding_result()

        user = _auth_user()
        result = ComputeInsureeEmbeddingMutation.mutate(
            None,
            _make_info(user),
            insuree_uuid="insuree-uuid",
        )

        mock_service.compute_insuree_embedding.assert_called_once_with(
            insuree_uuid="insuree-uuid",
            user=user,
        )
        self.assertTrue(result.success)

    @patch("biometric_verification.schema.BiometricVerificationConfig")
    @patch("biometric_verification.services.BiometricService")
    def test_authenticated_with_required_perms_calls_service(
        self, mock_service, mock_cfg
    ):
        mock_cfg.gql_mutation_compute_embedding_perms = ["biometric.compute"]
        mock_service.compute_insuree_embedding.return_value = _mock_embedding_result()

        user = _auth_user(has_perms=True)
        result = ComputeInsureeEmbeddingMutation.mutate(
            None,
            _make_info(user),
            insuree_uuid="insuree-uuid",
        )

        user.has_perms.assert_called_once_with(["biometric.compute"])
        mock_service.compute_insuree_embedding.assert_called_once()
        self.assertTrue(result.success)
        self.assertEqual(result.model, "ArcFace")
        self.assertEqual(result.provider, "deepface")

    @patch("biometric_verification.schema.BiometricVerificationConfig")
    def test_authenticated_missing_perms_raises_permission_denied(self, mock_cfg):
        mock_cfg.gql_mutation_compute_embedding_perms = ["biometric.compute"]

        user = _auth_user(has_perms=False)
        with self.assertRaises(PermissionDenied):
            ComputeInsureeEmbeddingMutation.mutate(
                None,
                _make_info(user),
                insuree_uuid="insuree-uuid",
            )

    # --- result forwarding ---

    @patch("biometric_verification.schema.BiometricVerificationConfig")
    @patch("biometric_verification.services.BiometricService")
    def test_service_error_result_forwarded(self, mock_service, mock_cfg):
        mock_cfg.gql_mutation_compute_embedding_perms = []
        error_result = _mock_embedding_result(success=False)
        error_result.error = "no reference photo"
        mock_service.compute_insuree_embedding.return_value = error_result

        result = ComputeInsureeEmbeddingMutation.mutate(
            None,
            _make_info(_auth_user()),
            insuree_uuid="bad-uuid",
        )

        self.assertFalse(result.success)
        self.assertEqual(result.error, "no reference photo")
