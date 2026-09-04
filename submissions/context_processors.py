from django.conf import settings


def portal_settings(request):
    """
    Context processor to pass portal-wide configuration to all templates.
    """
    return {
        'MAX_FILE_SIZE_MB': getattr(settings, 'MAX_FILE_SIZE_MB', 50),
        'MAX_FILE_SIZE_BYTES': getattr(settings, 'MAX_FILE_SIZE_BYTES', 50 * 1024 * 1024),
    }
