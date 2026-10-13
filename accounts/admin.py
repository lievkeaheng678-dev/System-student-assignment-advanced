from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import BaseUserCreationForm, UserChangeForm as DjangoUserChangeForm

from .models import LoginEvent, User


class UserCreationForm(BaseUserCreationForm):
    class Meta:
        model = User
        fields = ("email", "first_name", "last_name")


class UserChangeForm(DjangoUserChangeForm):
    class Meta:
        model = User
        fields = "__all__"


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    form = UserChangeForm
    add_form = UserCreationForm

    ordering = ("-date_joined",)
    list_display = (
        "student_id", "display_name", "email", "program", "year_of_study",
        "email_verified", "is_active", "date_joined",
    )
    list_filter = ("email_verified", "is_active", "is_staff", "program", "year_of_study")
    search_fields = ("email", "first_name", "last_name", "student_id")
    readonly_fields = ("student_id", "date_joined", "last_login")
    filter_horizontal = ("groups", "user_permissions")

    fieldsets = (
        (None, {"fields": ("student_id", "email", "password")}),
        ("Personal", {"fields": ("first_name", "last_name", "phone", "date_of_birth", "bio")}),
        ("Study", {"fields": ("program", "year_of_study")}),
        ("Status", {"fields": ("email_verified", "is_active")}),
        ("Permissions", {"classes": ("collapse",), "fields": ("is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Dates", {"fields": ("date_joined", "last_login")}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "first_name", "last_name", "password1", "password2"),
        }),
    )

    @admin.display(description="Name", ordering="last_name")
    def display_name(self, obj):
        return obj.get_full_name()


@admin.register(LoginEvent)
class LoginEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "identifier", "success", "ip_address", "device")
    list_filter = ("success",)
    search_fields = ("identifier", "ip_address")
    date_hierarchy = "created_at"
    readonly_fields = ("user", "identifier", "ip_address", "user_agent", "success", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
