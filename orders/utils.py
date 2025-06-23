import boto3
from django.conf import settings



R2_ENDPOINT_URL = f"https://{settings.CLOUDFLARE_R2_ACCOUNT_ID}.r2.cloudflarestorage.com"

def get_r2_client():
    return boto3.client(
        service_name='s3',
        endpoint_url=R2_ENDPOINT_URL,
        aws_access_key_id=settings.CLOUDFLARE_R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.CLOUDFLARE_R2_SECRET_ACCESS_KEY,
        region_name=settings.CLOUDFLARE_R2_REGION, # e.g., 'auto' or 'enam
    )

def generate_download_url(file_key):
    try:
        s3_client = get_r2_client()
        presigned_get = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': settings.CLOUDFLARE_R2_BUCKET_NAME, 'Key': file_key},
            ExpiresIn=3600
        )
        return presigned_get
    except Exception as e:
        return ""