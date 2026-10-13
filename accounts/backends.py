from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class EmailOrStudentIdBackend(ModelBackend):
    """
    Lets people sign in with either their email or their student ID.

    Extends ModelBackend so permission checks (admin, groups) keep working.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        UserModel = get_user_model()
        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD)
        if not username or password is None:
            return None

        user = UserModel.objects.by_identifier(username)
        if user is None:
            # Burn the same time a real check would, so response timing
            # doesn't reveal which emails are registered.
            UserModel().set_password(password)
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
