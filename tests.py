import re

from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from config.settings import parse_database_url

from .emails import make_verification_token
from .models import LoginEvent, User
from .security import describe_user_agent

PASSWORD = "Sturdy-Pass-4821"
NEW_PASSWORD = "Another-Pass-9937"


def make_user(email="sam@example.com", **extra):
    extra.setdefault("first_name", "Sam")
    extra.setdefault("last_name", "Lee")
    return User.objects.create_user(email=email, password=PASSWORD, **extra)


class ModelTests(TestCase):
    def test_student_id_is_generated_and_unique(self):
        a, b = make_user("a@example.com"), make_user("b@example.com")
        self.assertRegex(a.student_id, r"^STU-\d{4}-\d{5}$")
        self.assertNotEqual(a.student_id, b.student_id)

    def test_email_is_lowercased(self):
        self.assertEqual(make_user("Mixed@Example.COM").email, "mixed@example.com")

    def test_by_identifier_finds_email_or_student_id_ignoring_case(self):
        user = make_user()
        self.assertEqual(User.objects.by_identifier("SAM@example.com"), user)
        self.assertEqual(User.objects.by_identifier(user.student_id.lower()), user)
        self.assertIsNone(User.objects.by_identifier("nobody@example.com"))
        self.assertIsNone(User.objects.by_identifier(""))

    def test_superuser_flags(self):
        admin = User.objects.create_superuser("root@example.com", PASSWORD, first_name="R", last_name="T")
        self.assertTrue(admin.is_staff and admin.is_superuser and admin.email_verified)

    def test_profile_completeness_grows(self):
        user = make_user()
        before = user.profile_completeness
        user.phone, user.program = "0123456", "Law"
        self.assertGreater(user.profile_completeness, before)


class HelperTests(TestCase):
    def test_user_agent_summary(self):
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
        self.assertEqual(describe_user_agent(ua), "Chrome on Windows")
        self.assertEqual(describe_user_agent(""), "Unknown device")

    def test_database_url_parsing(self):
        cfg = parse_database_url("postgres://me:p%40ss@db.internal:5432/mydb")
        self.assertEqual(cfg["NAME"], "mydb")
        self.assertEqual(cfg["USER"], "me")
        self.assertEqual(cfg["PASSWORD"], "p@ss")
        self.assertEqual(cfg["HOST"], "db.internal")
        self.assertNotIn("OPTIONS", cfg)

    def test_external_render_database_requires_ssl(self):
        cfg = parse_database_url("postgres://u:p@dpg-abc.oregon-postgres.render.com/db")
        self.assertEqual(cfg["OPTIONS"]["sslmode"], "require")

    def test_health_check_needs_no_host_or_database(self):
        response = self.client.get("/healthz/", HTTP_HOST="somewhere-unlisted.example")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"ok")


class RegistrationTests(TestCase):
    def payload(self, **overrides):
        data = {
            "first_name": "Ada",
            "last_name": "Byron",
            "email": "Ada@Example.com",
            "program": "Computer Science",
            "year_of_study": "2",
            "password1": PASSWORD,
            "password2": PASSWORD,
            "accept_terms": "on",
            "website": "",
        }
        data.update(overrides)
        return data

    def test_register_creates_account_and_signs_in(self):
        response = self.client.post(reverse("register"), self.payload())
        self.assertRedirects(response, reverse("dashboard"))
        user = User.objects.get(email="ada@example.com")
        self.assertEqual(user.year_of_study, 2)
        self.assertEqual(user.program, "Computer Science")
        self.assertFalse(user.email_verified)
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(LoginEvent.objects.filter(user=user, success=True).exists())

    def test_duplicate_email_in_any_case_is_rejected(self):
        make_user("ada@example.com")
        response = self.client.post(reverse("register"), self.payload(email="ADA@example.com"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already exists")
        self.assertEqual(User.objects.count(), 1)

    def test_weak_password_is_rejected(self):
        response = self.client.post(
            reverse("register"), self.payload(password1="password", password2="password")
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.exists())

    def test_mismatched_passwords_are_rejected(self):
        response = self.client.post(reverse("register"), self.payload(password2=PASSWORD + "x"))
        self.assertContains(response, "don&#x27;t match")
        self.assertFalse(User.objects.exists())

    def test_terms_must_be_accepted(self):
        data = self.payload()
        del data["accept_terms"]
        response = self.client.post(reverse("register"), data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.exists())

    def test_honeypot_blocks_bots(self):
        self.client.post(reverse("register"), self.payload(website="http://spam.example"))
        self.assertFalse(User.objects.exists())

    @override_settings(REQUIRE_EMAIL_VERIFICATION=True)
    def test_verification_required_means_no_auto_sign_in(self):
        response = self.client.post(reverse("register"), self.payload())
        self.assertContains(response, "Check your email")
        self.assertNotIn("_auth_user_id", self.client.session)


class LoginTests(TestCase):
    def setUp(self):
        self.user = make_user()

    def sign_in(self, identifier, password=PASSWORD, client=None):
        return (client or self.client).post(
            reverse("login"), {"username": identifier, "password": password}
        )

    def test_sign_in_with_email_any_case(self):
        self.assertRedirects(self.sign_in("SAM@Example.com"), reverse("dashboard"))

    def test_sign_in_with_student_id(self):
        self.assertRedirects(self.sign_in(self.user.student_id.lower()), reverse("dashboard"))

    def test_wrong_password_is_logged_and_rejected(self):
        response = self.sign_in("sam@example.com", "wrong-password")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "isn&#x27;t right")
        self.assertEqual(LoginEvent.objects.filter(success=False, user=self.user).count(), 1)

    def test_lockout_after_repeated_failures_even_with_right_password(self):
        for _ in range(5):
            self.sign_in("sam@example.com", "wrong-password")
        response = self.sign_in("sam@example.com", PASSWORD)
        self.assertContains(response, "Too many failed attempts")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_lockout_message_is_the_same_for_unknown_accounts(self):
        for _ in range(5):
            self.sign_in("ghost@example.com", "wrong-password")
        response = self.sign_in("ghost@example.com", PASSWORD)
        self.assertContains(response, "Too many failed attempts")

    def test_success_resets_the_failure_count(self):
        for _ in range(4):
            self.sign_in("sam@example.com", "wrong-password")
        self.assertRedirects(self.sign_in("sam@example.com"), reverse("dashboard"))
        self.client.logout()
        for _ in range(4):
            self.sign_in("sam@example.com", "wrong-password")
        self.assertRedirects(self.sign_in("sam@example.com"), reverse("dashboard"))

    @override_settings(REQUIRE_EMAIL_VERIFICATION=True)
    def test_unverified_email_cannot_sign_in_when_required(self):
        response = self.sign_in("sam@example.com")
        self.assertContains(response, "confirm your email")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_inactive_account_cannot_sign_in(self):
        self.user.is_active = False
        self.user.save()
        self.assertEqual(self.sign_in("sam@example.com").status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logout_requires_post(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("logout")).status_code, 405)
        self.assertRedirects(self.client.post(reverse("logout")), reverse("home"))

    def test_signed_in_pages_need_a_login(self):
        for name in ("dashboard", "profile", "security"):
            url = reverse(name)
            self.assertRedirects(self.client.get(url), f"{reverse('login')}?next={url}")


class VerificationTests(TestCase):
    def setUp(self):
        self.user = make_user()

    def test_valid_link_confirms_email(self):
        url = reverse("verify_email", args=[make_verification_token(self.user)])
        self.client.get(url)
        self.user.refresh_from_db()
        self.assertTrue(self.user.email_verified)

    def test_garbage_link_does_nothing(self):
        self.client.get(reverse("verify_email", args=["not-a-real-token"]))
        self.user.refresh_from_db()
        self.assertFalse(self.user.email_verified)

    def test_link_dies_when_the_email_changes(self):
        token = make_verification_token(self.user)
        self.user.email = "new@example.com"
        self.user.save()
        self.client.get(reverse("verify_email", args=[token]))
        self.user.refresh_from_db()
        self.assertFalse(self.user.email_verified)

    def test_resend_is_rate_limited(self):
        self.client.force_login(self.user)
        self.client.post(reverse("resend_verification"))
        self.client.post(reverse("resend_verification"))
        self.assertEqual(len(mail.outbox), 1)


class ProfileTests(TestCase):
    def setUp(self):
        self.user = make_user(email_verified=True)
        self.other = make_user("other@example.com")
        self.client.force_login(self.user)

    def payload(self, **overrides):
        data = {
            "first_name": "Sam",
            "last_name": "Lee",
            "email": "sam@example.com",
            "phone": "+855 12 345 678",
            "date_of_birth": "2004-05-17",
            "program": "Law",
            "year_of_study": "3",
            "bio": "Hello there.",
        }
        data.update(overrides)
        return data

    def test_profile_saves(self):
        self.assertRedirects(self.client.post(reverse("profile"), self.payload()), reverse("profile"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.program, "Law")
        self.assertEqual(self.user.year_of_study, 3)
        self.assertTrue(self.user.email_verified)

    def test_changing_email_requires_confirming_again(self):
        self.client.post(reverse("profile"), self.payload(email="fresh@example.com"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "fresh@example.com")
        self.assertFalse(self.user.email_verified)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["fresh@example.com"])

    def test_cannot_take_another_students_email(self):
        response = self.client.post(reverse("profile"), self.payload(email="OTHER@example.com"))
        self.assertContains(response, "already uses this email")
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "sam@example.com")

    def test_future_birth_date_is_rejected(self):
        response = self.client.post(reverse("profile"), self.payload(date_of_birth="2999-01-01"))
        self.assertContains(response, "real date of birth")

    def test_student_id_cannot_be_edited(self):
        original = self.user.student_id
        self.client.post(reverse("profile"), self.payload(student_id="STU-0000-00000"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.student_id, original)


class SecurityPageTests(TestCase):
    def test_sign_out_other_devices(self):
        user = make_user()
        phone, laptop = Client(), Client()
        phone.force_login(user)
        laptop.force_login(user)
        self.assertEqual(laptop.get(reverse("dashboard")).status_code, 200)

        response = laptop.post(reverse("signout_others"))
        self.assertRedirects(response, reverse("security"))
        self.assertEqual(laptop.get(reverse("dashboard")).status_code, 200)
        self.assertEqual(phone.get(reverse("dashboard")).status_code, 302)

    def test_change_password(self):
        user = make_user()
        self.client.force_login(user)
        response = self.client.post(
            reverse("password_change"),
            {"old_password": PASSWORD, "new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD},
        )
        self.assertRedirects(response, reverse("security"))
        user.refresh_from_db()
        self.assertTrue(user.check_password(NEW_PASSWORD))
        # still signed in afterwards
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)

    def test_delete_account_needs_the_right_password(self):
        user = make_user()
        self.client.force_login(user)
        self.client.post(reverse("delete_account"), {"password": "nope", "confirm": "on"})
        self.assertTrue(User.objects.filter(pk=user.pk).exists())
        self.client.post(reverse("delete_account"), {"password": PASSWORD, "confirm": "on"})
        self.assertFalse(User.objects.filter(pk=user.pk).exists())

    def test_staff_cannot_self_delete(self):
        admin = User.objects.create_superuser("root@example.com", PASSWORD, first_name="R", last_name="T")
        self.client.force_login(admin)
        self.client.post(reverse("delete_account"), {"password": PASSWORD, "confirm": "on"})
        self.assertTrue(User.objects.filter(pk=admin.pk).exists())


@override_settings(DEMO_MODE=True)
class DemoGuardTests(TestCase):
    def setUp(self):
        self.demo = make_user("demo@student.test")
        self.client.force_login(self.demo)

    def test_demo_password_cannot_be_changed(self):
        self.client.post(
            reverse("password_change"),
            {"old_password": PASSWORD, "new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD},
        )
        self.demo.refresh_from_db()
        self.assertTrue(self.demo.check_password(PASSWORD))

    def test_demo_account_cannot_be_deleted(self):
        self.client.post(reverse("delete_account"), {"password": PASSWORD, "confirm": "on"})
        self.assertTrue(User.objects.filter(pk=self.demo.pk).exists())

    def test_banner_and_credentials_show_on_login_page(self):
        self.client.logout()
        self.assertContains(self.client.get(reverse("login")), "demo@student.test")


class PasswordResetTests(TestCase):
    def test_full_reset_flow(self):
        user = make_user()
        self.client.post(reverse("password_reset"), {"email": "SAM@example.com"})
        self.assertEqual(len(mail.outbox), 1)
        body = mail.outbox[0].body
        self.assertIn(user.student_id, body)

        link = re.search(r"http://testserver(/password-reset/\S+)", body).group(1)
        landing = self.client.get(link, follow=True)
        final_url = landing.redirect_chain[-1][0]
        response = self.client.post(
            final_url, {"new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD}
        )
        self.assertRedirects(response, reverse("password_reset_complete"))

        self.client.logout()
        signed_in = self.client.post(
            reverse("login"), {"username": "sam@example.com", "password": NEW_PASSWORD}
        )
        self.assertRedirects(signed_in, reverse("dashboard"))

    def test_unknown_email_gets_the_same_answer_and_no_mail(self):
        response = self.client.post(reverse("password_reset"), {"email": "ghost@example.com"})
        self.assertRedirects(response, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 0)
