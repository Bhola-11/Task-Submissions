from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from .models import Submission
from .validators import (
    validate_zip_file_security,
    sanitize_filename,
    validate_zip_magic_bytes,
    validate_zip_file_extension,
    validate_zip_file_size,
    validate_zip_mime_type,
)


class StudentSubmissionForm(forms.ModelForm):
    """
    Form for student task submission with front-to-back validation.
    """
    class Meta:
        model = Submission
        fields = ['student_name', 'task_name', 'file']
        widgets = {
            'student_name': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'e.g. Rahul Sharma',
                'autocomplete': 'name',
                'minlength': '2',
                'maxlength': '150',
                'required': True,
                'aria-label': 'Student Full Name',
            }),
            'task_name': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'e.g. Portfolio Website',
                'minlength': '2',
                'maxlength': '200',
                'required': True,
                'aria-label': 'Task Name',
            }),
            'file': forms.FileInput(attrs={
                'class': 'file-input-hidden',
                'accept': '.zip,application/zip,application/x-zip-compressed',
                'id': 'zipFileInput',
                'required': True,
                'aria-label': 'Upload ZIP File',
            }),
        }

    def clean_student_name(self):
        name = self.cleaned_data.get('student_name', '').strip()
        if len(name) < 2:
            raise ValidationError(
                _("Student name must be at least 2 characters long."),
                code='min_length'
            )
        return name

    def clean_task_name(self):
        task = self.cleaned_data.get('task_name', '').strip()
        if len(task) < 2:
            raise ValidationError(
                _("Task name must be at least 2 characters long."),
                code='min_length'
            )
        return task

    def clean_file(self):
        uploaded_file = self.cleaned_data.get('file')
        if not uploaded_file:
            raise ValidationError(
                _("Please select a ZIP file to upload."),
                code='required'
            )

        # Run comprehensive security validations
        validate_zip_file_security(uploaded_file)
        return uploaded_file


class AdminLoginForm(forms.Form):
    """
    Form for Administrator authentication.
    """
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'Enter admin username',
            'autocomplete': 'username',
            'required': True,
            'autofocus': True,
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'placeholder': 'Enter admin password',
            'autocomplete': 'current-password',
            'required': True,
        })
    )


class SubmissionFilterForm(forms.Form):
    """
    Form for filtering and searching submissions in Admin Dashboard.
    """
    STATUS_CHOICES = [
        ('', 'All Statuses'),
        (Submission.StatusChoices.PENDING, 'Pending'),
        (Submission.StatusChoices.REVIEWED, 'Reviewed'),
    ]

    GDRIVE_CHOICES = [
        ('', 'All Drive Statuses'),
        (Submission.GoogleDriveStatusChoices.NOT_UPLOADED, 'Not Uploaded'),
        (Submission.GoogleDriveStatusChoices.UPLOADED, 'Uploaded'),
        (Submission.GoogleDriveStatusChoices.FAILED, 'Failed'),
    ]

    q = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'filter-input search-input',
            'placeholder': 'Search student, task, file, or hash...',
            'aria-label': 'Search submissions',
        })
    )
    status = forms.ChoiceField(
        choices=STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={
            'class': 'filter-select',
            'aria-label': 'Filter by review status',
        })
    )
    gdrive_status = forms.ChoiceField(
        choices=GDRIVE_CHOICES,
        required=False,
        widget=forms.Select(attrs={
            'class': 'filter-select',
            'aria-label': 'Filter by Google Drive status',
        })
    )
    date = forms.CharField(
        required=False,
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'filter-input date-input',
            'aria-label': 'Filter by submission date',
        })
    )
