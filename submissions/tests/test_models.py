import os
import io
import zipfile
from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from submissions.models import Submission


def create_in_memory_zip(filename="test.zip", content="sample project code"):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr("main.py", content)
    buffer.seek(0)
    return SimpleUploadedFile(
        filename,
        buffer.getvalue(),
        content_type='application/zip'
    )


class SubmissionModelTest(TestCase):
    def test_create_submission(self):
        zip_file = create_in_memory_zip()
        submission = Submission.objects.create(
            student_name="Rahul",
            task_name="Portfolio",
            original_filename="portfolio.zip",
            stored_filename="submission_test_123.zip",
            file=zip_file,
            file_size=len(zip_file),
            status=Submission.StatusChoices.PENDING,
        )

        self.assertEqual(submission.student_name, "Rahul")
        self.assertEqual(submission.task_name, "Portfolio")
        self.assertEqual(submission.status, Submission.StatusChoices.PENDING)
        self.assertIn("Rahul - Portfolio", str(submission))
        self.assertTrue(submission.file_size_formatted.endswith("B") or submission.file_size_formatted.endswith("KB"))

    def test_file_size_formatting(self):
        sub1 = Submission(file_size=500)
        self.assertEqual(sub1.file_size_formatted, "500 B")

        sub2 = Submission(file_size=1536) # 1.5 KB
        self.assertEqual(sub2.file_size_formatted, "1.5 KB")

        sub3 = Submission(file_size=2 * 1024 * 1024) # 2 MB
        self.assertEqual(sub3.file_size_formatted, "2.00 MB")
