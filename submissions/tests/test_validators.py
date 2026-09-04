import io
import zipfile
from django.test import TestCase, override_settings
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from submissions.validators import (
    validate_zip_file_extension,
    validate_zip_magic_bytes,
    validate_zip_mime_type,
    validate_zip_file_size,
    validate_zip_file_security,
    sanitize_filename,
    generate_secure_storage_path,
)


class ValidatorSecurityTests(TestCase):
    def test_valid_zip_magic_bytes(self):
        # Valid PK\x03\x04 zip
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as z:
            z.writestr("test.txt", "hello")
        buf.seek(0)

        file_obj = SimpleUploadedFile("valid.zip", buf.getvalue(), content_type="application/zip")
        # Should not raise exception
        validate_zip_magic_bytes(file_obj)

    def test_invalid_extension_rejected(self):
        file_txt = SimpleUploadedFile("script.txt", b"plain text", content_type="text/plain")
        file_png = SimpleUploadedFile("image.png", b"\x89PNG\r\n\x1a\n", content_type="image/png")
        file_exe = SimpleUploadedFile("malware.exe", b"MZ\x90\x00", content_type="application/x-dosexec")

        with self.assertRaises(ValidationError):
            validate_zip_file_extension(file_txt)

        with self.assertRaises(ValidationError):
            validate_zip_file_extension(file_png)

        with self.assertRaises(ValidationError):
            validate_zip_file_extension(file_exe)

    def test_fake_zip_rejected(self):
        # Named .zip but contains text or exe bytes
        fake_zip = SimpleUploadedFile("fake.zip", b"This is not a real zip archive header", content_type="application/zip")
        with self.assertRaises(ValidationError):
            validate_zip_magic_bytes(fake_zip)

    @override_settings(MAX_FILE_SIZE_MB=1)
    def test_oversized_file_rejected(self):
        # 1.5 MB in size with 1 MB limit
        large_content = b"PK\x03\x04" + b"0" * (int(1.5 * 1024 * 1024))
        large_file = SimpleUploadedFile("huge.zip", large_content, content_type="application/zip")
        with self.assertRaises(ValidationError):
            validate_zip_file_size(large_file)

    def test_filename_sanitization_and_traversal_protection(self):
        traversal_name = "../../../etc/passwd.zip"
        clean = sanitize_filename(traversal_name)
        self.assertEqual(clean, "passwd.zip")

        dirty_name = "Rahul's Project <v1.0>?.zip"
        clean_dirty = sanitize_filename(dirty_name)
        self.assertNotIn("<", clean_dirty)
        self.assertNotIn(">", clean_dirty)
        self.assertNotIn("?", clean_dirty)
        self.assertTrue(clean_dirty.endswith(".zip"))

    def test_generate_secure_storage_path(self):
        path = generate_secure_storage_path(None, "my_assignment.zip")
        self.assertTrue(path.startswith("submissions\\") or path.startswith("submissions/"))
        self.assertIn("submission_", path)
        self.assertTrue(path.endswith(".zip"))
