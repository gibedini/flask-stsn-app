from flask import redirect, url_for, flash
from flask_login import current_user
from functools import wraps

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash("Admin access required", "danger")
            return redirect(url_for("members"))
        return f(*args, **kwargs)
    return decorated_function
