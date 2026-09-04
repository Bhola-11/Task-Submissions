import io
import os
import zipfile
from unittest.mock import patch, MagicMock, mock_open
from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from submissions.models import Submission
from submissions.services import SubmissionService, re_clean_name
from submissions.services.google_drive_service import calculate_sha256, GoogleDriveService


def create_test_zip(filename="test.zip", file_data=b"hello"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr("test.txt", file_data)
        z.writestr(".gitignore", "*.tmp\n")
        z.writestr(".git/HEAD", "ref: refs/heads/main\n")
    buf.seek(0)
    return SimpleUploadedFile(filename, buf.getvalue(), content_type="application/zip")


class SubmissionServiceTests(TestCase):
    def test_create_submission_service_and_sha256(self):
        zip_file = create_test_zip("portfolio.zip")
        sub = SubmissionService.create_submission("Rahul", "Portfolio", zip_file)
        self.assertEqual(sub.student_name, "Rahul")
        self.assertEqual(sub.task_name, "Portfolio")
        self.assertEqual(sub.original_filename, "portfolio.zip")
        self.assertEqual(sub.status, Submission.StatusChoices.PENDING)
        self.assertEqual(sub.google_drive_status, Submission.GoogleDriveStatusChoices.NOT_UPLOADED)
        self.assertTrue(sub.stored_filename.startswith("submission_"))
        
        # Verify SHA-256 calculation
        self.assertIsNotNone(sub.sha256_checksum)
        self.assertEqual(len(sub.sha256_checksum), 64)
        
        # Verify exact binary checksum match on stored file
        disk_hash = calculate_sha256(sub.file.path)
        self.assertEqual(sub.sha256_checksum, disk_hash)

        # Verify ZIP contains .git and hidden files untouched
        with zipfile.ZipFile(sub.file.path, 'r') as zf:
            namelist = zf.namelist()
            self.assertIn(".gitignore", namelist)
            self.assertIn(".git/HEAD", namelist)

    def test_dashboard_metrics(self):
        sub1 = SubmissionService.create_submission("Rahul", "Portfolio", create_test_zip())
        sub2 = SubmissionService.create_submission("Aman", "E-Commerce", create_test_zip())
        sub2.status = Submission.StatusChoices.REVIEWED
        sub2.google_drive_status = Submission.GoogleDriveStatusChoices.UPLOADED
        sub2.save()

        metrics = SubmissionService.get_dashboard_metrics()
        self.assertEqual(metrics['total_submissions'], 2)
        self.assertEqual(metrics['pending_submissions'], 1)
        self.assertEqual(metrics['reviewed_submissions'], 1)
        self.assertEqual(metrics['today_submissions'], 2)
        self.assertEqual(metrics['gdrive_uploaded'], 1)
        self.assertGreater(metrics['total_storage_bytes'], 0)

    def test_master_zip_packaging_and_collision_handling(self):
        sub1 = SubmissionService.create_submission("Rahul", "Portfolio", create_test_zip("proj.zip"))
        sub2 = SubmissionService.create_submission("Rahul", "Portfolio", create_test_zip("proj2.zip"))
        sub3 = SubmissionService.create_submission("Aman", "E-Commerce", create_test_zip("ecom.zip"))

        queryset = Submission.objects.all()
        temp_path, master_filename, missing, count = SubmissionService.generate_master_zip_file(queryset)

        self.assertTrue(os.path.exists(temp_path))
        self.assertEqual(count, 3)
        self.assertEqual(len(missing), 0)
        self.assertTrue(master_filename.startswith("All-Student-Tasks-"))

        # Verify contents of master ZIP
        with zipfile.ZipFile(temp_path, 'r') as mz:
            names = mz.namelist()
            self.assertIn("Rahul_Portfolio.zip", names)
            self.assertIn("Rahul_Portfolio_2.zip", names) # Collision safe!
            self.assertIn("Aman_E-Commerce.zip", names)

            # Verify that individual entries inside master ZIP are legitimate ZIPs
            inner_zip_bytes = mz.read("Rahul_Portfolio.zip")
            self.assertTrue(inner_zip_bytes.startswith(b'PK\x03\x04'))

        # Clean up
        if os.path.exists(temp_path):
            os.remove(temp_path)

    @patch('submissions.services.google_drive_service.GoogleDriveService.get_drive_client')
    def test_google_drive_upload_success(self, mock_get_client):
        # Mock Google Drive Client
        mock_drive = MagicMock()
        mock_files = MagicMock()
        mock_create = MagicMock()
        mock_create.execute.return_value = {
            'id': 'gdrive_file_id_999',
            'name': 'Rahul_Portfolio.zip',
            'webViewLink': 'https://drive.google.com/file/d/gdrive_file_id_999/view',
            'size': '1024'
        }
        mock_files.create.return_value = mock_create
        mock_drive.files.return_value = mock_files
        mock_get_client.return_value = mock_drive

        sub = SubmissionService.create_submission("Rahul", "Portfolio", create_test_zip("port.zip"))
        result = GoogleDriveService.upload_submission_zip(sub)

        self.assertTrue(result['success'])
        self.assertEqual(result['file_id'], 'gdrive_file_id_999')
        self.assertEqual(sub.google_drive_status, Submission.GoogleDriveStatusChoices.UPLOADED)
        self.assertEqual(sub.google_drive_file_id, 'gdrive_file_id_999')
        self.assertIsNotNone(sub.google_drive_uploaded_at)

    @patch('submissions.services.google_drive_service.GoogleDriveService.get_drive_client')
    def test_sync_all_submissions_batch(self, mock_get_client):
        mock_drive = MagicMock()
        mock_files = MagicMock()
        mock_create = MagicMock()
        mock_create.execute.return_value = {
            'id': 'gdrive_batch_123',
            'name': 'test.zip',
            'webViewLink': 'https://drive.google.com/file/d/gdrive_batch_123/view',
        }
        mock_files.create.return_value = mock_create
        mock_drive.files.return_value = mock_files
        mock_get_client.return_value = mock_drive

        sub1 = SubmissionService.create_submission("Rahul", "Portfolio", create_test_zip("p.zip"))
        sub2 = SubmissionService.create_submission("Aman", "E-Commerce", create_test_zip("e.zip"))

        summary = GoogleDriveService.sync_all_submissions()
        self.assertEqual(summary['total'], 2)
        self.assertEqual(summary['uploaded'], 2)
        self.assertEqual(summary['failed'], 0)

    def test_get_oauth_status_not_connected_when_no_token(self):
        with patch('os.path.exists') as mock_exists:
            mock_exists.return_value = False
            status = GoogleDriveService.get_oauth_status()
            self.assertEqual(status, 'Not Connected')
            self.assertFalse(GoogleDriveService.is_oauth_connected())

    @patch('google.oauth2.credentials.Credentials.from_authorized_user_file')
    def test_get_oauth_status_connected_when_valid(self, mock_from_file):
        with patch('os.path.exists') as mock_exists:
            mock_exists.return_value = True
            mock_creds = MagicMock()
            mock_creds.valid = True
            mock_from_file.return_value = mock_creds
            status = GoogleDriveService.get_oauth_status()
            self.assertEqual(status, 'Connected')
            self.assertTrue(GoogleDriveService.is_oauth_connected())

    @patch('google_auth_oauthlib.flow.Flow.from_client_secrets_file')
    def test_exchange_code_for_token_sets_verifier(self, mock_flow_from_file):
        mock_flow = MagicMock()
        mock_creds = MagicMock()
        mock_creds.to_json.return_value = '{"token": "xyz"}'
        mock_flow.credentials = mock_creds
        mock_flow_from_file.return_value = mock_flow

        with patch('submissions.services.google_drive_service.GoogleDriveService.get_client_secrets_path') as mock_path, \
             patch('builtins.open', mock_open()):
            mock_path.return_value = 'credentials.json'
            creds = GoogleDriveService.exchange_code_for_token(
                code='test_code',
                state='test_state',
                code_verifier='test_verifier_123',
                redirect_uri='http://127.0.0.1:8000/google/oauth2/callback/'
            )
            self.assertEqual(mock_flow.code_verifier, 'test_verifier_123')
            mock_flow.fetch_token.assert_called_once_with(code='test_code', code_verifier='test_verifier_123')
            self.assertEqual(creds, mock_creds)
