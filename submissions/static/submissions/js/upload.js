/**
 * Student Task Submission Portal - Upload & Drag/Drop Handler
 */

document.addEventListener('DOMContentLoaded', function () {
  const form = document.getElementById('submissionForm');
  if (!form) return;

  const dropzone = document.getElementById('uploadDropzone');
  const fileInput = document.getElementById('zipFileInput');
  const previewCard = document.getElementById('filePreviewCard');
  const fileNameDisplay = document.getElementById('fileNameDisplay');
  const fileSizeDisplay = document.getElementById('fileSizeDisplay');
  const removeFileBtn = document.getElementById('removeFileBtn');
  const replaceFileBtn = document.getElementById('replaceFileBtn');
  const submitBtn = document.getElementById('submitBtn');
  const submitBtnText = document.getElementById('submitBtnText');
  const submitBtnSpinner = document.getElementById('submitBtnSpinner');
  const progressContainer = document.getElementById('progressContainer');
  const progressBar = document.getElementById('progressBar');
  const progressPercent = document.getElementById('progressPercent');
  const errorAlert = document.getElementById('errorAlert');
  const errorAlertMessage = document.getElementById('errorAlertMessage');

  // Config variables from HTML data attributes or fallback
  const maxSizeBytes = parseInt(form.dataset.maxSizeBytes, 10) || (50 * 1024 * 1024);
  const maxSizeMb = parseInt(form.dataset.maxSizeMb, 10) || 50;

  let currentFile = null;

  // Format file size helper
  function formatBytes(bytes, decimals = 2) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
  }

  // Show inline error
  function showError(message) {
    if (errorAlert && errorAlertMessage) {
      errorAlertMessage.textContent = message;
      errorAlert.style.display = 'flex';
      errorAlert.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    } else {
      alert(message);
    }
  }

  // Clear inline error
  function clearError() {
    if (errorAlert) {
      errorAlert.style.display = 'none';
      if (errorAlertMessage) errorAlertMessage.textContent = '';
    }
  }

  // Validate selected file
  function validateFile(file) {
    if (!file) return false;

    // Check extension
    const fileName = file.name.toLowerCase();
    if (!fileName.endsWith('.zip')) {
      showError(`Invalid file extension. Only .zip files are accepted (got: ${file.name}).`);
      return false;
    }

    // Check size limit
    if (file.size > maxSizeBytes) {
      const actualSizeMb = (file.size / (1024 * 1024)).toFixed(2);
      showError(`File size (${actualSizeMb} MB) exceeds maximum allowed limit of ${maxSizeMb} MB.`);
      return false;
    }

    if (file.size === 0) {
      showError("The selected file is empty (0 bytes). Please select a valid ZIP archive.");
      return false;
    }

    return true;
  }

  // Update UI for selected file
  function handleFileSelected(file) {
    clearError();
    if (!validateFile(file)) {
      clearFileSelection();
      return;
    }

    currentFile = file;
    fileNameDisplay.textContent = file.name;
    fileSizeDisplay.textContent = formatBytes(file.size);

    dropzone.style.display = 'none';
    previewCard.style.display = 'block';
  }

  // Clear selected file
  function clearFileSelection() {
    currentFile = null;
    fileInput.value = '';
    previewCard.style.display = 'none';
    dropzone.style.display = 'block';
    if (progressContainer) progressContainer.style.display = 'none';
    if (progressBar) progressBar.style.width = '0%';
    if (progressPercent) progressPercent.textContent = '0%';
  }

  // Dropzone click trigger
  dropzone.addEventListener('click', function (e) {
    if (e.target !== fileInput) {
      fileInput.click();
    }
  });

  // Keyboard accessibility for dropzone
  dropzone.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      fileInput.click();
    }
  });

  // File picker change event
  fileInput.addEventListener('change', function () {
    if (fileInput.files && fileInput.files[0]) {
      handleFileSelected(fileInput.files[0]);
    }
  });

  // Replace file button
  replaceFileBtn.addEventListener('click', function (e) {
    e.preventDefault();
    fileInput.click();
  });

  // Remove file button
  removeFileBtn.addEventListener('click', function (e) {
    e.preventDefault();
    clearFileSelection();
  });

  // Drag & Drop events
  ['dragenter', 'dragover'].forEach(eventName => {
    dropzone.addEventListener(eventName, function (e) {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.add('drag-over');
    });
  });

  ['dragleave', 'dragend', 'drop'].forEach(eventName => {
    dropzone.addEventListener(eventName, function (e) {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.remove('drag-over');
    });
  });

  dropzone.addEventListener('drop', function (e) {
    const dt = e.dataTransfer;
    const files = dt.files;
    if (files && files.length > 0) {
      fileInput.files = files; // Sync with file input
      handleFileSelected(files[0]);
    }
  });

  // Form submission with AJAX & real-time progress
  form.addEventListener('submit', function (e) {
    e.preventDefault();
    clearError();

    const studentNameInput = document.getElementById('id_student_name');
    const taskNameInput = document.getElementById('id_task_name');

    const studentName = studentNameInput ? studentNameInput.value.trim() : '';
    const taskName = taskNameInput ? taskNameInput.value.trim() : '';

    if (!studentName || studentName.length < 2) {
      showError('Please enter a valid student name (minimum 2 characters).');
      if (studentNameInput) studentNameInput.focus();
      return;
    }

    if (!taskName || taskName.length < 2) {
      showError('Please enter a valid task name (minimum 2 characters).');
      if (taskNameInput) taskNameInput.focus();
      return;
    }

    if (!currentFile && (!fileInput.files || !fileInput.files[0])) {
      showError('Please select or drop a ZIP file to upload.');
      return;
    }

    const fileToUpload = currentFile || fileInput.files[0];
    if (!validateFile(fileToUpload)) {
      return;
    }

    // Set Loading state
    submitBtn.disabled = true;
    submitBtnSpinner.style.display = 'inline-block';
    submitBtnText.textContent = 'Uploading & Validating...';
    progressContainer.style.display = 'block';
    progressBar.style.width = '0%';
    progressPercent.textContent = '0%';

    // Prepare FormData
    const formData = new FormData(form);
    formData.set('is_ajax', 'true');
    // Ensure file is attached
    if (currentFile) {
      formData.set('file', currentFile);
    }

    const xhr = new XMLHttpRequest();
    xhr.open('POST', form.action || window.location.href, true);
    xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');

    // Progress handler
    xhr.upload.onprogress = function (event) {
      if (event.lengthComputable) {
        const percent = Math.round((event.loaded / event.total) * 100);
        progressBar.style.width = percent + '%';
        progressPercent.textContent = percent + '%';
        if (percent >= 100) {
          submitBtnText.textContent = 'Verifying ZIP Security...';
        }
      }
    };

    // Completion handler
    xhr.onload = function () {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const response = JSON.parse(xhr.responseText);
          if (response.success && response.redirect_url) {
            window.location.href = response.redirect_url;
          } else {
            resetSubmitState();
            showError(response.error || 'Submission could not be completed.');
          }
        } catch (err) {
          // If non-json redirect or success
          window.location.reload();
        }
      } else {
        resetSubmitState();
        try {
          const response = JSON.parse(xhr.responseText);
          if (response.errors) {
            const messages = [];
            for (const key in response.errors) {
              messages.push(response.errors[key].join(' '));
            }
            showError(messages.join(' '));
          } else if (response.error) {
            showError(response.error);
          } else {
            showError(`Server error (${xhr.status}): Please check your input and try again.`);
          }
        } catch (e) {
          showError(`Submission error (${xhr.status}). Please verify that your ZIP is valid and below ${maxSizeMb} MB.`);
        }
      }
    };

    xhr.onerror = function () {
      resetSubmitState();
      showError('Network connection failure. Please check your network and try again.');
    };

    xhr.send(formData);
  });

  function resetSubmitState() {
    submitBtn.disabled = false;
    submitBtnSpinner.style.display = 'none';
    submitBtnText.textContent = 'Submit Task';
    if (progressContainer) progressContainer.style.display = 'none';
  }
});
