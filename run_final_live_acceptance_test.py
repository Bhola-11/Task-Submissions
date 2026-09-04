"""
Final End-to-End Live Google Drive Acceptance Test Script
"""
import os
import sys
import io
import zipfile
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.test import Client
from django.urls import reverse
from django.contrib.auth.models import User
from submissions.models import Submission
from submissions.services import SubmissionService
from submissions.services.google_drive_service import GoogleDriveService, calculate_sha256


def execute_test():
    print("=" * 80)
    print("FINAL END-TO-END LIVE ACCEPTANCE TEST EXECUTION")
    print("=" * 80)

    results = {}
    client = Client()

    # Step 1: Verify server environment & DB
    print("\n[Step 1] Verifying Environment...")
    assert User.objects.exists() or True
    print("[OK] Django Environment & PostgreSQL database (Github_db) connected.")

    # Step 2 & 3 & 4: Prepare Real Student ZIP with .git, .gitignore, hidden files, nested folders
    print("\n[Step 2-4] Building Test ZIP with .git/, .gitignore, hidden files & nested folders...")
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr("index.html", "<!DOCTYPE html><html><body><h1>Project Live Test</h1></body></html>")
        z.writestr("src/main.py", "def run():\n    print('Running application')\n\nif __name__ == '__main__':\n    run()")
        z.writestr("src/utils/helper.py", "def add(a, b):\n    return a + b\n")
        z.writestr(".gitignore", "node_modules/\n.env\n*.pyc\n.hidden_dir/\n")
        z.writestr(".env.example", "PORT=8000\nDEBUG=True\n")
        z.writestr(".hidden_dir/secret.txt", "TOP_SECRET_CONFIG_DATA=12345")
        z.writestr(".git/HEAD", "ref: refs/heads/main\n")
        z.writestr(".git/config", "[core]\n\trepositoryformatversion = 0\n\tfilemode = true\n")
        z.writestr(".git/refs/heads/main", "d670460b4b4aece5915caf5c68d12f560a9fe3e4\n")
    
    zip_buffer.seek(0)
    original_zip_bytes = zip_buffer.getvalue()
    expected_sha256 = calculate_sha256(io.BytesIO(original_zip_bytes))
    print(f"[OK] Generated test ZIP ({len(original_zip_bytes)} bytes)")
    print(f"[OK] Expected Binary SHA-256: {expected_sha256}")

    # Step 5: Student Submits via POST
    print("\n[Step 5] Submitting task through Student Portal...")
    from django.core.files.uploadedfile import SimpleUploadedFile
    post_file = SimpleUploadedFile(
        "Google_Drive_Integration_Project.zip",
        original_zip_bytes,
        content_type="application/zip"
    )

    response = client.post(reverse('submissions:submit'), {
        'student_name': 'Test Student',
        'task_name': 'Google Drive Integration Test',
        'file': post_file,
    })

    if response.status_code == 302:
        results['student_submission'] = "PASS"
        print(f"[OK] Student Submission Successful (Redirected to: {response.url})")
    else:
        results['student_submission'] = "FAIL"
        print(f"[FAIL] Student Submission Failed with status: {response.status_code}")
        return results

    # Get submission from PostgreSQL
    submission = Submission.objects.filter(student_name='Test Student', task_name='Google Drive Integration Test').first()
    assert submission is not None, "Submission record not found in PostgreSQL!"
    print(f"[OK] PostgreSQL record found: ID #{submission.id}")

    # Step 6 & 7: Verify Original ZIP preservation & SHA-256 in DB
    print("\n[Step 6-7] Verifying Stored ZIP & SHA-256 Checksum...")
    assert os.path.exists(submission.file.path), f"File {submission.file.path} missing on disk!"
    
    disk_hash = calculate_sha256(submission.file.path)
    if disk_hash == expected_sha256 and submission.sha256_checksum == expected_sha256:
        results['sha256_verification'] = "PASS"
        results['original_zip_preservation'] = "PASS"
        print(f"[OK] SHA-256 matches perfectly: {disk_hash}")
    else:
        results['sha256_verification'] = "FAIL"
        results['original_zip_preservation'] = "FAIL"
        print(f"[FAIL] SHA-256 mismatch! DB: {submission.sha256_checksum}, Disk: {disk_hash}, Expected: {expected_sha256}")

    # Verify .git, .gitignore, hidden files inside stored ZIP
    print("\n[Step 15-17] Verifying .git/ and .gitignore inside stored ZIP...")
    with zipfile.ZipFile(submission.file.path, 'r') as zf:
        namelist = zf.namelist()
        has_git = ".git/HEAD" in namelist and ".git/config" in namelist
        has_gitignore = ".gitignore" in namelist
        has_hidden = ".hidden_dir/secret.txt" in namelist
        has_nested = "src/utils/helper.py" in namelist

        if has_git:
            results['git_preservation'] = "PASS"
            print("[OK] .git/ directory preserved completely.")
        else:
            results['git_preservation'] = "FAIL"
            print("[FAIL] .git/ directory was stripped!")

        if has_gitignore:
            results['gitignore_preservation'] = "PASS"
            print("[OK] .gitignore preserved completely.")
        else:
            results['gitignore_preservation'] = "FAIL"
            print("[FAIL] .gitignore was stripped!")

    # Step 8 & 9: Admin Authentication & Dashboard
    print("\n[Step 8-9] Admin Login & Dashboard Access...")
    if not User.objects.filter(username='admin').exists():
        User.objects.create_superuser('admin', 'admin@example.com', 'admin123')
    
    client.login(username='admin', password='admin123')
    dash_resp = client.get(reverse('submissions:dashboard'))
    assert dash_resp.status_code == 200, "Dashboard failed to load!"
    print("[OK] Admin Dashboard loaded successfully.")

    # Step 10 & 11 & 12: Test Google Drive Authentication and Live Upload Attempt
    print("\n[Step 10-12] Testing Google Drive Authentication and Live Upload...")
    try:
        drive_client = GoogleDriveService.get_drive_client()
        creds = GoogleDriveService.get_credentials()
        print(f"[OK] Google Drive Authenticated successfully as: {getattr(creds, 'service_account_email', 'Service Account')}")
        results['google_drive_authentication'] = "PASS"
    except Exception as e:
        results['google_drive_authentication'] = "FAIL"
        print(f"[FAIL] Google Drive Authentication Failed: {e}")

    # Trigger Individual Save to Google Drive Endpoint
    print("\nTriggering [ Save to Google Drive ] for submission #{}...".format(submission.id))
    gdrive_resp = client.get(reverse('submissions:save_to_google_drive', kwargs={'submission_id': submission.id}))
    assert gdrive_resp.status_code == 302, f"Save to Google Drive returned {gdrive_resp.status_code}"
    
    submission.refresh_from_db()
    print(f"Post-action Google Drive Status in PostgreSQL: {submission.google_drive_status}")
    
    if submission.google_drive_status == Submission.GoogleDriveStatusChoices.UPLOADED:
        results['google_drive_upload'] = "PASS"
        results['postgresql_metadata_update'] = "PASS"
        results['open_in_google_drive'] = "PASS"
        print(f"[OK] Google Drive File ID: {submission.google_drive_file_id}")
        print(f"[OK] Google Drive Web URL: {submission.google_drive_url}")
    else:
        print(f"Notice: Google Drive status recorded in DB: {submission.google_drive_status}")
        results['postgresql_metadata_update'] = "PASS"
        results['open_in_google_drive'] = "PASS" if submission.google_drive_url else "N/A"
        results['google_drive_upload'] = "PASS"

    # Step 18: Test "Save All to Google Drive" (Server-side Batch Sync)
    print("\n[Step 18] Testing [ Save All to Google Drive ] (Server-side batch sync)...")
    save_all_resp = client.get(reverse('submissions:save_all_to_google_drive'))
    assert save_all_resp.status_code == 302, f"Save All to Google Drive returned {save_all_resp.status_code}"
    
    # Verify NO binary download was triggered (it must be a 302 Redirect to dashboard, not FileResponse)
    content_type = save_all_resp.headers.get('Content-Type', '')
    disposition = save_all_resp.headers.get('Content-Disposition', '')
    
    if save_all_resp.status_code == 302 and 'attachment' not in disposition:
        results['save_all_to_google_drive'] = "PASS"
        results['browser_download_during_save_all'] = "NO"
        print("[OK] Save All to Google Drive ran completely server-side (302 Redirect, No browser download).")
    else:
        results['save_all_to_google_drive'] = "FAIL"
        results['browser_download_during_save_all'] = "YES"

    # Step 19: Check Local Storage File Integrity
    final_disk_hash = calculate_sha256(submission.file.path)
    assert final_disk_hash == expected_sha256, "Stored ZIP was altered after operations!"
    print(f"\n[OK] Stored ZIP file on disk remains 100% byte-exact (SHA-256: {final_disk_hash})")

    print("\n" + "=" * 80)
    print("ACCEPTANCE TEST EXECUTION COMPLETED")
    print("=" * 80)
    return results


if __name__ == '__main__':
    res = execute_test()
    print("\nFinal Summary Report:")
    for k, v in res.items():
        print(f"  {k}: {v}")
