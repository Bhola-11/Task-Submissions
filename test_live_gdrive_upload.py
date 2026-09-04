"""
Live Google Drive API Integration Test Script
"""
import os
import io
import zipfile
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from submissions.models import Submission
from submissions.services import SubmissionService
from submissions.services.google_drive_service import GoogleDriveService, calculate_sha256


def run_live_test():
    print("=" * 70)
    print("RUNNING LIVE GOOGLE DRIVE UPLOAD & INTEGRITY VERIFICATION")
    print("=" * 70)

    # 1. Prepare student ZIP containing .git and .gitignore
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr("index.html", "<h1>Live Test Project</h1>\n<p>Google Drive Verification</p>")
        z.writestr("styles.css", "body { font-family: sans-serif; }")
        z.writestr(".gitignore", "node_modules/\n.env\n*.pyc\n")
        z.writestr(".git/HEAD", "ref: refs/heads/main\n")
        z.writestr(".git/config", "[core]\n\trepositoryformatversion = 0\n")
    zip_buffer.seek(0)
    zip_bytes = zip_buffer.getvalue()

    # 2. Compute expected SHA-256
    expected_sha256 = calculate_sha256(io.BytesIO(zip_bytes))
    print(f"Pre-Upload Binary SHA-256: {expected_sha256}")

    from django.core.files.uploadedfile import SimpleUploadedFile
    uploaded_file = SimpleUploadedFile("portfolio.zip", zip_bytes, content_type="application/zip")

    submission = SubmissionService.create_submission(
        student_name="Rahul",
        task_name="Portfolio",
        uploaded_file=uploaded_file
    )
    print(f"[OK] Submission created in PostgreSQL: ID #{submission.id}")
    print(f"  Stored Checksum:    {submission.sha256_checksum}")
    print(f"  Google Drive Status:{submission.google_drive_status}")
    assert submission.sha256_checksum == expected_sha256, "SHA-256 mismatch upon creation!"

    # 4. Upload to Google Drive
    print("\nExecuting live upload to Google Drive folder '1yePeQA8Wd1diBIGzMcD7joDsT3ktaodJ'...")
    result = GoogleDriveService.upload_submission_zip(submission)

    print("\nUpload Result:")
    print(f"  Success:   {result.get('success')}")
    print(f"  File ID:   {result.get('file_id')}")
    print(f"  Web URL:   {result.get('url')}")
    print(f"  Filename:  {result.get('filename')}")
    print(f"  Status:    {result.get('status')}")
    if not result.get('success'):
        print(f"  Error:     {result.get('error')}")
        raise RuntimeError(f"Google Drive upload failed: {result.get('error')}")

    # 5. Verify PostgreSQL Record
    submission.refresh_from_db()
    print("\nVerifying PostgreSQL Record after upload:")
    print(f"  Google Drive Status:     {submission.google_drive_status}")
    print(f"  Google Drive File ID:    {submission.google_drive_file_id}")
    print(f"  Google Drive URL:        {submission.google_drive_url}")
    print(f"  Google Drive Upload Time:{submission.google_drive_uploaded_at}")
    assert submission.google_drive_status == Submission.GoogleDriveStatusChoices.UPLOADED
    assert submission.google_drive_file_id == result['file_id']
    assert submission.google_drive_url is not None

    # 6. Verify Google Drive Remote File Metadata
    drive_client = GoogleDriveService.get_drive_client()
    remote_file = drive_client.files().get(
        fileId=submission.google_drive_file_id,
        fields="id, name, size, mimeType, parents, md5Checksum"
    ).execute()

    print("\nGoogle Drive Remote Metadata:")
    print(f"  Name:      {remote_file.get('name')}")
    print(f"  Size:      {remote_file.get('size')} bytes (Local: {submission.file_size} bytes)")
    print(f"  MIME:      {remote_file.get('mimeType')}")
    print(f"  Parents:   {remote_file.get('parents')}")
    assert int(remote_file.get('size')) == submission.file_size, "Remote size does not match local file size!"

    # 7. Verify Local File Integrity Post-Upload
    post_disk_hash = calculate_sha256(submission.file.path)
    assert post_disk_hash == expected_sha256, "Local file corrupted or altered post-upload!"

    with zipfile.ZipFile(submission.file.path, 'r') as zf:
        namelist = zf.namelist()
        assert ".git/HEAD" in namelist, ".git/HEAD missing!"
        assert ".gitignore" in namelist, ".gitignore missing!"
        print(f"[OK] Stored ZIP contains all files intact: {namelist}")

    print("\n" + "=" * 70)
    print("LIVE GOOGLE DRIVE INTEGRATION TEST PASSED 100% SUCCESSFULLY!")
    print("=" * 70)


if __name__ == '__main__':
    run_live_test()
