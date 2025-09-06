from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import Profile, UserRole


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


# Replace default User admin so role appears inline
admin.site.unregister(User)

@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    inlines = [ProfileInline]
    list_display = DjangoUserAdmin.list_display + ("get_role",)

    @admin.display(ordering="profile__role", description="Role")
    def get_role(self, obj: User):
        try:
            return obj.profile.get_role_display()
        except Profile.DoesNotExist:
            return "—"