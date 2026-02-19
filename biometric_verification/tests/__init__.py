# Import all test cases so that Django's test runner discovers them when
# using the label "biometric_verification.tests" (loadTestsFromName only
# looks at symbols defined in / imported into this __init__.py).
from .test_base_provider import (
    TestVerificationResult,
    TestCosineDistance,
    TestVerifyFromEmbedding,
)
from .test_registry import TestProviderRegistry
from .test_services import (
    TestDecodeFrame,
    TestFetchInsureePhoto,
    TestVerifyFace,
    TestComputeInsureeEmbedding,
)
from .test_schema import (
    TestVerifyFaceMutation,
    TestComputeInsureeEmbeddingMutation,
)
