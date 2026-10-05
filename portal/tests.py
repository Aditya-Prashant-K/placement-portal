"""Tests for the rules the project spec cares about.

Run with:  python manage.py test
"""
from datetime import timedelta
from io import StringIO
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from . import services
from .models import (
    AdminActionLog,
    Application,
    ApprovalStatus,
    Company,
    JobPosting,
    StudentProfile,
    User,
)

PW = "Demo@1234"


class PortalTestCase(TestCase):
    def setUp(self):
        self.admin = self.make_user("admin", User.Role.ADMIN)
        self.recruiter = self.make_user("rec", User.Role.RECRUITER)
        self.other_recruiter = self.make_user("rec2", User.Role.RECRUITER)
        self.student = self.make_user("stu", User.Role.STUDENT)
        self.low_cgpa = self.make_user("low", User.Role.STUDENT)
        StudentProfile.objects.create(user=self.student, branch="CSE", cgpa=Decimal("8.5"),
                                      graduation_year=2027, resume_link="https://example.com/a")
        StudentProfile.objects.create(user=self.low_cgpa, branch="CSE", cgpa=Decimal("6.0"),
                                      graduation_year=2027, resume_link="https://example.com/b")

        self.company = Company.objects.create(owner=self.recruiter, name="Acme",
                                              status=ApprovalStatus.APPROVED)
        self.other_company = Company.objects.create(owner=self.other_recruiter, name="Other",
                                                    status=ApprovalStatus.APPROVED)
        self.job = JobPosting.objects.create(company=self.company, title="SDE", description="x",
                                             min_cgpa=Decimal("7.5"), allowed_branches="CSE,IT",
                                             status=ApprovalStatus.APPROVED)

    def make_user(self, username, role):
        return User.objects.create_user(username=username, password=PW, role=role)

    def login(self, user):
        self.client.force_login(user)


class EligibilityTests(PortalTestCase):
    def test_eligible_student_can_apply(self):
        self.login(self.student)
        resp = self.client.post(reverse("portal:job_apply", args=[self.job.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Application.objects.filter(student=self.student, job=self.job).exists())

    def test_low_cgpa_is_blocked_on_server_with_notice(self):
        self.login(self.low_cgpa)
        # POST directly, bypassing the UI, to prove the server enforces the rule.
        resp = self.client.post(reverse("portal:job_apply", args=[self.job.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "below the minimum required")
        self.assertFalse(Application.objects.filter(student=self.low_cgpa).exists())

    def test_wrong_branch_is_blocked(self):
        self.student.profile.branch = "MECH"
        self.student.profile.save()
        reasons = services.check_eligibility(self.student, self.job)
        self.assertTrue(any("branch" in r for r in reasons))

    def test_empty_branch_list_allows_everyone(self):
        self.job.allowed_branches = ""
        self.student.profile.branch = "CIVIL"
        self.assertEqual(services.check_eligibility(self.student, self.job), [])

    def test_missing_profile_is_blocked(self):
        no_profile = self.make_user("np", User.Role.STUDENT)
        reasons = services.check_eligibility(no_profile, self.job)
        self.assertIn("Complete your student profile", reasons[0])

    def test_past_deadline_is_blocked(self):
        self.job.deadline = timezone.localdate() - timedelta(days=1)
        self.assertTrue(any("deadline" in r for r in services.check_eligibility(self.student, self.job)))

    def test_cannot_apply_twice(self):
        services.apply_to_job(self.student, self.job)
        app, reasons = services.apply_to_job(self.student, self.job)
        self.assertIsNone(app)
        self.assertIn("already applied", reasons[0])


class VisibilityTests(PortalTestCase):
    def test_pending_job_hidden_from_students(self):
        pending = JobPosting.objects.create(company=self.company, title="Hidden", description="x")
        self.login(self.student)
        self.assertNotContains(self.client.get(reverse("portal:job_list")), "Hidden")
        self.assertEqual(self.client.get(reverse("portal:job_detail", args=[pending.pk])).status_code, 404)

    def test_job_of_unapproved_company_hidden(self):
        self.company.status = ApprovalStatus.PENDING
        self.company.save()
        self.assertFalse(JobPosting.objects.visible().filter(pk=self.job.pk).exists())

    def test_cannot_apply_to_unapproved_job_by_url(self):
        pending = JobPosting.objects.create(company=self.company, title="Hidden", description="x")
        self.login(self.student)
        resp = self.client.post(reverse("portal:job_apply", args=[pending.pk]))
        self.assertEqual(resp.status_code, 404)

    def test_editing_approved_job_requires_reapproval(self):
        self.login(self.recruiter)
        self.client.post(reverse("portal:job_edit", args=[self.job.pk]), {
            "title": "SDE II", "job_type": "FULL_TIME", "description": "y", "min_cgpa": "7.5",
            "allowed_branches": ["CSE"],
        })
        self.job.refresh_from_db()
        self.assertEqual(self.job.title, "SDE II")
        self.assertEqual(self.job.status, ApprovalStatus.PENDING)


class RoleBoundaryTests(PortalTestCase):
    def test_student_cannot_open_admin_or_recruiter_pages(self):
        self.login(self.student)
        for name in ["portal:admin_dashboard", "portal:admin_queue", "portal:audit_log",
                     "portal:recruiter_dashboard"]:
            self.assertEqual(self.client.get(reverse(name)).status_code, 403, name)

    def test_recruiter_cannot_open_admin_pages(self):
        self.login(self.recruiter)
        self.assertEqual(self.client.get(reverse("portal:admin_queue")).status_code, 403)
        resp = self.client.post(reverse("portal:review_company", args=[self.company.pk]),
                                {"action": "approve"})
        self.assertEqual(resp.status_code, 403)

    def test_anonymous_redirected_to_login(self):
        resp = self.client.get(reverse("portal:job_list"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("portal:login"), resp["Location"])

    def test_recruiter_cannot_see_other_companys_applicants(self):
        self.login(self.other_recruiter)
        self.assertEqual(self.client.get(reverse("portal:applicants", args=[self.job.pk])).status_code, 404)

    def test_recruiter_cannot_change_other_companys_application(self):
        app, _ = services.apply_to_job(self.student, self.job)
        self.login(self.other_recruiter)
        resp = self.client.post(reverse("portal:application_status", args=[app.pk]),
                                {"status": "REJECTED"})
        self.assertEqual(resp.status_code, 404)
        app.refresh_from_db()
        self.assertEqual(app.status, "APPLIED")

    def test_student_cannot_see_another_students_application(self):
        app, _ = services.apply_to_job(self.student, self.job)
        self.login(self.low_cgpa)
        self.assertEqual(self.client.get(reverse("portal:application_detail", args=[app.pk])).status_code, 404)

    def test_registration_cannot_create_admin(self):
        resp = self.client.post(reverse("portal:register"), {
            "username": "sneaky", "first_name": "S", "email": "s@example.com", "role": "ADMIN",
            "password1": "Very$trongPass1", "password2": "Very$trongPass1",
        })
        self.assertEqual(resp.status_code, 200)  # form re-rendered with an error
        self.assertFalse(User.objects.filter(username="sneaky").exists())


class PipelineTests(PortalTestCase):
    def setUp(self):
        super().setUp()
        self.app, _ = services.apply_to_job(self.student, self.job)

    def test_single_valid_transition(self):
        self.login(self.recruiter)
        self.client.post(reverse("portal:application_status", args=[self.app.pk]), {"status": "SHORTLISTED"})
        self.app.refresh_from_db()
        self.assertEqual(self.app.status, "SHORTLISTED")
        self.assertEqual(self.app.events.count(), 2)  # applied + shortlisted

    def test_invalid_transition_rejected(self):
        self.assertFalse(services.change_status(self.app, "OFFERED", self.recruiter))
        self.app.refresh_from_db()
        self.assertEqual(self.app.status, "APPLIED")

    def test_final_state_cannot_change(self):
        services.change_status(self.app, "REJECTED", self.recruiter)
        self.assertFalse(services.change_status(self.app, "SHORTLISTED", self.recruiter))

    def test_batch_update_changes_valid_and_skips_invalid(self):
        s2 = self.make_user("s2", User.Role.STUDENT)
        StudentProfile.objects.create(user=s2, branch="IT", cgpa=Decimal("9"), graduation_year=2027,
                                      resume_link="https://example.com/c")
        app2, _ = services.apply_to_job(s2, self.job)
        services.change_status(app2, "REJECTED", self.recruiter)  # final, so batch must skip it

        self.login(self.recruiter)
        self.client.post(reverse("portal:application_batch", args=[self.job.pk]),
                         {"status": "SHORTLISTED", "application_ids": [self.app.pk, app2.pk]})
        self.app.refresh_from_db()
        app2.refresh_from_db()
        self.assertEqual(self.app.status, "SHORTLISTED")
        self.assertEqual(app2.status, "REJECTED")

    def test_batch_ignores_ids_from_other_jobs(self):
        other_job = JobPosting.objects.create(company=self.other_company, title="X", description="x",
                                              status=ApprovalStatus.APPROVED)
        other_app, _ = services.apply_to_job(self.student, other_job)
        self.login(self.recruiter)
        self.client.post(reverse("portal:application_batch", args=[self.job.pk]),
                         {"status": "REJECTED", "application_ids": [other_app.pk]})
        other_app.refresh_from_db()
        self.assertEqual(other_app.status, "APPLIED")

    def test_status_json_returns_only_own_applications(self):
        self.login(self.student)
        data = self.client.get(reverse("portal:application_status_json")).json()
        self.assertEqual(list(data.keys()), [str(self.app.pk)])


class AdminReviewTests(PortalTestCase):
    def test_approve_writes_audit_log_with_reviewer_and_timestamp(self):
        company = Company.objects.create(owner=self.make_user("r3", User.Role.RECRUITER), name="New Co")
        self.login(self.admin)
        self.client.post(reverse("portal:review_company", args=[company.pk]), {"action": "approve"})
        company.refresh_from_db()
        self.assertEqual(company.status, ApprovalStatus.APPROVED)
        log = AdminActionLog.objects.get(target_id=company.pk, target_type="COMPANY")
        self.assertEqual(log.admin, self.admin)
        self.assertEqual(log.action, "APPROVED")
        self.assertIsNotNone(log.created_at)

    def test_reject_requires_note(self):
        job = JobPosting.objects.create(company=self.company, title="P", description="x")
        self.login(self.admin)
        resp = self.client.post(reverse("portal:review_job", args=[job.pk]), {"action": "reject", "note": ""})
        self.assertEqual(resp.status_code, 200)
        job.refresh_from_db()
        self.assertEqual(job.status, ApprovalStatus.PENDING)
        self.assertFalse(AdminActionLog.objects.exists())

    def test_reject_with_note_is_logged(self):
        job = JobPosting.objects.create(company=self.company, title="P", description="x")
        self.login(self.admin)
        self.client.post(reverse("portal:review_job", args=[job.pk]), {"action": "reject", "note": "Too vague"})
        job.refresh_from_db()
        self.assertEqual(job.status, ApprovalStatus.REJECTED)
        self.assertEqual(AdminActionLog.objects.get().note, "Too vague")

    def test_audit_log_page_shows_reviewer_id(self):
        services.review(self.company, self.admin, ApprovalStatus.REJECTED, "x")
        self.login(self.admin)
        resp = self.client.get(reverse("portal:audit_log"))
        self.assertContains(resp, f"#{self.admin.pk}")


class SmokeTests(TestCase):
    """Every page renders for its role with the demo data loaded."""

    def setUp(self):
        from django.core.management import call_command
        call_command("seed_demo", stdout=StringIO())

    def test_all_pages_render(self):
        job = JobPosting.objects.visible().first()
        app = Application.objects.filter(job__company__owner__username="recruiter").first()
        pages = {
            "student": ["portal:student_dashboard", "portal:profile_edit", "portal:job_list",
                        "portal:application_list", ("portal:job_detail", job.pk)],
            "recruiter": ["portal:recruiter_dashboard", "portal:company_edit", "portal:job_create",
                          ("portal:applicants", app.job_id), ("portal:applicant_detail", app.pk)],
            "admin": ["portal:admin_dashboard", "portal:admin_queue", "portal:audit_log",
                      ("portal:review_company", Company.objects.first().pk),
                      ("portal:review_job", JobPosting.objects.first().pk)],
        }
        for username, names in pages.items():
            self.client.force_login(User.objects.get(username=username))
            for item in names:
                name, args = (item, []) if isinstance(item, str) else (item[0], [item[1]])
                resp = self.client.get(reverse(name, args=args))
                self.assertEqual(resp.status_code, 200, f"{username} {name}")
        self.client.logout()
        for name in ["portal:home", "portal:login", "portal:register"]:
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)
