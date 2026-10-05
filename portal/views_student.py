from django.contrib import messages
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .decorators import role_required
from .forms import StudentProfileForm
from .models import Application, JobPosting, StudentProfile, User
from .services import apply_to_job, check_eligibility, get_profile

student_only = role_required(User.Role.STUDENT)


@student_only
def dashboard(request):
    applications = request.user.applications.select_related("job", "job__company")
    counts = {}
    for app in applications:
        counts[app.status] = counts.get(app.status, 0) + 1
    context = {
        "profile": get_profile(request.user),
        "recent": applications[:5],
        "total": len(applications),
        "counts": counts,
        "in_progress": counts.get("SHORTLISTED", 0) + counts.get("INTERVIEW", 0),
        "open_jobs": JobPosting.objects.visible().count(),
    }
    return render(request, "portal/student/dashboard.html", context)


@student_only
def profile_edit(request):
    profile = get_profile(request.user)
    form = StudentProfileForm(request.POST or None, instance=profile)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.user = request.user
        obj.save()
        messages.success(request, "Profile saved.")
        return redirect("portal:student_dashboard")
    return render(request, "portal/student/profile_form.html", {"form": form, "profile": profile})


@student_only
def job_list(request):
    jobs = JobPosting.objects.visible().select_related("company")

    q = request.GET.get("q", "").strip()
    if q:
        jobs = jobs.filter(
            Q(title__icontains=q) | Q(company__name__icontains=q) | Q(location__icontains=q)
        )
    job_type = request.GET.get("type", "")
    if job_type in JobPosting.JobType.values:
        jobs = jobs.filter(job_type=job_type)

    applied_ids = set(request.user.applications.values_list("job_id", flat=True))
    rows = [
        {
            "job": job,
            "reasons": check_eligibility(request.user, job),
            "applied": job.pk in applied_ids,
        }
        for job in jobs
    ]
    only_eligible = request.GET.get("eligible") == "1"
    if only_eligible:
        rows = [r for r in rows if not r["reasons"]]

    context = {
        "rows": rows,
        "q": q,
        "job_type": job_type,
        "only_eligible": only_eligible,
        "job_types": JobPosting.JobType.choices,
        "profile": get_profile(request.user),
    }
    return render(request, "portal/student/job_list.html", context)


def _job_detail_context(request, job, reasons=None):
    return {
        "job": job,
        "reasons": check_eligibility(request.user, job) if reasons is None else reasons,
        "application": Application.objects.filter(student=request.user, job=job).first(),
    }


@student_only
def job_detail(request, pk):
    # Only approved postings from approved companies exist as far as students are concerned.
    job = get_object_or_404(JobPosting.objects.visible().select_related("company"), pk=pk)
    return render(request, "portal/student/job_detail.html", _job_detail_context(request, job))


@student_only
@require_POST
def job_apply(request, pk):
    job = get_object_or_404(JobPosting.objects.visible().select_related("company"), pk=pk)
    application, reasons = apply_to_job(request.user, job)
    if application is None:
        # Blocked on the server: re-render the page with an explanatory notice.
        context = _job_detail_context(request, job, reasons=reasons)
        context["blocked"] = True
        return render(request, "portal/student/job_detail.html", context)
    messages.success(request, f"Application submitted to {job.company.name}.")
    return redirect("portal:application_detail", pk=application.pk)


@student_only
def application_list(request):
    applications = request.user.applications.select_related("job", "job__company")
    return render(request, "portal/student/application_list.html", {"applications": applications})


@student_only
def application_detail(request, pk):
    application = get_object_or_404(
        Application.objects.select_related("job", "job__company"), pk=pk, student=request.user
    )
    events = application.events.select_related("changed_by")
    return render(
        request,
        "portal/student/application_detail.html",
        {"application": application, "events": events},
    )


@student_only
def application_status_json(request):
    """Polled by the tracking page every few seconds so statuses update live."""
    data = {
        str(a.pk): {"status": a.status, "label": a.get_status_display()}
        for a in request.user.applications.all()
    }
    return JsonResponse(data)
