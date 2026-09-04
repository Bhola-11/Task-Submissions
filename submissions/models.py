import os
from django.db import models
from django.utils.translation import gettext_lazy as _
from .validators import generate_secure_storage_path, validate_zip_file_security


class Submission(models.Model):
    """
    Submission model representing a student's task submission.
    Stores metadata in PostgreSQL and points to the securely stored ZIP file on disk.
    Tracks Google Drive cloud synchronization status.
    """
    class StatusChoices(models.TextChoices):
        PENDING = 'Pending', _('Pending')
        REVIEWED = 'Reviewed', _('Reviewed')

    class GoogleDriveStatusChoices(models.TextChoices):
        NOT_UPLOADED = 'Not Uploaded', _('Not Uploaded')
        UPLOADED = 'Uploaded', _('Uploaded')
        FAILED = 'Failed', _('Failed')

    student_name = models.CharField(
        max_length=150,
        verbose_name=_('Student Name'),
        help_text=_('Full name of the submitting student.')
    )
    task_name = models.CharField(
        max_length=200,
        verbose_name=_('Task Name'),
        help_text=_('Title or name of the assigned task.')
    )
    original_filename = models.CharField(
        max_length=255,
        verbose_name=_('Original Filename'),
        help_text=_('Original name of the uploaded ZIP file.')
    )
    stored_filename = models.CharField(
        max_length=255,
        verbose_name=_('Stored Filename'),
        help_text=_('Unique server-side filename.')
    )
    file = models.FileField(
        upload_to=generate_secure_storage_path,
        validators=[validate_zip_file_security],
        verbose_name=_('ZIP File'),
        help_text=_('Original ZIP file preserved on server storage.')
    )
    file_size = models.PositiveBigIntegerField(
        verbose_name=_('File Size (Bytes)'),
        help_text=_('Size of the uploaded file in bytes.')
    )
    sha256_checksum = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        db_index=True,
        verbose_name=_('SHA-256 Checksum'),
        help_text=_('Hexadecimal SHA-256 hash of original ZIP file for binary integrity verification.')
    )
    status = models.CharField(
        max_length=20,
        choices=StatusChoices.choices,
        default=StatusChoices.PENDING,
        db_index=True,
        verbose_name=_('Status')
    )
    
    # Google Drive Integration Fields
    google_drive_status = models.CharField(
        max_length=20,
        choices=GoogleDriveStatusChoices.choices,
        default=GoogleDriveStatusChoices.NOT_UPLOADED,
        db_index=True,
        verbose_name=_('Google Drive Status')
    )
    google_drive_file_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name=_('Google Drive File ID')
    )
    google_drive_url = models.URLField(
        max_length=500,
        blank=True,
        null=True,
        verbose_name=_('Google Drive URL')
    )
    google_drive_uploaded_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name=_('Google Drive Uploaded At')
    )
    google_drive_error = models.TextField(
        blank=True,
        null=True,
        verbose_name=_('Google Drive Error Log')
    )

    submitted_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name=_('Submitted At')
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_('Updated At')
    )

    class Meta:
        verbose_name = _('Student Submission')
        verbose_name_plural = _('Student Submissions')
        ordering = ['-submitted_at']
        indexes = [
            models.Index(fields=['status'], name='idx_submission_status'),
            models.Index(fields=['submitted_at'], name='idx_submission_submitted_at'),
            models.Index(fields=['student_name'], name='idx_submission_student_name'),
            models.Index(fields=['task_name'], name='idx_submission_task_name'),
            models.Index(fields=['google_drive_status'], name='idx_sub_gdrive_status'),
            models.Index(fields=['sha256_checksum'], name='idx_sub_sha256'),
        ]

    def __str__(self):
        return f"{self.student_name} - {self.task_name} ({self.status}) [Drive: {self.google_drive_status}]"

    @property
    def file_size_formatted(self):
        """
        Returns the file size in a human-readable format (B, KB, MB, GB).
        """
        size = self.file_size or 0
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        elif size < 1024 * 1024 * 1024:
            return f"{size / (1024 * 1024):.2f} MB"
        else:
            return f"{size / (1024 * 1024 * 1024):.2f} GB"

    @property
    def is_file_available(self):
        """
        Verifies if the physical file actually exists in storage.
        """
        try:
            return bool(self.file and os.path.exists(self.file.path))
        except Exception:
            return False


class GoogleOAuthCredential(models.Model):
    """
    Stores encrypted Google OAuth 2.0 credentials in PostgreSQL (Neon).
    Persists refresh tokens across ephemeral Render restarts/redeploys.
    """
    encrypted_token_data = models.TextField(
        verbose_name=_('Encrypted Token Data'),
        help_text=_('AES-encrypted JSON payload containing Google OAuth refresh token and client metadata.')
    )
    user_email = models.EmailField(
        blank=True,
        null=True,
        verbose_name=_('Authorized User Email')
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('Connected At')
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_('Last Updated At')
    )

    class Meta:
        verbose_name = _('Google OAuth Credential')
        verbose_name_plural = _('Google OAuth Credentials')
        ordering = ['-updated_at']

    def __str__(self):
        return f"Google OAuth Credentials ({self.user_email or 'Authorized User'}) - Updated: {self.updated_at.strftime('%Y-%m-%d %H:%M')}"
