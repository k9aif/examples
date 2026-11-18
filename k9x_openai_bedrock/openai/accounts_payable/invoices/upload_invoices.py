# SPDX-License-Identifier: Apache-2.0
"""
Puts the demo's invoice PDFs in object storage (S3 or MinIO), where K9X HIL fetches them for the reviewer: each paused
payment's HIL task carries its invoice as an artifact, s3://<bucket>/<invoice_id>.pdf. Run once, with the same object
storage K9X HIL reads (S3_ENDPOINT_URL, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY in the environment):

    python accounts_payable/invoices/upload_invoices.py [bucket]      # default: AP_INVOICE_BUCKET or openai-ap-invoices
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import boto3

HERE = Path(__file__).resolve().parent


def upload(bucket: str) -> None:
    s3 = boto3.client("s3", endpoint_url=os.environ.get("S3_ENDPOINT_URL"),
                      aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
                      aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
                      config=boto3.session.Config(s3={"addressing_style": "path"}))
    if bucket not in [b["Name"] for b in s3.list_buckets()["Buckets"]]:
        s3.create_bucket(Bucket=bucket)
        print(f"created bucket {bucket}")
    for pdf in sorted(HERE.glob("INV-*.pdf")):
        s3.upload_file(str(pdf), bucket, pdf.name, ExtraArgs={"ContentType": "application/pdf"})
        print(f"s3://{bucket}/{pdf.name}")


if __name__ == "__main__":
    upload(sys.argv[1] if len(sys.argv) > 1 else os.environ.get("AP_INVOICE_BUCKET", "openai-ap-invoices"))
