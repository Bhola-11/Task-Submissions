import io
import zipfile
from unittest.mock import patch, MagicMock
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from submissions.models import Submission


def get_valid_zip_file(filename="assignment.zip"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr("app.py", "print('hello student')")
    buf.seek(0)
    return SimpleUploadedFile(filename, buf.getvalue(), content_type="application/zip")


class SubmissionsViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin_user = User.objects.create_superuser(
            username='admin_test',
            password='Password123!',
            email='admin@example.com'
        )
        self.regular_user = User.objects.create_user(
            username='student_user',
            password='Password123!'
        )

    def test_student_submit_page_loads(self):
        response = self.client.get(reverse('submissions:submit'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Student Task Submission")

    def test_student_valid_submission_post(self):
        zip_file = get_valid_zip_file("portfolio.zip")
        response = self.client.post(reverse('submissions:submit'), {
            'student_name': 'Rahul',
            'task_name': 'Portfolio',
            'file': zip_file,
        })
        self.assertEqual(response.status_code, 302)
        sub = Submission.objects.first()
        self.assertIsNotNone(sub)
        self.assertEqual(sub.student_name, 'Rahul')
        self.assertEqual(sub.task_name, 'Portfolio')

    def test_student_submission_ajax(self):
        zip_file = get_valid_zip_file("chatbot.zip")
        response = self.client.post(
            reverse('submissions:submit'),
            {
                'student_name': 'Priya',
                'task_name': 'AI Chatbot',
                'file': zip_file,
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 200)
        json_data = response.json()
        self.assertTrue(json_data.get('success'))
        self.assertIn('redirect_url', json_data)

    def test_student_submission_validation_errors(self):
        # Missing task name and invalid file
        response = self.client.post(reverse('submissions:submit'), {
            'student_name': 'R',  # Too short
            'task_name': '',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context['form'], 'student_name', 'Student name must be at least 2 characters long.')
        self.assertFormError(response.context['form'], 'task_name', 'This field is required.')

    def test_success_page(self):
        zip_file = get_valid_zip_file()
        response = self.client.post(reverse('submissions:submit'), {
            'student_name': 'Aman',
            'task_name': 'E-Commerce',
            'file': zip_file,
        })
        sub = Submission.objects.first()
        success_response = self.client.get(reverse('submissions:success', kwargs={'submission_id': sub.id}))
        self.assertEqual(success_response.status_code, 200)
        self.assertContains(success_response, "Task Submitted Successfully")
        self.assertContains(success_response, "Aman")
        self.assertContains(success_response, "E-Commerce")

    def test_admin_dashboard_protected(self):
        # Anonymous user should be redirected to login
        response = self.client.get(reverse('submissions:dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('admin/login', response.url)

    def test_admin_login_and_dashboard_access(self):
        # Login
        login_response = self.client.post(reverse('submissions:admin_login'), {
            'username': 'admin_test',
            'password': 'Password123!',
        })
        self.assertEqual(login_response.status_code, 302)

        # Dashboard
        dash_response = self.client.get(reverse('submissions:dashboard'))
        self.assertEqual(dash_response.status_code, 200)
        self.assertContains(dash_response, "Student Task Submissions")

    def test_admin_submission_detail_and_status_toggle(self):
        self.client.login(username='admin_test', password='Password123!')
        zip_file = get_valid_zip_file()
        sub = Submission.objects.create(
            student_name="Test Student",
            task_name="Test Task",
            original_filename="test.zip",
            stored_filename="submission_test.zip",
            file=zip_file,
            file_size=100,
            status=Submission.StatusChoices.PENDING
        )

        # Detail view
        detail_response = self.client.get(reverse('submissions:submission_detail', kwargs={'submission_id': sub.id}))
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, "Test Student")

        # Mark reviewed
        toggle_response = self.client.post(reverse('submissions:mark_reviewed', kwargs={'submission_id': sub.id}))
        self.assertEqual(toggle_response.status_code, 302)
        sub.refresh_from_db()
        self.assertEqual(sub.status, Submission.StatusChoices.REVIEWED)

    def test_individual_zip_download(self):
        self.client.login(username='admin_test', password='Password123!')
        zip_file = get_valid_zip_file("my_code.zip")
        sub = Submission.objects.create(
            student_name="Rahul",
            task_name="Portfolio",
            original_filename="my_code.zip",
            stored_filename="submission_rahul.zip",
            file=zip_file,
            file_size=len(zip_file),
        )

        response = self.client.get(reverse('submissions:download_submission_zip', kwargs={'submission_id': sub.id}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/zip')
        self.assertIn('my_code.zip', response['Content-Disposition'])

    def test_download_all_zips(self):
        self.client.login(username='admin_test', password='Password123!')
        sub1 = Submission.objects.create(
            student_name="Rahul",
            task_name="Portfolio",
            original_filename="p.zip",
            stored_filename="sub1.zip",
            file=get_valid_zip_file("p.zip"),
            file_size=100,
        )
        sub2 = Submission.objects.create(
            student_name="Aman",
            task_name="E-Commerce",
            original_filename="e.zip",
            stored_filename="sub2.zip",
            file=get_valid_zip_file("e.zip"),
            file_size=100,
        )

        response = self.client.get(reverse('submissions:download_all_zips'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/zip')
        self.assertIn('All-Student-Tasks-', response['Content-Disposition'])

    def test_save_to_google_drive_view(self):
        self.client.login(username='admin_test', password='Password123!')
        sub = Submission.objects.create(
            student_name="Rahul",
            task_name="Portfolio",
            original_filename="portfolio.zip",
            stored_filename="submission_test.zip",
            file=get_valid_zip_file(),
            file_size=100,
        )

        with patch('submissions.services.google_drive_service.GoogleDriveService.upload_submission_zip') as mock_upload:
            mock_upload.return_value = {
                'success': True,
                'status': 'uploaded',
                'file_id': 'file_123',
                'url': 'https://drive.google.com/file/d/file_123/view',
            }
            response = self.client.get(reverse('submissions:save_to_google_drive', kwargs={'submission_id': sub.id}))
            self.assertEqual(response.status_code, 302)
            mock_upload.assert_called_once()

    def test_save_all_to_google_drive_view(self):
        self.client.login(username='admin_test', password='Password123!')
        sub = Submission.objects.create(
            student_name="Aman",
            task_name="E-Commerce",
            original_filename="ecommerce.zip",
            stored_filename="submission_test.zip",
            file=get_valid_zip_file(),
            file_size=100,
        )

        with patch('submissions.services.google_drive_service.GoogleDriveService.sync_all_submissions') as mock_sync:
            mock_sync.return_value = {
                'total': 1,
                'uploaded': 1,
                'already_uploaded': 0,
                'failed': 0,
                'skipped': 0,
                'errors': [],
            }
            response = self.client.get(reverse('submissions:save_all_to_google_drive'))
            self.assertEqual(response.status_code, 302)
            mock_sync.assert_called_once()

    def test_oauth_authorize_protected(self):
        # Anonymous user cannot access OAuth authorize
        response = self.client.get(reverse('submissions:google_oauth_authorize'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('admin/login', response.url)

    def test_oauth_authorize_admin_redirect(self):
        self.client.login(username='admin_test', password='Password123!')
        with patch('submissions.services.google_drive_service.GoogleDriveService.get_authorization_url') as mock_auth:
            mock_auth.return_value = (
                'https://accounts.google.com/o/oauth2/v2/auth?client_id=test',
                'test_state_123',
                'test_code_verifier_xyz_123'
            )
            response = self.client.get(reverse('submissions:google_oauth_authorize'))
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.url, 'https://accounts.google.com/o/oauth2/v2/auth?client_id=test')
            self.assertEqual(self.client.session.get('google_oauth_state'), 'test_state_123')
            self.assertEqual(self.client.session.get('google_oauth_code_verifier'), 'test_code_verifier_xyz_123')

    def test_oauth_callback_success(self):
        self.client.login(username='admin_test', password='Password123!')
        # Set session state and PKCE verifier
        session = self.client.session
        session['google_oauth_state'] = 'test_state_123'
        session['google_oauth_code_verifier'] = 'test_verifier_789'
        session.save()

        with patch('submissions.services.google_drive_service.GoogleDriveService.exchange_code_for_token') as mock_exchange:
            mock_exchange.return_value = MagicMock()
            response = self.client.get(reverse('submissions:google_oauth_callback'), {
                'code': 'test_code_456',
                'state': 'test_state_123',
            })
            self.assertEqual(response.status_code, 302)
            self.assertIn('/admin/dashboard', response.url)
            mock_exchange.assert_called_once()
            # Verify code_verifier was passed to exchange
            _, kwargs = mock_exchange.call_args
            self.assertEqual(kwargs.get('code_verifier'), 'test_verifier_789')
            # Verify session was cleaned up
            self.assertNotIn('google_oauth_state', self.client.session)
            self.assertNotIn('google_oauth_code_verifier', self.client.session)

    def test_oauth_callback_missing_verifier(self):
        self.client.login(username='admin_test', password='Password123!')
        session = self.client.session
        session['google_oauth_state'] = 'test_state_123'
        # No code_verifier in session
        session.save()

        response = self.client.get(reverse('submissions:google_oauth_callback'), {
            'code': 'test_code_456',
            'state': 'test_state_123',
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/dashboard', response.url)

    def test_oauth_callback_state_mismatch(self):
        self.client.login(username='admin_test', password='Password123!')
        session = self.client.session
        session['google_oauth_state'] = 'correct_state'
        session['google_oauth_code_verifier'] = 'test_verifier'
        session.save()

        response = self.client.get(reverse('submissions:google_oauth_callback'), {
            'code': 'test_code_456',
            'state': 'wrong_state',
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/dashboard', response.url)

    def test_oauth_callback_error_handling(self):
        self.client.login(username='admin_test', password='Password123!')
        response = self.client.get(reverse('submissions:google_oauth_callback'), {
            'error': 'access_denied',
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/dashboard', response.url)

    def test_health_check_endpoint(self):
        response = self.client.get(reverse('submissions:health_check'))
        self.assertEqual(response.status_code, 200)
        json_data = response.json()
        self.assertEqual(json_data.get('status'), 'healthy')
        self.assertEqual(json_data.get('service'), 'Student Task Submission Portal')
