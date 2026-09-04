/**
 * Student Task Submission Portal - Admin Dashboard Interactivity
 */

document.addEventListener('DOMContentLoaded', function () {
  // Setup Copy Submission ID buttons
  const copyButtons = document.querySelectorAll('.btn-copy-id');
  copyButtons.forEach(btn => {
    btn.addEventListener('click', function (e) {
      e.preventDefault();
      const idToCopy = this.getAttribute('data-id') || this.dataset.id;
      if (!idToCopy) return;

      navigator.clipboard.writeText(idToCopy).then(() => {
        const originalText = this.innerHTML;
        this.innerHTML = '✓ Copied!';
        this.classList.add('copied');
        setTimeout(() => {
          this.innerHTML = originalText;
          this.classList.remove('copied');
        }, 2000);
      }).catch(err => {
        console.error('Failed to copy ID: ', err);
      });
    });
  });

  // Auto-dismiss alerts after 5 seconds if desired
  const alerts = document.querySelectorAll('.alert-dismissible');
  alerts.forEach(alert => {
    setTimeout(() => {
      alert.style.transition = 'opacity 0.5s ease';
      alert.style.opacity = '0';
      setTimeout(() => alert.remove(), 500);
    }, 5000);
  });
});
