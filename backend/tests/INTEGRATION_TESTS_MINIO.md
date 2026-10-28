# MinIO Integration Test Instructions

This document describes how to run integration tests for the object storage service against a real MinIO instance.

## Prerequisites

1. **Docker** installed and running
2. **MinIO** container running (via docker-compose)
3. **Python** with test dependencies installed

## Starting MinIO

### Using docker-compose (Recommended)

The project includes a `docker-compose.yml` with MinIO service:

```bash
# From project root
docker-compose up -d minio
```

This starts MinIO on:
- **API**: http://localhost:9000
- **Console**: http://localhost:9001 (login: minioadmin/minioadmin)

### Manual Docker Run

```bash
docker run -d \
  --name changeguard-minio \
  -p 9000:9000 \
  -p 9001:9001 \
  -e MINIO_ROOT_USER=minioadmin \
  -e MINIO_ROOT_PASSWORD=minioadmin \
  -v minio_data:/data \
  minio/minio:latest server /data --console-address ":9001"
```

## Configuration

Set these environment variables (or use `.env` file):

```bash
export OBJECT_STORAGE_ENDPOINT=localhost:9000
export OBJECT_STORAGE_ACCESS_KEY=minioadmin
export OBJECT_STORAGE_SECRET_KEY=minioadmin
export OBJECT_STORAGE_BUCKET=changeguard
export OBJECT_STORAGE_SECURE=false
export OBJECT_STORAGE_REGION=us-east-1
```
## Running Integration Tests

From the `backend` directory with environment variables set:

```bash
# Run only integration tests (requires MinIO running)
pytest tests/test_object_storage_integration.py -v -m integration

# Run unit tests only (no MinIO needed)
pytest tests/test_object_storage.py -v

# Run everything, letting integration tests auto-skip if MinIO missing
pytest tests/ -v
```

If the required `OBJECT_STORAGE_*` environment variables are not set, the
integration tests are skipped automatically (see the `minio_service` fixture).

## Test Coverage

`test_object_storage_integration.py` exercises against a real MinIO instance:

- upload/download round trip
- presigned URL generation and accessibility
- existence checks (present and absent keys)
- metadata (content type, size, tenant/project/document)
- deletion and post-delete existence
- validation: rejects `.exe`, faked PDF magic bytes, non-UUID document id
- filename sanitization (dangerous chars stripped from key)
- multiple file types (JPEG round trip)

## Troubleshooting

### Connection Refused

1. Check MinIO is running: `docker ps | grep minio`
2. Check health: `curl http://localhost:9000/minio/health/live`
3. Verify the `OBJECT_STORAGE_*` environment variables

### Bucket Not Found

- The service auto-creates the bucket on first use (`ensure_bucket_exists`).
- Check the configured `OBJECT_STORAGE_BUCKET` and credentials.

### Presigned URL Not Working

1. `OBJECT_STORAGE_SECURE` must match your setup (`false` for plain HTTP).
2. The endpoint must be reachable from the test process.
3. Inside Docker use `host.docker.internal:9000` instead of `localhost:9000`.

## Cleanup

After running integration tests, remove test objects with the MinIO client:

```bash
mc alias set local http://localhost:9000 minioadmin minioadmin
mc rm --recursive --force local/changeguard/
```
