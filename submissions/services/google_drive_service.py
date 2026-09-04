import os
import hashlib
import logging
from typing import Optional, Dict, Any
from django.conf import settings
from django.utils import timezone
from django.utils.text import slugify

logger = logging.getLogger(__name__)

# Scopes required for Google Drive API
DRIVE_SCOPES = [
    'https://www.googleapis.com/auth/drive.file',
    'https://www.googleapis.com/auth/drive'
]


def calculate_sha256(file_path_or_obj, chunk_size: int = 65536) -> str:
    """
    Computes SHA-256 checksum of a file without extracting or modifying it.
    Supports both file paths and open file-like objects (e.g. UploadedFile).
    """
    sha256_hash = hashlib.sha256()

    if isinstance(file_path_or_obj, str):
        if not os.path.exists(file_path_or_obj):
            raise FileNotFoundError(f"File not found: {file_path_or_obj}")
        with open(file_path_or_obj, 'rb') as f:
            for chunk in iter(lambda: f.read(chunk_size), b''):
                sha256_hash.update(chunk)
    else:
        # File-like object (e.g. Django UploadedFile)
        original_pos = 0
        try:
            original_pos = file_path_or_obj.tell()
            file_path_or_obj.seek(0)
        except Exception:
            pass

        for chunk in iter(lambda: file_path_or_obj.read(chunk_size), b''):
            sha256_hash.update(chunk)

        try:
            file_path_or_obj.seek(original_pos)
        except Exception:
            pass

    return sha256_hash.hexdigest()


import base64
import json
from cryptography.fernet import Fernet


def get_token_cipher() -> Fernet:
    """
    Derives a deterministic 32-byte Fernet key from Django SECRET_KEY for AES token encryption.
    """
    secret = getattr(settings, 'SECRET_KEY', 'default-django-secret-key-fallback')
    key_bytes = hashlib.sha256(secret.encode('utf-8')).digest()
    return Fernet(base64.urlsafe_b64encode(key_bytes))


def encrypt_token_json(raw_json: str) -> str:
    """Encrypts raw JSON token string using AES-Fernet."""
    return get_token_cipher().encrypt(raw_json.encode('utf-8')).decode('utf-8')


def decrypt_token_json(encrypted_str: str) -> str:
    """Decrypts AES-Fernet encrypted token string to raw JSON."""
    return get_token_cipher().decrypt(encrypted_str.encode('utf-8')).decode('utf-8')


class GoogleDriveService:
    """
    Dedicated service for authenticating and uploading student ZIP files
    directly to Google Drive using the official Google Drive API.
    Uses Google OAuth 2.0 User Credentials with persistent Neon PostgreSQL token storage.
    """

    @classmethod
    def get_client_secrets_path(cls) -> Optional[str]:
        """
        Resolves the absolute path to the Google OAuth 2.0 client secrets file (credentials.json).
        Supports Render Secret Files (/etc/secrets/credentials.json), custom paths, and BASE_DIR.
        """
        client_file = getattr(settings, 'GOOGLE_OAUTH_CLIENT_FILE', 'credentials.json')
        if client_file and os.path.isabs(client_file) and os.path.exists(client_file):
            return client_file

        if client_file:
            base_dir = getattr(settings, 'BASE_DIR', None)
            if base_dir:
                candidate = os.path.join(str(base_dir), client_file)
                if os.path.exists(candidate):
                    return candidate

        # Check Render standard secret file path
        render_secret = '/etc/secrets/credentials.json'
        if os.path.exists(render_secret):
            return render_secret

        # Check default credentials.json in BASE_DIR
        base_dir = getattr(settings, 'BASE_DIR', None)
        if base_dir:
            default_path = os.path.join(str(base_dir), 'credentials.json')
            if os.path.exists(default_path):
                return default_path

        return None

    @classmethod
    def get_token_path(cls) -> str:
        """
        Resolves the path to local token.json (used as secondary local storage).
        """
        token_file = getattr(settings, 'GOOGLE_OAUTH_TOKEN_FILE', 'token.json')
        if os.path.isabs(token_file):
            return token_file
        base_dir = getattr(settings, 'BASE_DIR', None)
        if base_dir:
            return os.path.join(str(base_dir), token_file)
        return token_file

    @classmethod
    def get_oauth_credentials(cls):
        """
        Loads and refreshes OAuth 2.0 user credentials.
        Priority:
        1. Neon PostgreSQL database (GoogleOAuthCredential model - survives Render redeploys)
        2. Local filesystem token.json (fallback for local dev)
        Automatically handles offline token refreshing.
        """
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from submissions.models import GoogleOAuthCredential

        # 1. Try loading from Neon PostgreSQL
        try:
            db_cred = GoogleOAuthCredential.objects.order_by('-updated_at').first()
            if db_cred and db_cred.encrypted_token_data:
                try:
                    decrypted_raw = decrypt_token_json(db_cred.encrypted_token_data)
                    info = json.loads(decrypted_raw)
                    creds = Credentials.from_authorized_user_info(info, scopes=DRIVE_SCOPES)
                    if creds:
                        if creds.expired and creds.refresh_token:
                            logger.info("Refreshing expired Google OAuth 2.0 access token via refresh token from DB...")
                            creds.refresh(Request())
                            # Update Neon DB with refreshed token
                            db_cred.encrypted_token_data = encrypt_token_json(creds.to_json())
                            db_cred.save(update_fields=['encrypted_token_data', 'updated_at'])
                            logger.info("Google OAuth 2.0 access token refreshed and saved to Neon PostgreSQL.")

                        if creds.valid:
                            return creds
                except Exception as db_err:
                    logger.error(f"Error decrypting or using Google OAuth credentials from database: {db_err}")
        except Exception as e:
            logger.warning(f"Could not query GoogleOAuthCredential table: {e}")

        # 2. Fallback to local token.json
        token_path = cls.get_token_path()
        if os.path.exists(token_path):
            try:
                creds = Credentials.from_authorized_user_file(token_path, scopes=DRIVE_SCOPES)
                if creds:
                    if creds.expired and creds.refresh_token:
                        logger.info("Refreshing expired Google OAuth 2.0 access token from file...")
                        creds.refresh(Request())
                        with open(token_path, 'w', encoding='utf-8') as token_out:
                            token_out.write(creds.to_json())
                        logger.info("Google OAuth 2.0 access token refreshed and saved to token.json.")

                    if creds.valid:
                        # Synchronize into DB if not present
                        try:
                            if not GoogleOAuthCredential.objects.exists():
                                GoogleOAuthCredential.objects.create(
                                    encrypted_token_data=encrypt_token_json(creds.to_json())
                                )
                        except Exception:
                            pass
                        return creds
            except Exception as e:
                logger.error(f"Error loading Google OAuth credentials from {token_path}: {e}")

        return None

    @classmethod
    def get_service_account_credentials(cls):
        """
        Retrieves Google Service Account credentials from environment or file.
        """
        from google.oauth2 import service_account

        service_account_file = getattr(settings, 'GOOGLE_SERVICE_ACCOUNT_FILE', None)
        if service_account_file:
            if not os.path.isabs(service_account_file) and not os.path.exists(service_account_file):
                base_dir = getattr(settings, 'BASE_DIR', None)
                if base_dir:
                    candidate = os.path.join(str(base_dir), service_account_file)
                    if os.path.exists(candidate):
                        service_account_file = candidate

            if os.path.exists(service_account_file):
                return service_account.Credentials.from_service_account_file(
                    service_account_file,
                    scopes=DRIVE_SCOPES
                )

        raw_json = os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON_RAW')
        if raw_json:
            import json
            info = json.loads(raw_json)
            return service_account.Credentials.from_service_account_info(
                info,
                scopes=DRIVE_SCOPES
            )

        return None

    @classmethod
    def is_oauth_connected(cls) -> bool:
        """
        Returns True if valid OAuth 2.0 user credentials exist on server.
        """
        creds = cls.get_oauth_credentials()
        return creds is not None and (creds.valid or bool(creds.refresh_token))

    @classmethod
    def get_authorization_url(cls, redirect_uri: str, state: Optional[str] = None):
        """
        Generates Google OAuth 2.0 authorization consent URL requesting offline access (refresh tokens).
        Returns (auth_url, generated_state, code_verifier).
        """
        from google_auth_oauthlib.flow import Flow

        client_secrets_path = cls.get_client_secrets_path()
        if not client_secrets_path or not os.path.exists(client_secrets_path):
            raise FileNotFoundError(
                "Google OAuth 2.0 client secrets file (credentials.json) not found on server. "
                "Please place your credentials.json in the project root or configure GOOGLE_OAUTH_CLIENT_FILE in .env."
            )

        flow = Flow.from_client_secrets_file(
            client_secrets_path,
            scopes=DRIVE_SCOPES,
            redirect_uri=redirect_uri
        )

        auth_url, generated_state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent',
            state=state
        )
        code_verifier = getattr(flow, 'code_verifier', None)
        return auth_url, generated_state, code_verifier

    @classmethod
    def exchange_code_for_token(
        cls,
        code: str,
        state: Optional[str] = None,
        code_verifier: Optional[str] = None,
        redirect_uri: Optional[str] = None
    ):
        """
        Exchanges the authorization code for access + refresh tokens using the exact
        PKCE code_verifier generated during the authorization request, and saves to token.json.
        """
        from google_auth_oauthlib.flow import Flow

        client_secrets_path = cls.get_client_secrets_path()
        if not client_secrets_path or not os.path.exists(client_secrets_path):
            raise FileNotFoundError(
                "Google OAuth 2.0 client secrets file (credentials.json) not found on server."
            )

        flow = Flow.from_client_secrets_file(
            client_secrets_path,
            scopes=DRIVE_SCOPES,
            state=state,
            redirect_uri=redirect_uri
        )

        # Restore the exact PKCE code_verifier generated during authorization
        if code_verifier:
            flow.code_verifier = code_verifier

        flow.fetch_token(code=code, code_verifier=code_verifier)
        creds = flow.credentials
        raw_token_json = creds.to_json()

        # 1. Save encrypted credentials in Neon PostgreSQL
        from submissions.models import GoogleOAuthCredential
        try:
            encrypted_data = encrypt_token_json(raw_token_json)
            GoogleOAuthCredential.objects.all().delete()  # Keep single active record
            GoogleOAuthCredential.objects.create(encrypted_token_data=encrypted_data)
            logger.info("Google OAuth 2.0 encrypted credentials saved to Neon PostgreSQL.")
        except Exception as e:
            logger.error(f"Error persisting Google OAuth credentials to database: {e}")

        # 2. Also write to local token.json for local development convenience
        try:
            token_path = cls.get_token_path()
            with open(token_path, 'w', encoding='utf-8') as f:
                f.write(raw_token_json)
            logger.info(f"Google OAuth 2.0 tokens saved locally to {token_path}")
        except Exception as e:
            logger.warning(f"Could not write to local token file (expected on read-only/ephemeral filesystems): {e}")

        return creds

    @classmethod
    def remove_stale_token(cls) -> bool:
        """
        Safely removes OAuth credentials from both Neon PostgreSQL and local token.json.
        """
        from submissions.models import GoogleOAuthCredential
        removed = False
        try:
            count, _ = GoogleOAuthCredential.objects.all().delete()
            if count > 0:
                removed = True
                logger.info("Deleted GoogleOAuthCredential records from database.")
        except Exception as e:
            logger.error(f"Error removing credentials from DB: {e}")

        token_path = cls.get_token_path()
        if os.path.exists(token_path):
            try:
                os.remove(token_path)
                removed = True
                logger.info(f"Stale local OAuth token removed: {token_path}")
            except Exception as e:
                logger.error(f"Error removing stale token {token_path}: {e}")
        return removed

    @classmethod
    def get_oauth_status(cls) -> str:
        """
        Returns the current Google Drive OAuth connection status:
        - 'Connected': Valid credentials or refreshed token available.
        - 'Reconnect Required': Token exists but expired, non-refreshable, or revoked.
        - 'Not Connected': No OAuth token file found.
        """
        token_path = cls.get_token_path()
        if not os.path.exists(token_path):
            return 'Not Connected'

        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request

        try:
            creds = Credentials.from_authorized_user_file(token_path, scopes=DRIVE_SCOPES)
            if not creds:
                return 'Reconnect Required'

            if creds.valid:
                return 'Connected'

            if creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    with open(token_path, 'w', encoding='utf-8') as f:
                        f.write(creds.to_json())
                    return 'Connected'
                except Exception as refresh_err:
                    logger.warning(f"OAuth token refresh attempt failed: {refresh_err}")
                    return 'Reconnect Required'

            return 'Reconnect Required'
        except Exception as e:
            logger.error(f"Error inspecting Google OAuth status: {e}")
            return 'Reconnect Required'

    @classmethod
    def is_oauth_connected(cls) -> bool:
        """
        Returns True if active and valid OAuth 2.0 user credentials exist on server.
        """
        return cls.get_oauth_status() == 'Connected'

    @classmethod
    def get_credentials(cls):
        """
        Retrieves active Google OAuth 2.0 User credentials.
        Exclusively uses OAuth 2.0 user credentials for personal Google Drive uploads.
        """
        return cls.get_oauth_credentials()

    @classmethod
    def get_drive_client(cls):
        """
        Builds and returns the Google Drive v3 resource client using OAuth 2.0 credentials.
        """
        from googleapiclient.discovery import build

        creds = cls.get_credentials()
        if not creds:
            status = cls.get_oauth_status()
            if status == 'Reconnect Required':
                raise ValueError("Google Drive authorization expired or revoked. Please click 'Reconnect Google Drive' in the Admin Dashboard.")
            raise ValueError("Google Drive is not connected. Please click 'Connect Google Drive' in the Admin Dashboard to authorize.")

        return build('drive', 'v3', credentials=creds, cache_discovery=False)

    @classmethod
    def generate_drive_filename(cls, submission) -> str:
        """
        Generates a collision-safe, clean filename for Google Drive while preserving
        the original ZIP extension and outer naming format.
        Format: <StudentName>_<TaskName>_<OriginalFilename> or <StudentName>_<TaskName>.zip
        """
        from submissions.services import re_clean_name

        student_clean = re_clean_name(submission.student_name)
        task_clean = re_clean_name(submission.task_name)
        orig_clean = re_clean_name(os.path.splitext(submission.original_filename)[0])

        if orig_clean and orig_clean.lower() not in (student_clean.lower(), task_clean.lower(), 'project', 'submission', 'task'):
            drive_filename = f"{student_clean}_{task_clean}_{orig_clean}.zip"
        else:
            drive_filename = f"{student_clean}_{task_clean}.zip"

        return drive_filename

    @classmethod
    def upload_submission_zip(cls, submission, folder_id: Optional[str] = None, force_reupload: bool = False) -> Dict[str, Any]:
        """
        Uploads the student's ORIGINAL ZIP file to Google Drive.
        CRITICAL: Never extracts, unpacks, or modifies ZIP contents.
        """
        from googleapiclient.http import MediaFileUpload
        from googleapiclient.errors import HttpError

        # Check if already uploaded
        if (
            submission.google_drive_status == submission.GoogleDriveStatusChoices.UPLOADED
            and submission.google_drive_file_id
            and not force_reupload
        ):
            return {
                'success': True,
                'status': 'already_uploaded',
                'file_id': submission.google_drive_file_id,
                'url': submission.google_drive_url,
                'message': f"Submission #{submission.id} is already uploaded to Google Drive.",
            }

        # Check physical file on disk
        if not submission.file or not os.path.exists(submission.file.path):
            err_msg = f"Physical file missing on server disk: {submission.file}"
            submission.google_drive_status = submission.GoogleDriveStatusChoices.FAILED
            submission.google_drive_error = err_msg
            submission.save(update_fields=['google_drive_status', 'google_drive_error', 'updated_at'])
            return {
                'success': False,
                'status': 'file_missing',
                'error': err_msg,
            }

        target_folder = folder_id or getattr(settings, 'GOOGLE_DRIVE_FOLDER_ID', '') or ''
        drive_filename = cls.generate_drive_filename(submission)

        try:
            drive_service = cls.get_drive_client()

            file_metadata = {
                'name': drive_filename,
                'mimeType': 'application/zip',
                'description': (
                    f"Student: {submission.student_name} | Task: {submission.task_name} | "
                    f"Original File: {submission.original_filename} | SHA256: {submission.sha256_checksum or 'N/A'}"
                )
            }

            if target_folder:
                file_metadata['parents'] = [target_folder]

            # Stream original binary file via resumable MediaFileUpload
            media = MediaFileUpload(
                submission.file.path,
                mimetype='application/zip',
                resumable=True
            )

            logger.info(
                f"Initiating Google Drive upload for submission ID {submission.id} ('{drive_filename}')..."
            )

            drive_file = drive_service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, name, webViewLink, webContentLink, size',
                supportsAllDrives=True
            ).execute()

            file_id = drive_file.get('id')
            web_url = drive_file.get('webViewLink') or f"https://drive.google.com/file/d/{file_id}/view"

            # Update PostgreSQL record
            submission.google_drive_file_id = file_id
            submission.google_drive_url = web_url
            submission.google_drive_status = submission.GoogleDriveStatusChoices.UPLOADED
            submission.google_drive_uploaded_at = timezone.now()
            submission.google_drive_error = None
            submission.save(update_fields=[
                'google_drive_file_id',
                'google_drive_url',
                'google_drive_status',
                'google_drive_uploaded_at',
                'google_drive_error',
                'updated_at'
            ])

            logger.info(
                f"Successfully uploaded submission ID {submission.id} to Google Drive: FileID={file_id}"
            )

            return {
                'success': True,
                'status': 'uploaded',
                'file_id': file_id,
                'url': web_url,
                'filename': drive_filename,
                'message': f"Successfully uploaded '{drive_filename}' to Google Drive.",
            }

        except Exception as e:
            error_details = str(e)
            if 'storageQuotaExceeded' in error_details or 'Service Accounts do not have storage quota' in error_details:
                user_friendly_error = (
                    "Service Accounts do not have personal storage quota on personal 'My Drive' folders. "
                    "To upload via Service Account, please share a Google Workspace 'Shared Drive' folder with the service account "
                    "or enable Domain-Wide Delegation."
                )
                error_details = f"{user_friendly_error} (Technical details: {error_details})"
            
            logger.error(
                f"Google Drive upload failed for submission ID {submission.id}: {error_details}",
                exc_info=True
            )

            submission.google_drive_status = submission.GoogleDriveStatusChoices.FAILED
            submission.google_drive_error = error_details
            submission.save(update_fields=['google_drive_status', 'google_drive_error', 'updated_at'])

            return {
                'success': False,
                'status': 'failed',
                'error': error_details,
                'message': f"Google Drive upload failed: {error_details}"
            }

    @classmethod
    def sync_all_submissions(cls, queryset=None, folder_id: Optional[str] = None, force_reupload: bool = False) -> Dict[str, Any]:
        """
        Executes server-side batch upload of all student task ZIPs to Google Drive.
        Preserves original student ZIP files intact.
        Returns a detailed summary report of uploaded, already uploaded, skipped, and failed items.
        """
        from submissions.models import Submission

        if queryset is None:
            queryset = Submission.objects.all().order_by('submitted_at')

        total = queryset.count()
        uploaded_count = 0
        already_uploaded_count = 0
        failed_count = 0
        skipped_count = 0
        errors = []

        for sub in queryset.iterator():
            # Check if file exists on disk
            if not sub.file or not os.path.exists(sub.file.path):
                skipped_count += 1
                errors.append(f"Submission #{sub.id} ({sub.student_name}): File missing on server disk.")
                continue

            # Check if already uploaded
            if (
                sub.google_drive_status == sub.GoogleDriveStatusChoices.UPLOADED
                and sub.google_drive_file_id
                and not force_reupload
            ):
                already_uploaded_count += 1
                continue

            # Upload original ZIP
            result = cls.upload_submission_zip(sub, folder_id=folder_id, force_reupload=force_reupload)

            if result['success']:
                if result.get('status') == 'already_uploaded':
                    already_uploaded_count += 1
                else:
                    uploaded_count += 1
            else:
                failed_count += 1
                errors.append(f"Submission #{sub.id} ({sub.student_name}): {result.get('error')}")

        return {
            'total': total,
            'uploaded': uploaded_count,
            'already_uploaded': already_uploaded_count,
            'failed': failed_count,
            'skipped': skipped_count,
            'errors': errors,
        }
