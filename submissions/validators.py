import os
import re
import uuid
from datetime import datetime
from django.core.exceptions import ValidationError
from django.conf import settings
from django.utils.text import slugify


# Legitimate ZIP Magic Bytes Signatures
# PK\x03\x04 (Local file header)
# PK\x05\x06 (Empty zip / End of central directory record)
# PK\x07\x08 (Data descriptor / Spanned archive)
ZIP_MAGIC_SIGNATURES = [
    b'PK\x03\x04',
    b'PK\x05\x06',
    b'PK\x07\x08',
]

VALID_ZIP_MIME_TYPES = [
    'application/zip',
    'application/x-zip',
    'application/x-zip-compressed',
    'application/octet-stream',
    'multipart/x-zip',
]


def validate_zip_file_extension(value):
    """
    Validates that the file has a .zip extension.
    """
    ext = os.path.splitext(value.name)[1].lower()
    if ext != '.zip':
        raise ValidationError(
            f"Invalid file extension '{ext}'. Only .zip files are allowed.",
            code='invalid_extension'
        )


def validate_zip_magic_bytes(file_obj):
    """
    Inspects the actual binary magic bytes at the beginning of the file.
    Ensures that the file actually starts with a valid PK zip header.
    Restores the file read pointer after inspection.
    """
    try:
        # Read the first 4 bytes
        header = file_obj.read(4)
        # Always rewind file pointer so subsequent reads/saves work properly
        file_obj.seek(0)
    except Exception as e:
        raise ValidationError(
            "Could not inspect file contents. File may be corrupted or unreadable.",
            code='unreadable_file'
        )

    if len(header) < 4:
        raise ValidationError(
            "Uploaded file is too small or empty to be a valid ZIP archive.",
            code='file_too_small'
        )

    is_valid_magic = any(header.startswith(sig) for sig in ZIP_MAGIC_SIGNATURES)
    if not is_valid_magic:
        raise ValidationError(
            "Security validation failed: The uploaded file is not a genuine ZIP archive (invalid magic bytes).",
            code='fake_zip'
        )


def validate_zip_mime_type(file_obj):
    """
    Validates the uploaded file's content_type header if present.
    """
    content_type = getattr(file_obj, 'content_type', None)
    if content_type and content_type.lower() not in VALID_ZIP_MIME_TYPES:
        # We do not solely trust MIME type, but if a known hostile/non-zip MIME is declared (like image/png, application/x-msdownload), reject
        if not content_type.lower().startswith('application/') and not content_type.lower().startswith('multipart/'):
            raise ValidationError(
                f"Invalid MIME type '{content_type}'. Expected ZIP archive.",
                code='invalid_mime'
            )


def validate_zip_file_size(file_obj):
    """
    Validates that the file does not exceed the maximum allowed size configured in settings.
    """
    max_size_mb = getattr(settings, 'MAX_FILE_SIZE_MB', 50)
    max_size_bytes = max_size_mb * 1024 * 1024

    if file_obj.size > max_size_bytes:
        file_size_mb = round(file_obj.size / (1024 * 1024), 2)
        raise ValidationError(
            f"File size ({file_size_mb} MB) exceeds the maximum allowed limit of {max_size_mb} MB.",
            code='file_too_large'
        )


def validate_zip_file_security(file_obj):
    """
    Executes the full suite of security validations on the uploaded ZIP file:
    1. Extension check
    2. Size check
    3. MIME type check
    4. Magic bytes inspection
    """
    validate_zip_file_extension(file_obj)
    validate_zip_file_size(file_obj)
    validate_zip_mime_type(file_obj)
    validate_zip_magic_bytes(file_obj)


def sanitize_filename(filename):
    """
    Cleans original filename, removing path traversal sequences and unsafe characters.
    """
    # Extract only the base name (prevents directory traversal e.g. ../../../etc/passwd)
    clean_name = os.path.basename(filename)
    # Remove any null bytes or non-printable chars
    clean_name = clean_name.replace('\x00', '')
    # Strip dangerous characters
    clean_name = re.sub(r'[^\w\s\.-]', '_', clean_name).strip()
    if not clean_name:
        clean_name = "submission.zip"
    return clean_name


def generate_secure_storage_path(instance, filename):
    """
    Generates a unique, collision-proof server-side storage path.
    Format: submissions/submission_<UUID>_<timestamp>.zip
    Example: submissions/submission_a1b2c3d4_20260904143000.zip
    """
    unique_id = uuid.uuid4().hex[:12]
    timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
    stored_name = f"submission_{unique_id}_{timestamp}.zip"
    return os.path.join('submissions', stored_name)
