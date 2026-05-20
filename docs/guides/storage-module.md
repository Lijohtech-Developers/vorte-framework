# Storage Module

File storage with local filesystem and AWS S3 backends.

## Setup

```python
from vorte import StorageModule

app.register(StorageModule())
```

## Configuration

```env
VORTE_STORAGE_DRIVER=local
VORTE_STORAGE_BUCKET=my-bucket
VORTE_STORAGE_REGION=us-east-1
VORTE_STORAGE_LOCAL_PATH=./storage
VORTE_STORAGE_CDN_URL=https://cdn.example.com
```

| Field | Default | Description |
|-------|---------|-------------|
| `driver` | `"local"` | Storage backend: "local" or "s3" |
| `bucket` | `""` | S3 bucket name |
| `cdn_url` | `None` | CDN URL for public access |
| `local_path` | `"./storage"` | Local storage directory |
| `access_key` | `""` | AWS access key |
| `secret_key` | `""` | AWS secret key |
| `region` | `"us-east-1"` | AWS region |

## Features

- **Local Storage** -- File system storage for development
- **S3 Storage** -- AWS S3 for production
- **CDN Integration** -- Serve files via CDN
- **Presigned URLs** -- Generate time-limited download URLs
- **File Upload/Download** -- Standard file operations
