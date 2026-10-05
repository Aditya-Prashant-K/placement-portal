"""Business rules, kept out of the views so they are easy to read and to test.

The three rules that matter most for this project:
1. check_eligibility / apply_to_job  -> server-side eligibility gating
2. change_status / batch_change_status -> the hiring pipeline state machine
3. review                              -> admin approval + audit logging
"""
from django.db import transaction
from django.utils import timezone

from .models import (
    AdminActionLog,
    Application,
    ApplicationEvent,
    Company,
    StudentProfile,
)


def get_profile(user):
    """Return the student's profile, or None if they haven't filled it in yet."""
    try:
        return user.profile
    except StudentProfile.DoesNotExist:
        return None


# --------------------------------------------------------------------------
# 1. Eligibility gating
# --------------------------------------------------------------------------
def check_eligibility(user, job):
    """Return a list of human-readable reasons the student is NOT eligible.

    An empty list means eligible. This is the single source of truth: the job
    pages use it to show notices, and apply_to_job() uses it to block the
    submission, so the UI can never disagree with the backend.
    """
    profile = get_profile(user)
    if profile is None:
        return [
            "Complete your student profile (branch, CGPA, graduation year, resume link) "
            "before applying."
        ]

    reasons = []
    if profile.cgpa < job.min_cgpa:
        reasons.append(
            f"Your CGPA ({profile.cgpa}) is below the minimum required for this posting "
            f"({job.min_cgpa})."
        )
    if not job.allows_branch(profile.branch):
        reasons.append(
            f"Your branch ({profile.branch}) is not among the eligible departments for this "
            f"posting ({job.allowed_branches_display()})."
        )
    if job.deadline and job.deadline < timezone.localdate():
        reasons.append(f"The application deadline ({job.deadline:%d %b %Y}) has passed.")
    return reasons


def apply_to_job(user, job):
    """Try to create an application. Returns (application, reasons).

    On success: (Application, []). If blocked: (None, [reason, ...]).
    """
    reasons = check_eligibility(user, job)
    if reasons:
        return None, reasons

    with transaction.atomic():
        application, created = Application.objects.get_or_create(student=user, job=job)
        if not created:
            return None, ["You have already applied to this posting."]
        ApplicationEvent.objects.create(
            application=application,
            status=application.status,
            changed_by=user,
            note="Application submitted",
        )
    return application, []


# --------------------------------------------------------------------------
# 2. Application pipeline
# --------------------------------------------------------------------------
def change_status(application, new_status, by, note=""):
    """Move one application to a new status. Returns False if not allowed."""
    if not application.can_move_to(new_status):
        return False
    with transaction.atomic():
        application.status = new_status
        application.save(update_fields=["status", "updated_at"])
        ApplicationEvent.objects.create(
            application=application, status=new_status, changed_by=by, note=note
        )
    return True


def batch_change_status(applications, new_status, by):
    """Apply one status to many applications. Returns (changed, skipped).

    Applications for which the move is not a valid pipeline transition are
    skipped (not silently forced), and the count is reported back to the UI.
    """
    changed = skipped = 0
    for application in applications:
        if change_status(application, new_status, by, note="Batch update"):
            changed += 1
        else:
            skipped += 1
    return changed, skipped


# --------------------------------------------------------------------------
# 3. Admin review + audit log
# --------------------------------------------------------------------------
def review(obj, admin, decision, note=""):
    """Approve or reject a Company or JobPosting and write the audit record.

    `decision` is "APPROVED" or "REJECTED". Returns False when the object is
    already in that state (nothing to do, nothing to log).
    """
    if obj.status == decision:
        return False

    target_type = (
        AdminActionLog.TargetType.COMPANY
        if isinstance(obj, Company)
        else AdminActionLog.TargetType.JOB
    )
    with transaction.atomic():
        obj.status = decision
        obj.review_note = note
        obj.save(update_fields=["status", "review_note", "updated_at"])
        AdminActionLog.objects.create(
            admin=admin,
            action=decision,
            target_type=target_type,
            target_id=obj.pk,
            target_label=str(obj),
            note=note,
        )
    return True
