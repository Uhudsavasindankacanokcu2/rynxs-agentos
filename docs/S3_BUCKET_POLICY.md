# S3 Bucket Policy for Conditional Write Enforcement

Production-grade configuration for enforcing conditional writes (If-None-Match) at the bucket level.

## Why This Matters

The rynxs operator uses S3 conditional writes (`If-None-Match: *`) to prevent event log overwrites. This is critical for split-brain protection:

- **Problem**: Without enforcement, a rogue script or misconfigured operator could overwrite events
- **Solution**: Bucket policy that **rejects** all PutObject requests without `If-None-Match`

AWS S3 officially supports conditional writes as of 2023. MinIO also supports this via S3 compatibility layer.

**References**:
- [AWS S3 Conditional Writes](https://aws.amazon.com/blogs/aws/new-conditional-writes-for-amazon-s3/)
- [AWS S3 Conditional Request Headers](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-requests.html)

---

## AWS S3 Bucket Policy

### Policy: Deny PutObject Without If-None-Match

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyPutObjectWithoutIfNoneMatch",
      "Effect": "Deny",
      "Principal": "*",
      "Action": "s3:PutObject",
      "Resource": "arn:aws:s3:::rynxs-events-prod/events/*",
      "Condition": {
        "StringNotEquals": {
          "s3:x-amz-copy-source-if-none-match": "*"
        },
        "Null": {
          "s3:x-amz-copy-source-if-none-match": "true"
        }
      }
    }
  ]
}
```

**Explanation**:
- **Resource**: `events/*` prefix (only enforce for event objects, not other bucket contents)
- **Condition**: Rejects PUT if `If-None-Match` header is missing or not equal to `*`
- **Null check**: Rejects if header is completely absent

**Apply via AWS CLI**:
```bash
# Save policy to file
cat > bucket-policy.json <<'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyPutObjectWithoutIfNoneMatch",
      "Effect": "Deny",
      "Principal": "*",
      "Action": "s3:PutObject",
      "Resource": "arn:aws:s3:::rynxs-events-prod/events/*",
      "Condition": {
        "StringNotEquals": {
          "s3:x-amz-copy-source-if-none-match": "*"
        },
        "Null": {
          "s3:x-amz-copy-source-if-none-match": "true"
        }
      }
    }
  ]
}
EOF

# Apply policy
aws s3api put-bucket-policy --bucket rynxs-events-prod --policy file://bucket-policy.json

# Verify policy
aws s3api get-bucket-policy --bucket rynxs-events-prod --output text | jq .
```

---

## MinIO Bucket Policy

MinIO supports S3-compatible bucket policies with some caveats. The same policy structure applies:

```bash
# MinIO client (mc) configuration
mc alias set myminio https://minio.example.com MINIOADMIN MINIOADMINPASSWORD

# Apply policy
mc admin policy attach myminio rynxs-conditional-write --user rynxs-operator

# Verify policy
mc admin policy info myminio rynxs-conditional-write
```

**MinIO Policy JSON** (same as AWS):
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Deny",
      "Action": ["s3:PutObject"],
      "Resource": ["arn:aws:s3:::rynxs-events/events/*"],
      "Condition": {
        "StringNotEquals": {
          "s3:x-amz-copy-source-if-none-match": "*"
        },
        "Null": {
          "s3:x-amz-copy-source-if-none-match": "true"
        }
      }
    }
  ]
}
```

**Important**: MinIO conditional write support varies by version. Ensure MinIO version >= RELEASE.2023-08-01 for full compatibility.

---

## Testing the Policy

### Test 1: Conditional Write (Should Succeed)

```bash
# Create test event with If-None-Match
aws s3api put-object \
  --bucket rynxs-events-prod \
  --key events/test-0000000001.json \
  --body test-event.json \
  --if-none-match '*'

# Expected: Success (200 OK)
```

### Test 2: Unconditional Write (Should Fail)

```bash
# Try to PUT without If-None-Match
aws s3api put-object \
  --bucket rynxs-events-prod \
  --key events/test-0000000002.json \
  --body test-event.json

# Expected: Failure (403 Forbidden)
# Error: An error occurred (AccessDenied) when calling the PutObject operation
```

### Test 3: Overwrite Attempt (Should Fail)

```bash
# Try to overwrite existing object even with If-None-Match
aws s3api put-object \
  --bucket rynxs-events-prod \
  --key events/test-0000000001.json \
  --body test-event.json \
  --if-none-match '*'

# Expected: Failure (412 Precondition Failed)
# S3 rejects because object already exists
```

---

## Operator Configuration

The rynxs operator already uses `If-None-Match: *` in `S3EventStore._put_event_object()`:

```python
# engine/log/s3_store.py
def _put_event_object(self, key: str, body: str) -> bool:
    try:
        self.s3_client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=body.encode("utf-8"),
            ContentType="application/json",
            IfNoneMatch="*"  # ← Conditional write header
        )
        return True
    except ClientError as e:
        if e.response.get("Error", {}).get("Code", "") in ("PreconditionFailed", "412"):
            return False  # Object already exists (expected)
        raise
```

**No code changes needed** - just apply the bucket policy.

---

## Monitoring

### CloudWatch Metrics (AWS)

Monitor `PutObject` rejections due to policy:

```promql
# CloudWatch query
aws cloudwatch get-metric-statistics \
  --namespace AWS/S3 \
  --metric-name 4xxErrors \
  --dimensions Name=BucketName,Value=rynxs-events-prod \
  --start-time 2024-01-01T00:00:00Z \
  --end-time 2024-01-02T00:00:00Z \
  --period 3600 \
  --statistics Sum
```

### Prometheus Alert (Operator Side)

Alert on S3 PutObject failures (operator logs `ClientError`):

```yaml
- alert: RynxsS3PutObjectFailuresHigh
  expr: rate(rynxs_events_total{event_type="S3PutObjectFailed"}[5m]) > 0.1
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "High rate of S3 PutObject failures"
    description: "Operator is failing to write events to S3. Check bucket policy and credentials."
```

---

## Troubleshooting

### Error: AccessDenied (403)

**Symptom**: Operator logs `ClientError: AccessDenied` on event append.

**Diagnosis**:
1. Check bucket policy is applied correctly:
   ```bash
   aws s3api get-bucket-policy --bucket rynxs-events-prod
   ```

2. Verify IAM user/role has `s3:PutObject` permission:
   ```bash
   aws iam get-user-policy --user-name rynxs-operator --policy-name S3EventStorePolicy
   ```

3. Test conditional write manually (see Test 1 above)

**Resolution**:
- If policy is missing: Apply policy from this doc
- If IAM permissions missing: Add `s3:PutObject` to IAM policy
- If MinIO: Check MinIO version supports conditional writes

### Error: PreconditionFailed (412)

**Symptom**: Operator logs `PreconditionFailed` on event append.

**Root Cause**: Attempting to write event with seq that already exists (duplicate).

**This is expected behavior** - the operator will retry with next seq. If persistent:
1. Check for split-brain (multiple operators writing)
2. Verify leader election is working (`rynxs_leader_election_status` metric)
3. Check event log for gaps/duplicates:
   ```bash
   aws s3 ls s3://rynxs-events-prod/events/ | awk '{print $4}' | sort
   ```

---

## Production Deployment Checklist

- [ ] Bucket policy applied (AWS or MinIO)
- [ ] IAM permissions include `s3:PutObject` with conditional write header
- [ ] Tested conditional write enforcement (Test 1-3 above)
- [ ] CloudWatch/Prometheus alerts configured for S3 failures
- [ ] Runbook updated with troubleshooting steps
- [ ] Operator helm values include correct S3 bucket name
- [ ] S3 bucket has versioning enabled (optional, for audit trail)
- [ ] S3 bucket has lifecycle policy for old events (optional, for cost optimization)

---

## References

- [AWS S3 Conditional Writes Announcement](https://aws.amazon.com/blogs/aws/new-conditional-writes-for-amazon-s3/)
- [AWS S3 Conditional Request Headers](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-requests.html)
- [MinIO S3 Compatibility](https://min.io/docs/minio/linux/developers/s3-api-compatibility.html)
- [S3EventStore Implementation](../engine/log/s3_store.py)
- [Event Sourcing Patterns](https://martinfowler.com/eaaDev/EventSourcing.html)
