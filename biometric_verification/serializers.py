"""
Django REST Framework serializers for biometric verification module.

Allows mobile apps and frontend to POST facial verification results.
"""

from rest_framework import serializers

from .models import ClaimFacialAudit


class ClaimFacialAuditSerializer(serializers.ModelSerializer):
    """
    Serializer for creating facial audit records from mobile apps or frontend.

    Usage example (POST request):
    {
        "claim": "uuid-or-id",
        "service": "uuid-or-id",  # optional
        "similarity_score": 0.85,
        "threshold_used": 0.68,
        "is_verified": true,
        "step_name": "reception",
        "device_id": "tablet-001",
        "metadata": {
            "provider": "deepface",
            "model_name": "ArcFace",
            "capture_quality": "high"
        }
    }
    """

    class Meta:
        model = ClaimFacialAudit
        fields = [
            'uuid',
            'claim',
            'service',
            'similarity_score',
            'threshold_used',
            'is_verified',
            'step_name',
            'device_id',
            'audit_date',
            'metadata',
        ]
        read_only_fields = ['uuid', 'audit_date']

    def validate_similarity_score(self, value):
        """Ensure similarity score is between 0.0 and 1.0"""
        if not 0.0 <= value <= 1.0:
            raise serializers.ValidationError(
                "Similarity score must be between 0.0 and 1.0"
            )
        return value

    def validate_threshold_used(self, value):
        """Ensure threshold is between 0.0 and 1.0"""
        if not 0.0 <= value <= 1.0:
            raise serializers.ValidationError(
                "Threshold must be between 0.0 and 1.0"
            )
        return value

    def validate(self, data):
        """
        Cross-field validation: Ensure is_verified matches the comparison
        of similarity_score and threshold_used.
        """
        similarity_score = data.get('similarity_score')
        threshold_used = data.get('threshold_used')
        is_verified = data.get('is_verified')

        if similarity_score is not None and threshold_used is not None:
            expected_verified = similarity_score >= threshold_used
            if is_verified != expected_verified:
                raise serializers.ValidationError(
                    f"is_verified={is_verified} is inconsistent with "
                    f"similarity_score={similarity_score} >= threshold={threshold_used}"
                )

        return data


class ClaimRiskAssessmentSerializer(serializers.Serializer):
    """
    Serializer for returning claim risk assessment results.

    Read-only serializer for GET requests to retrieve risk scores.
    """

    risk_score = serializers.FloatField(
        help_text="Fraud risk score from 0.0 (safe) to 1.0 (suspected fraud)"
    )
    risk_level = serializers.ChoiceField(
        choices=['UNKNOWN', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'],
        help_text="Risk category"
    )
    audit_count = serializers.IntegerField(
        help_text="Total number of facial audits for this claim"
    )
    failed_audits = serializers.IntegerField(
        help_text="Number of failed verifications"
    )
    score_variance = serializers.FloatField(
        help_text="Variance in similarity scores across audits"
    )
    avg_similarity = serializers.FloatField(
        help_text="Average similarity score across all audits"
    )
    message = serializers.CharField(
        required=False,
        help_text="Additional information message"
    )
