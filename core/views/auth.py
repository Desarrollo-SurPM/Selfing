from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required


def is_supervisor(user):
    return user.is_superuser


@login_required
def home(request):
    if is_supervisor(request.user):
        return redirect('admin_dashboard')
    else:
        return redirect('operator_dashboard')
