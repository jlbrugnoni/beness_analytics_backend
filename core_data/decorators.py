from functools import wraps
from django.views.decorators.cache import cache_page

def server_cache_viewset(timeout, key_prefix):
    
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            cached_view = cache_page(timeout, key_prefix=key_prefix)(view_func)
            response = cached_view(request, *args, **kwargs)
            response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response["Pragma"] = "no-cache"
            response["Expires"] = "0"
            response["X-Cached"] = "YES"
            return response
        return wrapped
    return decorator