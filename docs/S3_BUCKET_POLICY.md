# S3 Write-Once Enforcement for Event Log

Production-grade configuration for preventing event log overwrites using AWS S3 conditional writes and Object Lock.

## Why This Matters

The rynxs operator uses S3 as an append-only event log. Preventing overwrites is **critical** for:
- **Split-brain protection**: Ensures only one leader can write each sequence number
- **Audit trail integrity**: Events cannot be altered after writing
- **Forensic analysis**: Fencing tokens in event metadata enable post-mortem investigation

AWS S3 provides two approaches for write-once enforcement:
1. **Conditional writes** (If-None-Match) - Application-level + bucket policy enforcement
2. **Object Lock (WORM)** - Infrastructure-level immutability

---

## Approach 1: Conditional Writes (Recommended for Rynxs)

### Overview

AWS S3 supports conditional writes via the `If-None-Match: *` HTTP header (added August 2023, bucket policy enforcement added **November 2024**).

**How it works:**
- Client (rynxs operator) includes `If-None-Match: *` header in PutObject request
- S3 checks if object key already exists:
  - **Not exists** → 200 OK, object created
  - **Exists** → 412 Precondition Failed, write rejected
- Bucket policy enforces header presence (prevents misconfigured clients from bypassing protection)

**References:**
- [AWS S3 Conditional Writes (Aug 2023)](https://aws.amazon.com/blogs/aws/new-conditional-writes-for-amazon-s3/)
- [Enforce Conditional Writes on Buckets (Nov 2024)](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes-enforce.html)
- [AWS Announcement (Nov 2024)](https://aws.amazon.com/about-aws/whats-new/2024/11/amazon-s3-enforcement-conditional-write-operations-general-purpose-buckets/)

---

### AWS S3 Bucket Policy

**Policy: Require If-None-Match Header for PutObject**

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "RequireConditionalWriteForEvents",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::123456789012:role/rynxs-operator"
      },
      "Action": "s3:PutObject",
      "Resource": "arn:aws:s3:::rynxs-events-prod/events/*",
      "Condition": {
        "Null": {
          "s3:if-none-match": "false"
        }
      }
    },
    {
      "Sid": "AllowMultipartUploads",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::123456789012:role/rynxs-operator"
      },
      "Action": "s3:PutObject",
      "Resource": "arn:aws:s3:::rynxs-events-prod/events/*",
      "Condition": {
        "Bool": {
          "s3:ObjectCreationOperation": "false"
        }
      }
    }
  ]
}
```

**Explanation:**
- **First statement**: Allows PutObject **only if** `If-None-Match` header is present (`"Null": "false"`)
- **Second statement**: Allows multipart upload operations (`CreateMultipartUpload`, `UploadPart`, `CompleteMultipartUpload`) which don't use If-None-Match
- **Resource**: `events/*` prefix (only enforce for event objects)
- **Principal**: IAM role used by rynxs operator (replace with your role ARN)

**Apply via AWS CLI:**

```bash
# Save policy to file
cat > bucket-policy.json <<'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "RequireConditionalWriteForEvents",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::123456789012:role/rynxs-operator"
      },
      "Action": "s3:PutObject",
      "Resource": "arn:aws:s3:::rynxs-events-prod/events/*",
      "Condition": {
        "Null": {
          "s3:if-none-match": "false"
        }
      }
    },
    {
      "Sid": "AllowMultipartUploads",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::123456789012:role/rynxs-operator"
      },
      "Action": "s3:PutObject",
      "Resource": "arn:aws:s3:::rynxs-events-prod/events/*",
      "Condition": {
        "Bool": {
          "s3:ObjectCreationOperation": "false"
        }
      }
    }
  ]
}
EOF

# Replace with your IAM role ARN
sed -i 's/123456789012/YOUR_ACCOUNT_ID/g' bucket-policy.json
sed -i 's/rynxs-operator/YOUR_ROLE_NAME/g' bucket-policy.json

# Apply policy
aws s3api put-bucket-policy --bucket rynxs-events-prod --policy file://bucket-policy.json

# Verify policy
aws s3api get-bucket-policy --bucket rynxs-events-prod --output text | jq .
```

---

### MinIO Support

**Status**: Limited support for conditional writes (as of RELEASE.2023-08-01+).

MinIO supports `If-None-Match` at the **API level** but **bucket policy enforcement** is **not guaranteed**. The `s3:if-none-match` condition key may not be respected in MinIO bucket policies.

**Recommendation for MinIO:**
- Rely on application-level conditional writes (operator already uses `IfNoneMatch="*"`)
- Use MinIO versioning + deny DeleteObject policy as additional protection
- For production, prefer AWS S3 over MinIO for event log storage

**MinIO Versioning Policy (defense-in-depth):**

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Deny",
      "Principal": "*",
      "Action": ["s3:DeleteObject", "s3:DeleteObjectVersion"],
      "Resource": "arn:aws:s3:::rynxs-events/events/*"
    }
  ]
}
```

---

### Testing the Policy

#### Test 1: Conditional Write (Should Succeed)

```bash
# Create test event with If-None-Match
aws s3api put-object \
  --bucket rynxs-events-prod \
  --key events/test-0000000001.json \
  --body test-event.json \
  --if-none-match '*'

# Expected: Success (200 OK)
```

#### Test 2: Unconditional Write (Should Fail)

```bash
# Try to PUT without If-None-Match (policy should reject)
aws s3api put-object \
  --bucket rynxs-events-prod \
  --key events/test-0000000002.json \
  --body test-event.json

# Expected: Failure (403 Forbidden)
# Error: An error occurred (AccessDenied) when calling the PutObject operation
```

#### Test 3: Overwrite Attempt (Should Fail)

```bash
# Try to overwrite existing object even with If-None-Match
aws s3api put-object \
  --bucket rynxs-events-prod \
  --key events/test-0000000001.json \
  --body test-event.json \
  --if-none-match '*'

# Expected: Failure (412 Precondition Failed)
# S3 rejects because object already exists (conditional write semantics)
```

---

### Operator Configuration

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
            return False  # Object already exists (expected during retry)
        raise
```

**No code changes needed** - just apply the bucket policy.

---

## Approach 2: S3 Object Lock (WORM Compliance)

### Overview

S3 Object Lock provides **infrastructure-level write-once-read-many (WORM)** protection using retention policies.

**Key features:**
- **Compliance mode**: Objects cannot be deleted or overwritten by **any user** (including root) for the retention period
- **Legal hold**: Additional immutability flag (independent of retention)
- **Versioning required**: Object Lock requires S3 versioning to be enabled
- **Regulatory compliance**: SEC 17a-4, CFTC, FINRA certified

**When to use Object Lock:**
- High-assurance audit requirements (financial, healthcare, government)
- Defense-in-depth: Combine with conditional writes for dual protection
- Long-term immutability (years, not hours/days)

**References:**
- [S3 Object Lock Documentation](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html)
- [AWS Storage Blog: Multi-Writer Applications](https://aws.amazon.com/blogs/storage/building-multi-writer-applications-on-amazon-s3-using-native-controls/)

---

### Enabling Object Lock

**1. Create bucket with Object Lock enabled (cannot be enabled on existing buckets):**

```bash
aws s3api create-bucket \
  --bucket rynxs-events-prod-worm \
  --region us-east-1 \
  --object-lock-enabled-for-bucket
```

**2. Configure default retention (optional):**

```bash
aws s3api put-object-lock-configuration \
  --bucket rynxs-events-prod-worm \
  --object-lock-configuration '{
    "ObjectLockEnabled": "Enabled",
    "Rule": {
      "DefaultRetention": {
        "Mode": "COMPLIANCE",
        "Years": 7
      }
    }
  }'
```

**3. Upload object with retention:**

```bash
aws s3api put-object \
  --bucket rynxs-events-prod-worm \
  --key events/0000000001.json \
  --body event.json \
  --object-lock-mode COMPLIANCE \
  --object-lock-retain-until-date "2030-01-01T00:00:00Z"
```

---

### Object Lock vs Conditional Writes

| Feature | Conditional Writes | Object Lock (WORM) |
|---------|-------------------|-------------------|
| **Prevent overwrites** | ✅ Yes (If-None-Match) | ✅ Yes (retention policy) |
| **Prevent deletes** | ❌ No (use IAM/policy) | ✅ Yes (compliance mode) |
| **Performance** | Native PutObject | Native PutObject |
| **Cost** | Standard S3 pricing | Standard S3 pricing |
| **Versioning required** | ❌ No | ✅ Yes |
| **Regulatory compliance** | ❌ No | ✅ SEC 17a-4, CFTC, FINRA |
| **Use case** | Append-only event log | High-assurance audit trail |

**Recommendation:**
- **Default**: Conditional writes (simpler, no versioning overhead)
- **High assurance**: Object Lock Compliance mode (regulatory compliance)
- **Defense-in-depth**: Both (conditional writes + Object Lock)

---

## Monitoring

### CloudWatch Metrics (AWS)

Monitor `PutObject` rejections due to policy:

```bash
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

Alert on S3 PutObject failures:

```yaml
- alert: RynxsS3PutObjectFailuresHigh
  expr: rate(rynxs_s3_put_errors_total[5m]) > 0.1
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

**Diagnosis:**
1. Check bucket policy is applied correctly:
   ```bash
   aws s3api get-bucket-policy --bucket rynxs-events-prod
   ```

2. Verify IAM role has `s3:PutObject` permission:
   ```bash
   aws iam get-role-policy --role-name rynxs-operator --policy-name S3EventStorePolicy
   ```

3. Test conditional write manually (see Test 1 above)

**Resolution:**
- If policy is missing: Apply policy from this doc
- If IAM permissions missing: Add `s3:PutObject` to IAM policy
- If principal ARN mismatch: Update bucket policy with correct IAM role ARN

---

### Error: PreconditionFailed (412)

**Symptom**: Operator logs `PreconditionFailed` on event append.

**Root Cause**: Attempting to write event with sequence number that already exists (duplicate).

**This is expected behavior** - the operator will retry with next sequence number. If persistent:
1. Check for split-brain (multiple operators writing):
   - Verify `rynxs_leader_election_status` metric (should be 1 total across all replicas)
   - Check fencing tokens in event metadata for holder_identity conflicts
2. Check event log for gaps/duplicates:
   ```bash
   aws s3 ls s3://rynxs-events-prod/events/ | awk '{print $4}' | sort -n
   ```
3. Inspect recent events for fencing token epoch transitions:
   ```bash
   aws s3api get-object --bucket rynxs-events-prod --key events/0000001234.json /dev/stdout | jq '.meta.fencing_token'
   ```

---

## Production Deployment Checklist

### Conditional Writes (Recommended)
- [ ] Bucket policy applied with correct IAM principal ARN
- [ ] IAM role has `s3:PutObject` permission
- [ ] Tested conditional write enforcement (Test 1-3 above)
- [ ] CloudWatch/Prometheus alerts configured for S3 failures
- [ ] Operator helm values include correct S3 bucket name
- [ ] S3 bucket has versioning enabled (optional, for audit trail)
- [ ] S3 bucket has lifecycle policy for old events (optional, for cost optimization)

### Object Lock (Optional, High Assurance)
- [ ] New bucket created with `--object-lock-enabled-for-bucket`
- [ ] Default retention policy configured (COMPLIANCE mode, 7+ years)
- [ ] Operator updated to include `ObjectLockMode` and `ObjectLockRetainUntilDate` in PutObject
- [ ] Legal hold policy documented (if required)
- [ ] S3 Glacier transition policy configured (for cost optimization after retention period)

---

## References

- [AWS S3 Conditional Writes Announcement (Aug 2023)](https://aws.amazon.com/blogs/aws/new-conditional-writes-for-amazon-s3/)
- [Enforce Conditional Writes on Buckets (Nov 2024)](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes-enforce.html)
- [AWS Announcement: Conditional Write Enforcement (Nov 2024)](https://aws.amazon.com/about-aws/whats-new/2024/11/amazon-s3-enforcement-conditional-write-operations-general-purpose-buckets/)
- [S3 Object Lock Documentation](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html)
- [MinIO S3 Compatibility](https://min.io/docs/minio/linux/developers/s3-api-compatibility.html)
- [S3EventStore Implementation](../engine/log/s3_store.py)
- [Event Sourcing Patterns](https://martinfowler.com/eaaDev/EventSourcing.html)
