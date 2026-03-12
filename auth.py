from flask import redirect, url_for, flash
from flask_login import current_user
from functools import wraps

def is_superadmin():
    """Retorna True se o usuário atual é SuperAdmin."""
    return current_user.is_authenticated and current_user.perfil and current_user.perfil.nome == 'SuperAdmin'

def is_admin_or_superadmin():
    """Retorna True se o usuário atual é Admin ou SuperAdmin."""
    return current_user.is_authenticated and current_user.perfil and current_user.perfil.nome in ('Admin', 'SuperAdmin')

def admin_required(f):
    """Decorator: permite acesso a Admin e SuperAdmin."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_admin_or_superadmin():
            flash("Acesso restrito a administradores.", "danger")
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def superadmin_required(f):
    """Decorator: permite acesso apenas ao SuperAdmin."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_superadmin():
            flash("Acesso restrito ao Super Administrador.", "danger")
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function
