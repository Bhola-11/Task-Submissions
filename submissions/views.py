import os
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.http import JsonResponse, FileResponse, HttpResponse, Http404
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST, require_GET
from django.views.decorators.csrf import ensure_csrf_cookie
from django.conf import settings

from .models import Submission
from .forms import StudentSubmissionForm, AdminLoginForm, SubmissionFilterForm
from .services import SubmissionService
from .services.google_drive_service import GoogleDriveService

logger = logging.getLogger(__name__)


def is_admin_user(user):
    """
    Check if user is authenticated and is staff or superuser.
    """
    return user.is_authenticated and (user.is_staff or user.is_superuser)


# ==========================================
# PHASE 1: STUDENT SUBMISSION PORTAL VIEWS
# ==========================================

@ensure_csrf_cookie
def submit_view(request):
    """
    Student landing page and submission handler.
    Supports both traditional POST form submissions and asynchronous AJAX uploads.
    """
    if request.method == 'POST':
        form = StudentSubmissionForm(request.POST, request.FILES)
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.POST.get('is_ajax') == 'true'

        if form.is_valid():
            try:
                submission = SubmissionService.create_submission(
                    student_name=form.cleaned_data['student_name'],
                    task_name=form.cleaned_data['task_name'],
                    uploaded_file=form.cleaned_data['file']
                )

                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'message': 'Task submitted successfully!',
                        'redirect_url': reverse('submissions:success', kwargs={'submission_id': submission.id}),
                        'submission_id': submission.id,
                        'sha256': submission.sha256_checksum,
                    })

                messages.success(request, 'Task submitted successfully!')
                return redirect('submissions:success', submission_id=submission.id)

            except Exception as e:
                logger.error(f"Failed to process submission: {str(e)}", exc_info=True)
                if is_ajax:
                    return JsonResponse({
                        'success': False,
                        'error': 'An internal server error occurred while processing your upload. Please try again.',
                    }, status=500)
                form.add_error(None, 'An error occurred while saving your submission. Please try again.')
        else:
            if is_ajax:
                errors = {}
                for field, error_list in form.errors.items():
                    errors[field] = [str(err) for err in error_list]
                return JsonResponse({
                    'success': False,
                    'errors': errors,
                }, status=400)

    else:
        form = StudentSubmissionForm()

    return render(request, 'submissions/submit.html', {
        'form': form,
    })


def success_view(request, submission_id):
    """
    Confirmation page displayed after a successful submission.
    """
    submission = get_object_or_404(Submission, id=submission_id)
    return render(request, 'submissions/success.html', {
        'submission': submission,
    })


# ==========================================
# PHASE 2 & GOOGLE DRIVE ADMIN VIEWS
# ==========================================

def admin_login_view(request):
    """
    Custom login view for administrators.
    """
    if request.user.is_authenticated and (request.user.is_staff or request.user.is_superuser):
        return redirect('submissions:dashboard')

    next_url = request.GET.get('next', 'submissions:dashboard')

    if request.method == 'POST':
        form = AdminLoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']
            user = authenticate(request, username=username, password=password)

            if user is not None and (user.is_staff or user.is_superuser):
                login(request, user)
                messages.success(request, f"Welcome back, {user.username}!")
                return redirect(next_url if next_url and next_url.startswith('/') else 'submissions:dashboard')
            else:
                messages.error(request, "Invalid administrator credentials or insufficient permissions.")
    else:
        form = AdminLoginForm()

    return render(request, 'submissions/admin_login.html', {
        'form': form,
        'next': next_url,
    })


@require_http_methods(["GET", "POST"])
def admin_logout_view(request):
    """
    Logs out the administrator and redirects to the login screen.
    """
    if request.user.is_authenticated:
        logout(request)
        messages.info(request, "You have been successfully logged out.")
    return redirect('submissions:admin_login')


@login_required(login_url='submissions:admin_login')
@user_passes_test(is_admin_user, login_url='submissions:admin_login')
def dashboard_view(request):
    """
    Custom Admin Dashboard displaying metrics, search, filtering, and submissions table.
    """
    filter_form = SubmissionFilterForm(request.GET)
    search_query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '').strip()
    gdrive_filter = request.GET.get('gdrive_status', '').strip()
    date_filter = request.GET.get('date', '').strip()

    # Queryset
    queryset = Submission.objects.all()
    queryset = SubmissionService.filter_submissions(
        queryset=queryset,
        search_query=search_query,
        status_filter=status_filter,
        date_filter=date_filter,
        gdrive_filter=gdrive_filter,
    )

    # Aggregated Summary Cards Metrics
    metrics = SubmissionService.get_dashboard_metrics()

    # Pagination: 10 items per page
    paginator = Paginator(queryset, 10)
    page = request.GET.get('page', 1)

    try:
        submissions_page = paginator.page(page)
    except PageNotAnInteger:
        submissions_page = paginator.page(1)
    except EmptyPage:
        submissions_page = paginator.page(paginator.num_pages)

    # Preserve GET parameters across pagination links
    query_params = request.GET.copy()
    if 'page' in query_params:
        del query_params['page']
    pagination_query = query_params.urlencode()

    return render(request, 'submissions/dashboard.html', {
        'submissions': submissions_page,
        'metrics': metrics,
        'filter_form': filter_form,
        'search_query': search_query,
        'status_filter': status_filter,
        'gdrive_filter': gdrive_filter,
        'date_filter': date_filter,
        'pagination_query': pagination_query,
        'oauth_connected': GoogleDriveService.is_oauth_connected(),
        'oauth_status': GoogleDriveService.get_oauth_status(),
    })


@login_required(login_url='submissions:admin_login')
@user_passes_test(is_admin_user, login_url='submissions:admin_login')
def submission_detail_view(request, submission_id):
    """
    Detailed submission inspection view with SHA-256 and Google Drive sync status.
    """
    submission = get_object_or_404(Submission, id=submission_id)
    return render(request, 'submissions/submission_detail.html', {
        'submission': submission,
    })


@login_required(login_url='submissions:admin_login')
@user_passes_test(is_admin_user, login_url='submissions:admin_login')
@require_POST
def mark_reviewed_view(request, submission_id):
    """
    Toggles or sets the status of a submission to Reviewed.
    """
    submission = get_object_or_404(Submission, id=submission_id)
    target_status = request.POST.get('status')

    if target_status in [Submission.StatusChoices.PENDING, Submission.StatusChoices.REVIEWED]:
        submission.status = target_status
    else:
        # Toggle by default
        submission.status = (
            Submission.StatusChoices.REVIEWED
            if submission.status == Submission.StatusChoices.PENDING
            else Submission.StatusChoices.PENDING
        )

    submission.save(update_fields=['status', 'updated_at'])
    messages.success(request, f"Submission #{submission.id} marked as {submission.status}.")

    next_url = request.POST.get('next') or request.META.get('HTTP_REFERER')
    if next_url and ('/admin/' in next_url or '/dashboard' in next_url or '/submissions/' in next_url):
        return redirect(next_url)
    return redirect('submissions:submission_detail', submission_id=submission.id)


@login_required(login_url='submissions:admin_login')
@user_passes_test(is_admin_user, login_url='submissions:admin_login')
def download_submission_zip_view(request, submission_id):
    """
    Serves the student's original ZIP file without modification.
    """
    submission = get_object_or_404(Submission, id=submission_id)

    if not submission.file or not os.path.exists(submission.file.path):
        logger.error(f"Requested ZIP file for submission {submission_id} does not exist on disk.")
        messages.error(request, "The requested ZIP file could not be found on server storage.")
        return redirect('submissions:submission_detail', submission_id=submission_id)

    download_filename = submission.original_filename or f"submission_{submission.id}.zip"

    # Open file for streaming response
    file_handle = open(submission.file.path, 'rb')
    response = FileResponse(file_handle, content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="{download_filename}"'
    response['Content-Length'] = submission.file_size
    return response


@login_required(login_url='submissions:admin_login')
@user_passes_test(is_admin_user, login_url='submissions:admin_login')
def download_all_zips_view(request):
    """
    Packages all student ZIP files into one master archive (All-Student-Tasks-YYYY-MM-DD.zip).
    Preserves original individual ZIPs inside the master archive.
    """
    submissions = Submission.objects.all().order_by('submitted_at')

    if not submissions.exists():
        messages.warning(request, "No submissions available to download.")
        return redirect('submissions:dashboard')

    temp_path, master_filename, missing_files, added_count = SubmissionService.generate_master_zip_file(submissions)

    if added_count == 0:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        messages.error(request, "No physical ZIP files were found on disk to package.")
        return redirect('submissions:dashboard')

    if missing_files:
        messages.warning(
            request,
            f"Master archive generated with {added_count} files. Note: {len(missing_files)} file(s) were missing on storage."
        )

    # Class for automatically cleaning up the temporary file after response streaming completes
    class CleanupFileResponse(FileResponse):
        def close(self):
            super().close()
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception as e:
                logger.error(f"Error removing temporary master zip {temp_path}: {e}")

    file_handle = open(temp_path, 'rb')
    response = CleanupFileResponse(file_handle, content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="{master_filename}"'
    return response


# ==========================================
# GOOGLE DRIVE INTEGRATION VIEWS
# ==========================================

@login_required(login_url='submissions:admin_login')
@user_passes_test(is_admin_user, login_url='submissions:admin_login')
@require_http_methods(["GET", "POST"])
def save_to_google_drive_view(request, submission_id):
    """
    Uploads an individual student's original ZIP file directly to Google Drive via Drive API.
    """
    submission = get_object_or_404(Submission, id=submission_id)
    force_reupload = request.GET.get('force') == '1' or request.POST.get('force') == '1'

    result = GoogleDriveService.upload_submission_zip(submission, force_reupload=force_reupload)

    if result['success']:
        if result.get('status') == 'already_uploaded':
            messages.info(request, f"Submission #{submission.id} is already uploaded to Google Drive.")
        else:
            messages.success(
                request,
                f"Successfully uploaded {submission.student_name}'s ZIP to Google Drive! (File ID: {result.get('file_id')})"
            )
    else:
        messages.error(
            request,
            f"Failed to upload submission #{submission.id} to Google Drive: {result.get('error')}"
        )

    next_url = request.POST.get('next') or request.GET.get('next') or request.META.get('HTTP_REFERER')
    if next_url and ('/admin/' in next_url or '/dashboard' in next_url or '/submissions/' in next_url):
        return redirect(next_url)
    return redirect('submissions:submission_detail', submission_id=submission.id)


@login_required(login_url='submissions:admin_login')
@user_passes_test(is_admin_user, login_url='submissions:admin_login')
@require_http_methods(["GET", "POST"])
def save_all_to_google_drive_view(request):
    """
    Server-side batch upload of all student ZIPs to Google Drive.
    IMPORTANT: This action does NOT download files to the admin's browser.
    Uploads original student ZIP files directly from server storage to Google Drive.
    """
    force_reupload = request.GET.get('force') == '1' or request.POST.get('force') == '1'
    queryset = Submission.objects.all().order_by('submitted_at')

    if not queryset.exists():
        messages.warning(request, "No submissions found to sync with Google Drive.")
        return redirect('submissions:dashboard')

    summary = GoogleDriveService.sync_all_submissions(queryset=queryset, force_reupload=force_reupload)

    msg = (
        f"Google Drive Sync Completed — Total: {summary['total']}, "
        f"Uploaded: {summary['uploaded']}, "
        f"Already Uploaded: {summary['already_uploaded']}, "
        f"Failed: {summary['failed']}"
    )

    if summary['failed'] == 0:
        messages.success(request, msg)
    else:
        messages.warning(request, msg + f" (See submission details for failure logs)")

    return redirect('submissions:dashboard')


# ==========================================
# GOOGLE OAUTH 2.0 AUTHORIZATION & CALLBACK
# ==========================================

@login_required(login_url='submissions:admin_login')
@user_passes_test(is_admin_user, login_url='submissions:admin_login')
def google_oauth_authorize_view(request):
    """
    Initiates Google OAuth 2.0 authorization flow for administrator with PKCE code_verifier.
    Requests offline access to acquire a refresh token for unattended background uploads.
    """
    try:
        redirect_uri = getattr(settings, 'GOOGLE_OAUTH_REDIRECT_URI', '')
        if not redirect_uri:
            redirect_uri = request.build_absolute_uri(reverse('submissions:google_oauth_callback'))

        import secrets
        state = secrets.token_urlsafe(32)
        auth_url, generated_state, code_verifier = GoogleDriveService.get_authorization_url(
            redirect_uri=redirect_uri,
            state=state
        )
        # Store state and PKCE code_verifier securely in the Django session
        request.session['google_oauth_state'] = generated_state
        request.session['google_oauth_code_verifier'] = code_verifier
        request.session.modified = True
        return redirect(auth_url)
    except FileNotFoundError as e:
        logger.error(f"Google OAuth initialization failed: {e}")
        messages.error(
            request,
            "OAuth client file (credentials.json) not found on server. "
            "Please ensure credentials.json is placed in the project root directory."
        )
        return redirect('submissions:dashboard')
    except Exception as e:
        logger.error(f"Unexpected error starting Google OAuth authorization: {e}", exc_info=True)
        messages.error(request, f"Failed to initialize Google authorization: {e}")
        return redirect('submissions:dashboard')


@login_required(login_url='submissions:admin_login')
@user_passes_test(is_admin_user, login_url='submissions:admin_login')
def google_oauth_callback_view(request):
    """
    Handles Google OAuth 2.0 callback, verifies CSRF state token,
    restores PKCE code_verifier, exchanges authorization code for access + refresh tokens,
    and securely saves credentials server-side.
    """
    error = request.GET.get('error')
    if error:
        request.session.pop('google_oauth_state', None)
        request.session.pop('google_oauth_code_verifier', None)
        logger.warning(f"Google OAuth authorization returned error: {error}")
        messages.error(request, f"Google OAuth authorization was declined or cancelled: {error}")
        return redirect('submissions:dashboard')

    code = request.GET.get('code')
    incoming_state = request.GET.get('state')
    saved_state = request.session.pop('google_oauth_state', None)
    code_verifier = request.session.pop('google_oauth_code_verifier', None)

    if not code:
        messages.error(request, "Google OAuth error: No authorization code received from Google.")
        return redirect('submissions:dashboard')

    if not saved_state or incoming_state != saved_state:
        logger.warning("OAuth CSRF state mismatch detected in callback.")
        messages.error(
            request,
            "Google OAuth security error: Invalid or expired state token. Please click 'Connect Google Drive' to try again."
        )
        return redirect('submissions:dashboard')

    if not code_verifier:
        logger.warning("OAuth PKCE code verifier missing from session in callback.")
        messages.error(
            request,
            "Google OAuth security error: Missing PKCE code verifier in session. Please start authorization again."
        )
        return redirect('submissions:dashboard')

    try:
        redirect_uri = getattr(settings, 'GOOGLE_OAUTH_REDIRECT_URI', '')
        if not redirect_uri:
            redirect_uri = request.build_absolute_uri(reverse('submissions:google_oauth_callback'))

        GoogleDriveService.exchange_code_for_token(
            code=code,
            state=incoming_state,
            code_verifier=code_verifier,
            redirect_uri=redirect_uri
        )
        messages.success(
            request,
            "Google Drive account successfully connected! Drive uploads will now use your authorized Google account with automatic offline token refresh."
        )
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error exchanging OAuth code for tokens: {e}", exc_info=True)
        if 'invalid_grant' in error_msg:
            messages.error(
                request,
                "Google OAuth token exchange failed (invalid_grant): Authorization code was expired or invalid. Please click 'Connect Google Drive' again."
            )
        else:
            messages.error(request, f"Failed to complete Google Drive connection: {error_msg}")

    return redirect('submissions:dashboard')


# ==========================================
# HEALTH CHECK VIEW (RENDER MONITORING)
# ==========================================

def health_check_view(request):
    """
    Lightweight health check endpoint for Render monitoring.
    Returns HTTP 200 without exposing sensitive data.
    """
    return JsonResponse({
        "status": "healthy",
        "service": "Student Task Submission Portal"
    }, status=200)


# ==========================================
# PHASE 3: CUSTOM ERROR VIEWS
# ==========================================

def error_400_view(request, exception=None):
    return render(request, 'submissions/errors/400.html', {
        'error_title': 'Bad Request',
        'error_message': 'The server could not understand the request due to invalid syntax or parameters.',
    }, status=400)


def error_403_view(request, exception=None):
    return render(request, 'submissions/errors/403.html', {
        'error_title': 'Access Forbidden',
        'error_message': 'You do not have permission to access the requested resource.',
    }, status=403)


def error_404_view(request, exception=None):
    return render(request, 'submissions/errors/404.html', {
        'error_title': 'Page Not Found',
        'error_message': 'The requested submission or page could not be found.',
    }, status=404)


def error_500_view(request):
    return render(request, 'submissions/errors/500.html', {
        'error_title': 'Internal Server Error',
        'error_message': 'An unexpected error occurred on the server. Our technical team has been notified.',
    }, status=500)
