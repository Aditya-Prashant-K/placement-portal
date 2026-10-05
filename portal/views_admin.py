from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render

from .decorators import role_required
from .forms import ReviewForm
from .models import AdminActionLog, ApprovalStatus, Company, JobPosting, User
from .services import review

admin_only = role_required(User.Role.ADMIN)


@admin_only
def dashboard(request):
    context = {
        "pending_companies": Company.objects.filter(status=ApprovalStatus.PENDING).count(),
        "pending_jobs": JobPosting.objects.filter(status=ApprovalStatus.PENDING).count(),
        "recent_logs": AdminActionLog.objects.select_related("admin")[:5],
        "log_total": AdminActionLog.objects.count(),
    }
    return render(request, "portal/adminportal/dashboard.html", context)


@admin_only
def queue(request):
    context = {
        "companies": Company.objects.filter(status=ApprovalStatus.PENDING).select_related("owner"),
        "jobs": JobPosting.objects.filter(status=ApprovalStatus.PENDING).select_related("company"),
    }
    return render(request, "portal/adminportal/queue.html", context)


def _handle_review(request, obj, kind, redirect_to="portal:admin_queue"):
    form = ReviewForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        action = request.POST.get("action")
        note = form.cleaned_data["note"].strip()
        decision = {"approve": ApprovalStatus.APPROVED, "reject": ApprovalStatus.REJECTED}.get(
            action
        )
        if decision is None:
            messages.error(request, "Unknown action.")
        elif decision == ApprovalStatus.REJECTED and not note:
            form.add_error("note", "Please explain the rejection - the recruiter will see it.")
        elif review(obj, request.user, decision, note):
            messages.success(request, f"{kind} {decision.label.lower()}: {obj}.")
            return redirect(redirect_to)
        else:
            messages.info(request, f"This {kind.lower()} is already {decision.label.lower()}.")
            return redirect(redirect_to)
    return render(
        request,
        "portal/adminportal/review.html",
        {"obj": obj, "kind": kind, "form": form, "is_job": kind == "Job posting"},
    )


@admin_only
def review_company(request, pk):
    company = get_object_or_404(Company.objects.select_related("owner"), pk=pk)
    return _handle_review(request, company, "Company")


@admin_only
def review_job(request, pk):
    job = get_object_or_404(JobPosting.objects.select_related("company"), pk=pk)
    return _handle_review(request, job, "Job posting")


@admin_only
def audit_log(request):
    logs = AdminActionLog.objects.select_related("admin")
    action = request.GET.get("action", "")
    target = request.GET.get("target", "")
    if action in AdminActionLog.Action.values:
        logs = logs.filter(action=action)
    if target in AdminActionLog.TargetType.values:
        logs = logs.filter(target_type=target)
    page = Paginator(logs, 20).get_page(request.GET.get("page"))
    context = {
        "page": page,
        "action": action,
        "target": target,
        "actions": AdminActionLog.Action.choices,
        "targets": AdminActionLog.TargetType.choices,
    }
    return render(request, "portal/adminportal/audit_log.html", context)
