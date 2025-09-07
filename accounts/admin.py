from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import Profile

class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    fk_name = "user"
    extra = 0
    fields = ("role",)

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role")
    list_filter = ("role",)
    search_fields = ("user__username", "user__email")

# Safe-unregister default User admin
try:
    admin.site.unregister(User)
except admin.sites.NotRegistered:
    pass

@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    inlines = [ProfileInline]
    list_display = DjangoUserAdmin.list_display + ("get_role",)
    list_select_related = ("profile",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("profile")

    @admin.display(ordering="profile__role", description="Role")
    def get_role(self, obj: User):
        try:
            return obj.profile.get_role_display()
        except Profile.DoesNotExist:
            return "—"
