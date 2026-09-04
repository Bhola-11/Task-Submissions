import os
import io
import zipfile
import logging
import tempfile
from datetime import datetime, date
from django.utils import timezone
from django.db.models import Sum, Count, Q
from django.http import FileResponse, Http404
from django.utils.text import slugify

from submissions.models import Submission
from submissions.validators import sanitize_filename
from .google_drive_service import calculate_sha256, GoogleDriveService

logger = logging.getLogger(__name__)


class SubmissionService:
    """
    Business logic layer for handling student submissions, storage,
    metrics calculation, and archive packaging.
    """

    @staticmethod
    def create_submission(student_name: str, task_name: str, uploaded_file) -> Submission:
        """
        Processes and saves a validated student submission.
        Preserves original ZIP bytes without extraction or modification.
        Calculates and stores the SHA-256 binary checksum.
        """
        orig_filename = sanitize_filename(uploaded_file.name)
        file_size = uploaded_file.size
        checksum = calculate_sha256(uploaded_file)

        submission = Submission(
            student_name=student_name.strip(),
            task_name=task_name.strip(),
            original_filename=orig_filename,
            file=uploaded_file,
            file_size=file_size,
            sha256_checksum=checksum,
            status=Submission.StatusChoices.PENDING,
            google_drive_status=Submission.GoogleDriveStatusChoices.NOT_UPLOADED,
        )
        submission.save()

        # Update stored_filename field to reflect the actual relative path base
        submission.stored_filename = os.path.basename(submission.file.name)
        submission.save(update_fields=['stored_filename'])

        logger.info(
            f"Submission created: ID={submission.id}, Student='{submission.student_name}', "
            f"Task='{submission.task_name}', File='{submission.stored_filename}' "
            f"({submission.file_size_formatted}, SHA256={submission.sha256_checksum[:8]}...)"
        )
        return submission

    @staticmethod
    def get_dashboard_metrics() -> dict:
        """
        Calculates high-performance aggregated metrics for the Admin Dashboard.
        """
        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # Execute optimized single-query aggregation
        aggregates = Submission.objects.aggregate(
            total=Count('id'),
            pending=Count('id', filter=Q(status=Submission.StatusChoices.PENDING)),
            reviewed=Count('id', filter=Q(status=Submission.StatusChoices.REVIEWED)),
            today=Count('id', filter=Q(submitted_at__gte=today_start)),
            total_bytes=Sum('file_size'),
            gdrive_uploaded=Count('id', filter=Q(google_drive_status=Submission.GoogleDriveStatusChoices.UPLOADED)),
            gdrive_failed=Count('id', filter=Q(google_drive_status=Submission.GoogleDriveStatusChoices.FAILED)),
        )

        total_bytes = aggregates.get('total_bytes') or 0
        
        # Format total storage
        if total_bytes < 1024:
            storage_formatted = f"{total_bytes} B"
        elif total_bytes < 1024 * 1024:
            storage_formatted = f"{total_bytes / 1024:.1f} KB"
        elif total_bytes < 1024 * 1024 * 1024:
            storage_formatted = f"{total_bytes / (1024 * 1024):.2f} MB"
        else:
            storage_formatted = f"{total_bytes / (1024 * 1024 * 1024):.2f} GB"

        return {
            'total_submissions': aggregates.get('total') or 0,
            'pending_submissions': aggregates.get('pending') or 0,
            'reviewed_submissions': aggregates.get('reviewed') or 0,
            'today_submissions': aggregates.get('today') or 0,
            'total_storage_bytes': total_bytes,
            'total_storage_formatted': storage_formatted,
            'gdrive_uploaded': aggregates.get('gdrive_uploaded') or 0,
            'gdrive_failed': aggregates.get('gdrive_failed') or 0,
        }

    @staticmethod
    def filter_submissions(
        queryset,
        search_query: str = '',
        status_filter: str = '',
        date_filter: str = '',
        gdrive_filter: str = ''
    ):
        """
        Applies search and filters on submissions queryset.
        """
        if search_query:
            q = search_query.strip()
            queryset = queryset.filter(
                Q(student_name__icontains=q) |
                Q(task_name__icontains=q) |
                Q(original_filename__icontains=q) |
                Q(sha256_checksum__icontains=q)
            )

        if status_filter in [Submission.StatusChoices.PENDING, Submission.StatusChoices.REVIEWED]:
            queryset = queryset.filter(status=status_filter)

        if gdrive_filter in [
            Submission.GoogleDriveStatusChoices.NOT_UPLOADED,
            Submission.GoogleDriveStatusChoices.UPLOADED,
            Submission.GoogleDriveStatusChoices.FAILED,
        ]:
            queryset = queryset.filter(google_drive_status=gdrive_filter)

        if date_filter:
            try:
                parsed_date = datetime.strptime(date_filter.strip(), '%Y-%m-%d').date()
                queryset = queryset.filter(submitted_at__date=parsed_date)
            except ValueError:
                pass  # Ignore invalid date formats gracefully

        return queryset

    @staticmethod
    def generate_master_zip_file(submissions_queryset):
        """
        Generates a master ZIP file containing all student ZIPs in their original state.
        Ensures collision-safe naming (e.g. Rahul_Portfolio.zip) and handles missing files gracefully.
        Returns (temp_file_path, master_zip_filename, missing_files_count).
        """
        today_str = timezone.now().strftime('%Y-%m-%d')
        master_zip_filename = f"All-Student-Tasks-{today_str}.zip"

        # Create temporary file for master archive to prevent heavy memory usage
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
        temp_file_path = temp_file.name
        temp_file.close()

        used_archive_names = set()
        missing_files = []
        added_count = 0

        with zipfile.ZipFile(temp_file_path, 'w', zipfile.ZIP_DEFLATED) as master_zip:
            for sub in submissions_queryset:
                try:
                    if not sub.file or not os.path.exists(sub.file.path):
                        logger.warning(f"File for submission ID {sub.id} ({sub.student_name}) not found on disk: {sub.file}")
                        missing_files.append(f"{sub.student_name} - {sub.task_name} (ID: {sub.id})")
                        continue

                    # Generate a clean, descriptive, collision-safe name inside master zip
                    clean_student = re_clean_name(sub.student_name)
                    clean_task = re_clean_name(sub.task_name)
                    base_name = f"{clean_student}_{clean_task}"
                    archive_name = f"{base_name}.zip"

                    # Handle duplicate names if multiple submissions have same student & task
                    counter = 1
                    while archive_name in used_archive_names:
                        counter += 1
                        archive_name = f"{base_name}_{counter}.zip"

                    used_archive_names.add(archive_name)

                    # Add the original ZIP file into the master ZIP without extracting
                    master_zip.write(sub.file.path, arcname=archive_name)
                    added_count += 1
                except Exception as e:
                    logger.error(f"Error packaging submission ID {sub.id} into master zip: {str(e)}", exc_info=True)
                    missing_files.append(f"{sub.student_name} - {sub.task_name} (Error: {str(e)})")

        return temp_file_path, master_zip_filename, missing_files, added_count


def re_clean_name(name_str: str) -> str:
    """
    Cleans a string for safe use in filenames inside ZIP archives and cloud storage.
    Preserves alphanumeric characters and replaces spaces with underscores.
    """
    clean = "".join(c if c.isalnum() or c in (' ', '_', '-') else '_' for c in name_str).strip()
    clean = "_".join(clean.split())
    return clean or "Task"
