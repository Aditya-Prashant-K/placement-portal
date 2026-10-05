from django.contrib import messages
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .decorators import role_required
from .forms import CompanyForm, JobPostingForm, StatusForm
from .models import Application, ApprovalStatus, Company, JobPosting, User
from .services import batch_change_status, change_status

recruiter_only = role_required(User.Role.RECRUITER)


def _get_company(user):
    try:
        return user.company
    except Company.DoesNotExist:
        return None


def _own_job_or_404(request, pk):
    # Filtering on company__owner is the ownership check: recruiters can never
    # reach another company's posting, even by guessing its URL.
    return get_object_or_404(
        JobPosting.objects.select_related("company"), pk=pk, company__owner=request.user
    )


@recruiter_only
def dashboard(request):
    company = _get_company(request.user)
    jobs = []
    if company:
        jobs = company.jobs.annotate(applicant_count=Count("applications"))
    return render(request, "portal/recruiter/dashboard.html", {"company": company, "jobs": jobs})


@recruiter_only
def company_edit(request):
    company = _get_company(request.user)
    form = CompanyForm(request.POST or None, instance=company)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.owner = request.user
        if company is None:
            messages.success(request, "Company submitted. The placement cell will review it.")
        elif company.status == ApprovalStatus.REJECTED:
            obj.status = ApprovalStatus.PENDING  # resubmission after rejection
            messages.success(request, "Company resubmitted for review.")
        else:
            messages.success(request, "Company details updated.")
        obj.save()
        return redirect("portal:recruiter_dashboard")
    return render(request, "portal/recruiter/company_form.html", {"form": form, "company": company})


def _save_job(request, form, company, instance=None):
    job = form.save(commit=False)
    job.company = company
    if instance is not None and instance.status != ApprovalStatus.PENDING:
        job.status = ApprovalStatus.PENDING  # edits to a reviewed posting need re-approval
    job.save()
    return job


@recruiter_only
def job_create(request):
    company = _get_company(request.user)
    if company is None:
        messages.warning(request, "Create your company profile before posting a job.")
        return redirect("portal:company_edit")
    form = JobPostingForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        _save_job(request, form, company)
        messages.success(request, "Job posting submitted for placement-cell approval.")
        return redirect("portal:recruiter_dashboard")
    return render(request, "portal/recruiter/job_form.html", {"form": form, "job": None})


@recruiter_only
def job_edit(request, pk):
    job = _own_job_or_404(request, pk)
    form = JobPostingForm(request.POST or None, instance=job)
    if request.method == "POST" and form.is_valid():
        was_reviewed = job.status != ApprovalStatus.PENDING
        _save_job(request, form, job.company, instance=job)
        if was_reviewed:
            messages.info(request, "Posting updated and sent back for approval.")
        else:
            messages.success(request, "Posting updated.")
        return redirect("portal:recruiter_dashboard")
    return render(request, "portal/recruiter/job_form.html", {"form": form, "job": job})


@recruiter_only
def applicants(request, pk):
    job = _own_job_or_404(request, pk)
    applications = job.applications.select_related("student", "student__profile")
    status_filter = request.GET.get("status", "")
    if status_filter in Application.Status.values:
        applications = applications.filter(status=status_filter)
    context = {
        "job": job,
        "applications": applications,
        "status_filter": status_filter,
        "statuses": Application.Status.choices,
    }
    return render(request, "portal/recruiter/applicants.html", context)


@recruiter_only
def applicant_detail(request, pk):
    application = get_object_or_404(
        Application.objects.select_related("student", "student__profile", "job", "job__company"),
        pk=pk,
        job__company__owner=request.user,
    )
    return render(
        request,
        "portal/recruiter/applicant_detail.html",
        {"application": application, "events": application.events.select_related("changed_by")},
    )


def _safe_next(request, fallback):
    target = request.POST.get("next", "")
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        return target
    return fallback


@recruiter_only
@require_POST
def application_status(request, pk):
    """Single status transition."""
    application = get_object_or_404(
        Application.objects.select_related("job", "student"),
        pk=pk,
        job__company__owner=request.user,
    )
    form = StatusForm(request.POST)
    fallback = reverse("portal:applicants", args=[application.job_id])
    if form.is_valid():
        new_status = form.cleaned_data["status"]
        if change_status(application, new_status, by=request.user):
            messages.success(
                request,
                f"{application.student.display_name} moved to "
                f"{application.get_status_display()}.",
            )
        else:
            messages.error(
                request,
                f"Can't move from {application.get_status_display()} to "
                f"{dict(Application.Status.choices)[new_status]}.",
            )
    else:
        messages.error(request, "Invalid status.")
    return redirect(_safe_next(request, fallback))


@recruiter_only
@require_POST
def application_batch(request, pk):
    """Batch status transition for the ticked applicants of one posting."""
    job = _own_job_or_404(request, pk)
    form = StatusForm(request.POST)
    ids = request.POST.getlist("application_ids")
    if not ids:
        messages.warning(request, "Tick at least one applicant first.")
    elif not form.is_valid():
        messages.error(request, "Choose a valid status for the batch update.")
    else:
        # Restricting to this job's applications stops tampering with other IDs.
        selected = job.applications.filter(pk__in=ids).select_related("student")
        changed, skipped = batch_change_status(selected, form.cleaned_data["status"], request.user)
        msg = f"Updated {changed} applicant(s)."
        if skipped:
            msg += f" Skipped {skipped} where that status isn't a valid next step."
        (messages.success if changed else messages.warning)(request, msg)
    return redirect("portal:applicants", pk=job.pk)
