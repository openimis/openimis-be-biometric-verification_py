"""
WebSocket consumer for real-time biometric face verification.

This consumer receives video frames from the frontend and performs
face verification with time-based sampling to reduce load.
"""

import asyncio
import json
import logging
import time
import zlib
import traceback

from channels.generic.websocket import AsyncConsumer
from asgiref.sync import sync_to_async

from ..apps import BiometricVerificationConfig
from ..services import BiometricService

logger = logging.getLogger(__name__)


class BiometricVerificationConsumer(AsyncConsumer):
    """
    WebSocket consumer for streaming biometric verification.

    Protocol:
    - Client sends frames: {"type": "frame", "insuree_uuid": "...", "frame": "base64..."}
    - Server responds: {"type": "verification_result", "verified": true/false, ...}

    Time-based sampling:
    - Frames are received continuously
    - Verification only runs every SAMPLING_INTERVAL_SECONDS (default: 5)
    - This reduces CPU load while maintaining responsive UX
    """

    async def websocket_connect(self, event):
        """
        Handle new WebSocket connection.
        Initialize state and authenticate if required.
        """
        logger.info("BiometricVerificationConsumer: Client connected")

        # Accept the WebSocket connection
        await self.send({"type": "websocket.accept"})

        # Authenticate connection
        try:
            await self._authenticate_connection()
        except ConnectionError as e:
            logger.warning(f"Authentication failed: {e}")
            return

        # Initialize verification state
        self.last_verification_time = 0
        self.verification_count = 0
        self.frame_count = 0

        # Send connection success message
        await self.send({
            "type": "websocket.send",
            "text": json.dumps({
                "type": "connected",
                "message": "WebSocket connection established",
                "sampling_interval": BiometricVerificationConfig.sampling_interval_seconds,
            })
        })

    async def websocket_receive(self, event):
        """
        Handle incoming WebSocket messages from client.

        Expected message format:
        {
            "type": "frame",
            "insuree_uuid": "uuid-string",
            "frame": "data:image/jpeg;base64,..."
        }
        """
        try:
            payload = self._get_content(event)

            if payload.get('type') == 'frame':
                self.frame_count += 1
                await self._handle_frame(payload)
            else:
                logger.warning(f"Unknown message type: {payload.get('type')}")

        except Exception as e:
            logger.error(f"Error processing message: {e}")
            logger.debug(traceback.format_exc())
            await self._send_error(str(e))

    async def websocket_disconnect(self, event):
        """Handle WebSocket disconnection."""
        logger.info(f"BiometricVerificationConsumer: Client disconnected "
                   f"(verified {self.verification_count} times, "
                   f"received {self.frame_count} frames)")

    def _get_content(self, event):
        """
        Extract and parse message content.
        Supports both compressed (bytes) and uncompressed (text) messages.
        """
        # Try compressed bytes first (like claim_ai)
        bytes_data = event.get('bytes', None)
        if bytes_data:
            try:
                bytes_data = zlib.decompress(bytes_data)
            except Exception:
                pass  # Not compressed
            return json.loads(bytes_data.decode("utf-8"))

        # Fallback to text
        text_data = event.get('text', None)
        if text_data:
            return json.loads(text_data)

        raise ValueError("Message contains neither 'text' nor 'bytes'")

    async def _handle_frame(self, payload):
        """
        Process incoming video frame with time-based sampling.

        Only performs verification if SAMPLING_INTERVAL_SECONDS has elapsed
        since last verification. This prevents overwhelming the CPU with
        face recognition on every single frame.
        """
        current_time = time.time()

        # Time-based sampling: Check if enough time has passed
        sampling_interval = BiometricVerificationConfig.sampling_interval_seconds
        time_since_last_verification = current_time - self.last_verification_time

        if time_since_last_verification < sampling_interval:
            # Skip this frame - too soon since last verification
            logger.debug(f"Skipping frame (last verification {time_since_last_verification:.1f}s ago, "
                        f"threshold {sampling_interval}s)")
            return

        # Perform verification
        await self._perform_verification(payload, current_time)

    async def _perform_verification(self, payload, current_time):
        """
        Run face verification and send result back to client.

        Also creates a ClaimFacialAudit record if claim_code is provided.
        """
        logger.info(f"_perform_verification called at {current_time}")

        insuree_uuid = payload.get('insuree_uuid')
        frame_b64 = payload.get('frame')
        claim_code = payload.get('claim_code')  # Claim code from QR scan
        step_name = payload.get('step_name', 'unknown')  # e.g. 'reception', 'consultation'
        service_uuid = payload.get('service_uuid')  # Optional
        device_id = payload.get('device_id', '')  # Optional

        logger.info(f"Processing frame for insuree {insuree_uuid}, claim_code={claim_code}")

        if not insuree_uuid or not frame_b64:
            logger.warning(f"Missing data: insuree_uuid={insuree_uuid}, frame_b64={'present' if frame_b64 else 'missing'}")
            await self._send_error("Missing insuree_uuid or frame in payload")
            return

        try:
            logger.info("Calling BiometricService.verify_face...")
            # Call the BiometricService (synchronous call wrapped for async context)
            # Use sync_to_async to safely call Django ORM from async consumer
            result = await sync_to_async(BiometricService.verify_face)(
                insuree_uuid=insuree_uuid,
                frame_b64=frame_b64,
                user=self.scope.get('user')
            )

            # Update state
            self.last_verification_time = current_time
            self.verification_count += 1

            # Create ClaimFacialAudit record if claim_code is provided
            audit_uuid = None
            logger.info(f"Audit check: claim_code={claim_code}, result.error={result.error}")

            if claim_code and not result.error:
                logger.info(f"Creating facial audit for claim_code={claim_code}, step={step_name}")
                audit_uuid = await self._create_facial_audit(
                    claim_code=claim_code,
                    service_uuid=service_uuid,
                    similarity_score=result.confidence / 100.0,  # Convert percentage to 0-1
                    threshold_used=BiometricVerificationConfig.similarity_threshold,
                    is_verified=result.verified,
                    step_name=step_name,
                    device_id=device_id,
                    provider=result.provider,
                )
                logger.info(f"Facial audit created with UUID: {audit_uuid}")
            else:
                if not claim_code:
                    logger.warning("No claim_code provided - skipping facial audit creation")
                if result.error:
                    logger.warning(f"Verification error present - skipping facial audit: {result.error}")

            # Send result to client
            await self.send({
                "type": "websocket.send",
                "text": json.dumps({
                    "type": "verification_result",
                    "verified": result.verified,
                    "confidence": result.confidence,
                    "distance": result.distance,
                    "provider": result.provider,
                    "error": result.error,
                    "verification_count": self.verification_count,
                    "frame_count": self.frame_count,
                    "timestamp": current_time,
                    "audit_uuid": str(audit_uuid) if audit_uuid else None,
                })
            })

            logger.info(
                f"Verification #{self.verification_count} for {insuree_uuid}: "
                f"verified={result.verified}, confidence={result.confidence}, "
                f"claim_code={claim_code}, step={step_name}, audit={audit_uuid}"
            )

        except Exception as e:
            logger.error(f"Verification failed: {e}")
            logger.debug(traceback.format_exc())
            await self._send_error(f"Verification error: {str(e)}")

    async def _send_error(self, error_message):
        """Send error message to client."""
        await self.send({
            "type": "websocket.send",
            "text": json.dumps({
                "type": "error",
                "message": error_message,
            })
        })

    async def _create_facial_audit(self, claim_code, service_uuid, similarity_score,
                                    threshold_used, is_verified, step_name, device_id, provider):
        """
        Create a ClaimFacialAudit record linked to a claim via claim_code.

        NOTE: claim_code could change during claim processing (POC limitation).
        This should be addressed in production by using claim UUID instead.
        """
        from ..models import ClaimFacialAudit
        from claim.models import Claim
        from medical.models import Service

        try:
            # Look up claim by code (sync operation wrapped for async)
            claim = await sync_to_async(
                lambda: Claim.objects.get(code=claim_code, validity_to__isnull=True)
            )()

            # Look up service if UUID provided
            service = None
            if service_uuid:
                service = await sync_to_async(
                    lambda: Service.objects.get(uuid=service_uuid, validity_to__isnull=True)
                )()

            # Create audit record
            audit = await sync_to_async(ClaimFacialAudit.objects.create)(
                claim=claim,
                service=service,
                similarity_score=similarity_score,
                threshold_used=threshold_used,
                is_verified=is_verified,
                step_name=step_name,
                device_id=device_id,
                metadata={'provider': provider},
                user_created=self.scope.get('user'),
                user_updated=self.scope.get('user'),
            )

            logger.info(f"Created facial audit {audit.uuid} for claim {claim_code}")
            return audit.uuid

        except Claim.DoesNotExist:
            logger.error(f"Claim with code {claim_code} not found")
            return None
        except Service.DoesNotExist:
            logger.error(f"Service with UUID {service_uuid} not found")
            return None
        except Exception as e:
            logger.error(f"Failed to create facial audit: {e}")
            logger.debug(traceback.format_exc())
            return None

    async def _authenticate_connection(self):
        """
        Authenticate WebSocket connection if authentication is configured.

        Follows the same pattern as claim_ai:
        - If authentication list is empty/None: allow all connections
        - If authentication list is configured: require matching auth-token header
        """
        auth_tokens = BiometricVerificationConfig.websocket_auth_tokens

        if not auth_tokens:
            # No authentication required
            logger.debug("No authentication configured, allowing connection")
            return True

        # Extract auth-token from headers
        auth_token = None
        for header_name, value in self.scope.get('headers', []):
            if header_name == b'auth-token':
                auth_token = value.decode("utf-8")
                break

        # Validate token
        if not auth_token or auth_token not in auth_tokens:
            error_payload = {
                "type": "authentication_error",
                "message": "Invalid or missing authentication token"
            }
            await self.send({
                "type": "websocket.send",
                "text": json.dumps(error_payload)
            })
            await self.send({"type": "websocket.close", "code": 1008})
            raise ConnectionError("Invalid authentication token")

        logger.info(f"WebSocket authenticated with token: {auth_token[:8]}...")
        return True
