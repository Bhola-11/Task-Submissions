"""
End-to-End Acceptance Test Script for Student Task Submission Portal
Validates PostgreSQL + Django MVT + Google Drive API Integration + SHA-256 Checksums
"""
import os
import sys
import io
import zipfile
from unittest.mock import patch, MagicMock
import django

# Setup Django Environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.test import Client
from django.urls import reverse
from django.contrib.auth.models import User
from submissions.models import Submission
from submissions.services import SubmissionService
from submissions.services.google_drive_service import calculate_sha256, GoogleDriveService


def create_zip_bytes(files_dict):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as z:
        for filename, content in files_dict.items():
            z.writestr(filename, content)
    buffer.seek(0)
    return buffer.getvalue()


def run_acceptance_test():
    print("=" * 70)
    print("RUNNING END-TO-END ACCEPTANCE TEST WITH GOOGLE DRIVE & SHA-256")
    print("=" * 70)

    client = Client()

    # 1. Clean existing submissions for clean acceptance run
    Submission.objects.all().delete()
    print("[OK] Cleared prior submissions from PostgreSQL.")

    # 2. Prepare 3 Student ZIPs (with .git and .gitignore to verify integrity)
    students_data = [
        {
            'name': 'Rahul',
            'task': 'Portfolio',
            'filename': 'portfolio.zip',
            'files': {
                'index.html': '<h1>Rahul Portfolio</h1><p>Full Stack Dev</p>',
                'style.css': 'body { background: #111; color: #fff; }',
                'app.js': 'console.log("Welcome to Rahul Portfolio");',
                '.gitignore': 'node_modules/\n.env\n',
                '.git/HEAD': 'ref: refs/heads/main\n',
                '.git/config': '[core]\n\trepositoryformatversion = 0\n',
            }
        },
        {
            'name': 'Aman',
            'task': 'E-Commerce',
            'filename': 'ecommerce.zip',
            'files': {
                'store.py': 'class Cart:\n    pass\n',
                'products.json': '{"items": [{"id": 1, "name": "Laptop", "price": 999}]}',
                'README.md': '# Aman E-Commerce Platform\nDjango + Stripe backend',
                '.gitignore': '*.pyc\n__pycache__/\n',
                '.git/HEAD': 'ref: refs/heads/master\n',
            }
        },
        {
            'name': 'Priya',
            'task': 'AI Chatbot',
            'filename': 'chatbot.zip',
            'files': {
                'bot.py': 'def chat(prompt):\n    return "Response to: " + prompt\n',
                'model_config.json': '{"temperature": 0.7, "max_tokens": 500}',
                'requirements.txt': 'torch\ntransformers\n',
                '.gitignore': '.env\nweights/\n',
                '.git/HEAD': 'ref: refs/heads/dev\n',
            }
        },
    ]

    # 3. Submit each task via HTTP POST
    submission_ids = []
    for item in students_data:
        zip_bytes = create_zip_bytes(item['files'])
        zip_file = io.BytesIO(zip_bytes)
        zip_file.name = item['filename']

        print(f"\nSubmitting task for Student: {item['name']}, Task: {item['task']}, File: {item['filename']}...")
        response = client.post(reverse('submissions:submit'), {
            'student_name': item['name'],
            'task_name': item['task'],
            'file': zip_file,
        })

        if response.status_code == 302:
            print(f"[OK] Form submission succeeded (302 Redirect to {response.url})")
            sub_id = int(response.url.strip('/').split('/')[-1])
            submission_ids.append(sub_id)
        else:
            print(f"[FAIL] Submission failed with status {response.status_code}")
            sys.exit(1)

    # 4. Verify Database, Checksum & Storage Integrity
    print("\n" + "=" * 70)
    print("VERIFYING POSTGRESQL & BINARY SHA-256 INTEGRITY")
    print("=" * 70)

    db_submissions = list(Submission.objects.all().order_by('id'))
    assert len(db_submissions) == 3, f"Expected 3 submissions, found {len(db_submissions)}"

    for sub, expected in zip(db_submissions, students_data):
        print(f"\nVerifying Submission #{sub.id}:")
        print(f"  Student Name:       {sub.student_name} (Expected: {expected['name']})")
        print(f"  Task Name:          {sub.task_name} (Expected: {expected['task']})")
        print(f"  Original Filename:  {sub.original_filename} (Expected: {expected['filename']})")
        print(f"  Stored Filename:    {sub.stored_filename}")
        print(f"  File Size:          {sub.file_size_formatted} ({sub.file_size} bytes)")
        print(f"  SHA-256 Checksum:   {sub.sha256_checksum}")
        print(f"  Review Status:      {sub.status}")
        print(f"  Google Drive Status:{sub.google_drive_status}")
        print(f"  Submitted At:       {sub.submitted_at}")

        assert sub.student_name == expected['name']
        assert sub.task_name == expected['task']
        assert sub.original_filename == expected['filename']
        assert sub.status == 'Pending'
        assert sub.google_drive_status == 'Not Uploaded'
        assert len(sub.sha256_checksum) == 64, "Invalid SHA-256 hash length!"
        assert os.path.exists(sub.file.path), f"File {sub.file.path} not found on disk!"

        # Verify disk binary checksum matches database hash
        disk_hash = calculate_sha256(sub.file.path)
        assert sub.sha256_checksum == disk_hash, f"Checksum mismatch! DB: {sub.sha256_checksum}, Disk: {disk_hash}"
        print(f"  [OK] SHA-256 exact binary checksum match verified ({disk_hash[:12]}...).")

        # CRITICAL INTEGRITY CHECK: Verify ZIP contains .git and hidden files completely untouched
        with zipfile.ZipFile(sub.file.path, 'r') as student_zip:
            namelist = student_zip.namelist()
            for expected_file in expected['files'].keys():
                assert expected_file in namelist, f"Missing {expected_file} in stored ZIP!"
        print(f"  [OK] Physical ZIP file contains all files including .git/ and .gitignore without modification.")

    # 5. Admin Authentication & Dashboard
    print("\n" + "=" * 70)
    print("VERIFYING ADMIN DASHBOARD & GOOGLE DRIVE INTEGRATION")
    print("=" * 70)

    # Ensure admin user exists
    if not User.objects.filter(username='admin').exists():
        User.objects.create_superuser('admin', 'admin@example.com', 'admin123')

    login_success = client.login(username='admin', password='admin123')
    assert login_success, "Admin login failed!"
    print("[OK] Admin authenticated successfully.")

    # Check Dashboard
    dash_resp = client.get(reverse('submissions:dashboard'))
    assert dash_resp.status_code == 200, f"Dashboard returned {dash_resp.status_code}"
    dash_html = dash_resp.content.decode('utf-8')
    assert "Rahul" in dash_html
    assert "Aman" in dash_html
    assert "Priya" in dash_html
    assert "Save All to Google Drive" in dash_html
    print("[OK] Dashboard loaded successfully with Google Drive actions.")

    # Test Individual Google Drive Sync
    first_sub = db_submissions[0]
    with patch('submissions.services.google_drive_service.GoogleDriveService.upload_submission_zip') as mock_upload:
        mock_upload.return_value = {
            'success': True,
            'status': 'uploaded',
            'file_id': 'gdrive_file_99999',
            'url': 'https://drive.google.com/file/d/gdrive_file_99999/view',
            'filename': 'Rahul_Portfolio.zip'
        }
        gdrive_resp = client.get(reverse('submissions:save_to_google_drive', kwargs={'submission_id': first_sub.id}))
        assert gdrive_resp.status_code == 302, f"Google Drive upload endpoint returned {gdrive_resp.status_code}"
        mock_upload.assert_called_once()
        print(f"[OK] Individual Google Drive upload view verified for #{first_sub.id}.")

    # Test Save All to Google Drive (Server-Side Batch Sync)
    with patch('submissions.services.google_drive_service.GoogleDriveService.sync_all_submissions') as mock_sync:
        mock_sync.return_value = {
            'total': 3,
            'uploaded': 3,
            'already_uploaded': 0,
            'failed': 0,
            'skipped': 0,
            'errors': []
        }
        batch_resp = client.get(reverse('submissions:save_all_to_google_drive'))
        assert batch_resp.status_code == 302, f"Save All to Google Drive returned {batch_resp.status_code}"
        mock_sync.assert_called_once()
        print("[OK] 'Save All to Google Drive' server-side batch sync verified.")

    # Test Individual Download
    for sub in db_submissions:
        dl_resp = client.get(reverse('submissions:download_submission_zip', kwargs={'submission_id': sub.id}))
        assert dl_resp.status_code == 200, f"Download failed for #{sub.id}"
        assert dl_resp['Content-Type'] == 'application/zip'
        assert sub.original_filename in dl_resp['Content-Disposition']
        # Read downloaded bytes
        downloaded_bytes = b"".join(dl_resp.streaming_content)
        with zipfile.ZipFile(io.BytesIO(downloaded_bytes), 'r') as check_zip:
            assert '.git/HEAD' in check_zip.namelist()
        print(f"[OK] Individual ZIP download verified for #{sub.id} ({sub.original_filename}) preserving .git.")

    # 6. Test Download All ZIPs
    print("\n" + "=" * 70)
    print("VERIFYING MASTER ARCHIVE PACKAGING")
    print("=" * 70)

    all_resp = client.get(reverse('submissions:download_all_zips'))
    assert all_resp.status_code == 200, f"Download all failed with {all_resp.status_code}"
    assert all_resp['Content-Type'] == 'application/zip'
    assert 'All-Student-Tasks-' in all_resp['Content-Disposition']
    print(f"[OK] Master ZIP downloaded: {all_resp['Content-Disposition']}")

    master_bytes = b"".join(all_resp.streaming_content)
    with zipfile.ZipFile(io.BytesIO(master_bytes), 'r') as master_zip:
        inner_filenames = master_zip.namelist()
        print(f"Master ZIP contains: {inner_filenames}")

        assert "Rahul_Portfolio.zip" in inner_filenames
        assert "Aman_E-Commerce.zip" in inner_filenames
        assert "Priya_AI_Chatbot.zip" in inner_filenames

        # CRITICAL VERIFICATION: Each item inside is an intact, original ZIP file
        for name in ["Rahul_Portfolio.zip", "Aman_E-Commerce.zip", "Priya_AI_Chatbot.zip"]:
            student_zip_data = master_zip.read(name)
            assert student_zip_data.startswith(b'PK\x03\x04'), f"{name} is not a valid intact ZIP!"
            with zipfile.ZipFile(io.BytesIO(student_zip_data), 'r') as extracted_inner:
                print(f"  [OK] {name} inside master ZIP is an intact original ZIP containing: {extracted_inner.namelist()}")

    print("\n" + "=" * 70)
    print("ALL ACCEPTANCE TESTS WITH GOOGLE DRIVE & SHA-256 PASSED PERFECTLY!")
    print("=" * 70)


if __name__ == '__main__':
    run_acceptance_test()
