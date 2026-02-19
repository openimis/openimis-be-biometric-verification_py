# Security Considerations — openimis-be-biometric_verification

> Read this document before deploying to any environment beyond localhost.

---

## Public `verifyFace` endpoint

### What was done

`VerifyFaceMutation` is added to `GRAPHQL_JWT["JWT_ALLOW_ANY_CLASSES"]` at app
startup (`apps.py`). This means **any caller — including unauthenticated HTTP
requests — can invoke the `verifyFace` GraphQL mutation** without a JWT token.

This was a deliberate design choice to support a public kiosk page
(`/biometric_verification/verify/`) usable at point of service on shared
tablets where asking health workers to log in first is impractical.

---

## Risk assessment

| Risk | Severity | Notes |
|---|---|---|
| **Enumeration of insuree existence** | Medium | An attacker who knows a valid insuree UUID can determine whether the person is enrolled. UUIDs are not guessable (128-bit random), but may be leaked via other channels. |
| **Biometric probing** | Medium | An attacker can submit arbitrary face images for any known UUID and observe the `verified` response, allowing offline brute-force against the biometric threshold. |
| **Resource exhaustion / DoS** | High | Each call runs full model inference (CPU-intensive). Without rate limiting, the endpoint can be used to saturate the server. |
| **Photo path disclosure** | Low | Errors from `_fetch_insuree_photo` may reveal filesystem layout in error messages. Review logging in production. |
| **Replay attacks** | Low | The endpoint is stateless — a captured frame can be replayed. Liveness detection is not implemented. |

---

## Mandatory mitigations before production deployment

1. **Rate limiting** — Apply nginx / Django rate limiting to
   `/biometric_verification/verify/` and `/graphql` for unauthenticated
   callers. Recommended: ≤ 10 requests/minute per IP for the mutation.

   ```nginx
   limit_req_zone $binary_remote_addr zone=biometric:10m rate=10r/m;
   location /graphql {
       limit_req zone=biometric burst=5 nodelay;
   }
   ```

2. **Network-level isolation** — Do not expose the backend directly to the
   internet. Place it behind a VPN or restrict access to the facility LAN.
   The kiosk page is designed for **intranet / offline** use.

3. **HTTPS only** — Camera access (`getUserMedia`) is blocked by browsers on
   non-HTTPS origins (except `localhost`). TLS is required for any non-local
   deployment. Without it, the kiosk page will not function.

4. **Liveness detection** (future) — The current implementation compares a
   static frame against a stored photo. A printed photo can fool it. Add
   liveness detection (e.g., blink detection, depth map) before using this
   in high-security contexts.

5. **Audit logging** — Log all verification attempts (insuree UUID, timestamp,
   result, source IP) to a tamper-evident store for forensic review.

---

## To disable the public endpoint

If you decide the public endpoint is not appropriate for your deployment,
remove `VerifyFaceMutation` from `_PUBLIC_MUTATIONS` in `apps.py` and
revert the `schema.py` permission guard to its original form (re-add the
`user.is_anonymous` check at the top of `VerifyFaceMutation.mutate()`).

The `ComputeInsureeEmbeddingMutation` is **never** whitelisted and always
requires an authenticated user.