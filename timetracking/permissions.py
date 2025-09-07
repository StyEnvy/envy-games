from django.contrib.auth.models import AnonymousUser

try:
    from accounts.models import UserRole  # your enum with PM/DEV
except Exception:  # fallback defaults
    class UserRole:
        PROJECT_MANAGER = "pm"
        DEVELOPER = "dev"


def is_pm(user) -> bool:
    if not user or isinstance(user, AnonymousUser) or not user.is_authenticated:
        return False
    profile = getattr(user, "profile", None)
    role = getattr(profile, "role", None)
    return role == getattr(UserRole, "PROJECT_MANAGER", "pm")


def is_dev(user) -> bool:
    if not user or isinstance(user, AnonymousUser) or not user.is_authenticated:
        return False
    profile = getattr(user, "profile", None)
    role = getattr(profile, "role", None)
    return role == getattr(UserRole, "DEVELOPER", "dev")


def can_edit_entry(user, entry_user_id: int) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if is_pm(user):
        return True
    if is_dev(user):
        return user.id == entry_user_id
    # default conservative
    return user.id == entry_user_id