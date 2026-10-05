"""Django's built-in admin: a raw database inspector for developers.

The audit log is read-only here so even superusers can't edit history.
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import (
    AdminActionLog,
    Application,
    ApplicationEvent,
    Company,
    JobPosting,
    StudentProfile,
    User,
)


@admin.register(User)
class PortalUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("Portal", {"fields": ("role",)}),)
    list_display = ("username", "email", "role", "is_staff")
    list_filter = ("role",)


@admin.register(AdminActionLog)
class AdminActionLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "admin", "action", "target_type", "target_label")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(StudentProfile)
admin.site.register(Company)
admin.site.register(JobPosting)
admin.site.register(Application)
admin.site.register(ApplicationEvent)
