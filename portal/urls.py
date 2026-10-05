from django.contrib.auth import views as auth_views
from django.urls import path

from . import views_admin, views_public, views_recruiter, views_student

app_name = "portal"

urlpatterns = [
    # --- public / auth ---
    path("", views_public.home, name="home"),
    path("dashboard/", views_public.dashboard, name="dashboard"),
    path("register/", views_public.register, name="register"),
    path(
        "login/",
        auth_views.LoginView.as_view(template_name="portal/login.html"),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    # --- student portal ---
    path("student/", views_student.dashboard, name="student_dashboard"),
    path("student/profile/", views_student.profile_edit, name="profile_edit"),
    path("student/jobs/", views_student.job_list, name="job_list"),
    path("student/jobs/<int:pk>/", views_student.job_detail, name="job_detail"),
    path("student/jobs/<int:pk>/apply/", views_student.job_apply, name="job_apply"),
    path("student/applications/", views_student.application_list, name="application_list"),
    path(
        "student/applications/status.json",
        views_student.application_status_json,
        name="application_status_json",
    ),
    path(
        "student/applications/<int:pk>/",
        views_student.application_detail,
        name="application_detail",
    ),
    # --- recruiter portal ---
    path("recruiter/", views_recruiter.dashboard, name="recruiter_dashboard"),
    path("recruiter/company/", views_recruiter.company_edit, name="company_edit"),
    path("recruiter/jobs/new/", views_recruiter.job_create, name="job_create"),
    path("recruiter/jobs/<int:pk>/edit/", views_recruiter.job_edit, name="job_edit"),
    path("recruiter/jobs/<int:pk>/applicants/", views_recruiter.applicants, name="applicants"),
    path(
        "recruiter/jobs/<int:pk>/applicants/batch/",
        views_recruiter.application_batch,
        name="application_batch",
    ),
    path(
        "recruiter/applications/<int:pk>/",
        views_recruiter.applicant_detail,
        name="applicant_detail",
    ),
    path(
        "recruiter/applications/<int:pk>/status/",
        views_recruiter.application_status,
        name="application_status",
    ),
    # --- placement cell admin portal ---
    path("admin-portal/", views_admin.dashboard, name="admin_dashboard"),
    path("admin-portal/queue/", views_admin.queue, name="admin_queue"),
    path("admin-portal/companies/<int:pk>/", views_admin.review_company, name="review_company"),
    path("admin-portal/jobs/<int:pk>/", views_admin.review_job, name="review_job"),
    path("admin-portal/audit-log/", views_admin.audit_log, name="audit_log"),
]
