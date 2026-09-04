from django.contrib import admin
from django.utils.html import format_html
from .models import Submission


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    """
    Standard Django Admin representation of Submission model.
    """
    list_display = (
        'id',
        'student_name',
        'task_name',
        'original_filename',
        'file_size_formatted_display',
        'sha256_short',
        'status_badge',
        'gdrive_badge',
        'submitted_at',
        'updated_at',
    )
    list_filter = ('status', 'google_drive_status', 'submitted_at')
    search_fields = ('student_name', 'task_name', 'original_filename', 'stored_filename', 'sha256_checksum', 'google_drive_file_id')
    readonly_fields = (
        'submitted_at',
        'updated_at',
        'file_size',
        'stored_filename',
        'sha256_checksum',
        'google_drive_file_id',
        'google_drive_url',
        'google_drive_uploaded_at',
        'google_drive_error'
    )
    ordering = ('-submitted_at',)
    list_per_page = 25

    def file_size_formatted_display(self, obj):
        return obj.file_size_formatted
    file_size_formatted_display.short_description = 'File Size'

    def sha256_short(self, obj):
        if obj.sha256_checksum:
            return obj.sha256_checksum[:10] + '...'
        return '-'
    sha256_short.short_description = 'SHA-256'

    def status_badge(self, obj):
        color = '#10b981' if obj.status == Submission.StatusChoices.REVIEWED else '#f59e0b'
        bg = '#ecfdf5' if obj.status == Submission.StatusChoices.REVIEWED else '#fffbeb'
        return format_html(
            '<span style="background-color: {}; color: {}; padding: 4px 10px; border-radius: 9999px; font-weight: 600; font-size: 0.75rem; border: 1px solid {};">{}</span>',
            bg, color, color, obj.status
        )
    status_badge.short_description = 'Status'

    def gdrive_badge(self, obj):
        if obj.google_drive_status == Submission.GoogleDriveStatusChoices.UPLOADED:
            return format_html(
                '<span style="background-color: #ecfdf5; color: #059669; padding: 4px 8px; border-radius: 9999px; font-weight: 600; font-size: 0.75rem; border: 1px solid #10b981;">☁️ Uploaded</span>'
            )
        elif obj.google_drive_status == Submission.GoogleDriveStatusChoices.FAILED:
            return format_html(
                '<span style="background-color: #fef2f2; color: #dc2626; padding: 4px 8px; border-radius: 9999px; font-weight: 600; font-size: 0.75rem; border: 1px solid #ef4444;">❌ Failed</span>'
            )
        else:
            return format_html(
                '<span style="background-color: #f1f5f9; color: #64748b; padding: 4px 8px; border-radius: 9999px; font-weight: 600; font-size: 0.75rem; border: 1px solid #cbd5e1;">Not Uploaded</span>'
            )
    gdrive_badge.short_description = 'Drive Status'
