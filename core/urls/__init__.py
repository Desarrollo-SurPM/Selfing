from .auth import urlpatterns as auth_patterns
from .admin import urlpatterns as admin_patterns
from .operator import urlpatterns as operator_patterns
from .gps import urlpatterns as gps_patterns
from .vehicles import urlpatterns as vehicle_patterns
from .api import urlpatterns as api_patterns

urlpatterns = (
    auth_patterns
    + admin_patterns
    + operator_patterns
    + gps_patterns
    + vehicle_patterns
    + api_patterns
)
