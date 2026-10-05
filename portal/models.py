"""Data model for the Campus Placement & Internship Portal.

Entity overview
---------------
User               -> one account, with a `role` (STUDENT / RECRUITER / ADMIN)
StudentProfile     -> branch, CGPA, graduation year, resume link (students only)
Company            -> created by a recruiter; must be approved by an admin
JobPosting         -> belongs to a company; has eligibility criteria; must be approved
Application        -> a student's application to a posting, with a status
ApplicationEvent   -> history of every status change (powers the tracking timeline)
AdminActionLog     -> audit trail of admin approvals / rejections
"""
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

BRANCHES = [
    ("CSE", "Computer Science & Engineering"),
    ("IT", "Information Technology"),
    ("ECE", "Electronics & Communication"),
    ("EEE", "Electrical & Electronics"),
    ("MECH", "Mechanical Engineering"),
    ("CIVIL", "Civil Engineering"),
]
BRANCH_LABELS = dict(BRANCHES)


class ApprovalStatus(models.TextChoices):
    PENDING = "PENDING", "Pending review"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"


class User(AbstractUser):
    class Role(models.TextChoices):
        STUDENT = "STUDENT", "Student"
        RECRUITER = "RECRUITER", "Recruiter"
        ADMIN = "ADMIN", "Placement Cell Admin"

    role = models.CharField(max_length=10, choices=Role.choices, default=Role.STUDENT)

    def save(self, *args, **kwargs):
        # Anyone created with `createsuperuser` is a placement-cell admin.
        if self.is_superuser:
            self.role = self.Role.ADMIN
        super().save(*args, **kwargs)

    @property
    def is_student(self):
        return self.role == self.Role.STUDENT

    @property
    def is_recruiter(self):
        return self.role == self.Role.RECRUITER

    @property
    def is_placement_admin(self):
        return self.role == self.Role.ADMIN

    @property
    def display_name(self):
        return self.get_full_name() or self.username


class StudentProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile"
    )
    branch = models.CharField(max_length=10, choices=BRANCHES)
    cgpa = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(10)],
        help_text="On a 10-point scale, e.g. 8.45",
    )
    graduation_year = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(2020), MaxValueValidator(2040)]
    )
    resume_link = models.URLField(help_text="Public link to your resume (Drive, GitHub, etc.)")

    def __str__(self):
        return f"{self.user.display_name} ({self.branch}, {self.cgpa})"


class Company(models.Model):
    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="company"
    )
    name = models.CharField(max_length=120, unique=True)
    industry = models.CharField(max_length=80, blank=True)
    website = models.URLField(blank=True)
    location = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)

    status = models.CharField(
        max_length=10, choices=ApprovalStatus.choices, default=ApprovalStatus.PENDING
    )
    review_note = models.TextField(blank=True, help_text="Admin's note, shown to the recruiter")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "companies"
        ordering = ["name"]

    def __str__(self):
        return self.name


class JobQuerySet(models.QuerySet):
    def visible(self):
        """Postings students may see: the posting AND its company are approved."""
        return self.filter(
            status=ApprovalStatus.APPROVED, company__status=ApprovalStatus.APPROVED
        )


class JobPosting(models.Model):
    class JobType(models.TextChoices):
        FULL_TIME = "FULL_TIME", "Full-time placement"
        INTERNSHIP = "INTERNSHIP", "Internship"

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="jobs")
    title = models.CharField(max_length=140)
    job_type = models.CharField(max_length=12, choices=JobType.choices, default=JobType.FULL_TIME)
    location = models.CharField(max_length=100, blank=True)
    compensation = models.CharField(
        max_length=80, blank=True, help_text="CTC or stipend, e.g. '12 LPA' or '30,000/month'"
    )
    description = models.TextField()

    # Eligibility criteria (enforced server-side in services.check_eligibility)
    min_cgpa = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(10)],
    )
    # Comma-separated branch codes, e.g. "CSE,IT". Empty string = all branches.
    allowed_branches = models.CharField(max_length=80, blank=True)
    deadline = models.DateField(null=True, blank=True)

    status = models.CharField(
        max_length=10, choices=ApprovalStatus.choices, default=ApprovalStatus.PENDING
    )
    review_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = JobQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} @ {self.company.name}"

    def allowed_branch_list(self):
        return [b for b in self.allowed_branches.split(",") if b]

    def allows_branch(self, branch):
        allowed = self.allowed_branch_list()
        return not allowed or branch in allowed

    def allowed_branches_display(self):
        allowed = self.allowed_branch_list()
        return ", ".join(allowed) if allowed else "All branches"


class Application(models.Model):
    class Status(models.TextChoices):
        APPLIED = "APPLIED", "Applied"
        UNDER_REVIEW = "UNDER_REVIEW", "Under review"
        SHORTLISTED = "SHORTLISTED", "Shortlisted"
        INTERVIEW = "INTERVIEW", "Interview"
        OFFERED = "OFFERED", "Offered"
        REJECTED = "REJECTED", "Rejected"

    # The hiring pipeline: which status may follow which.
    # OFFERED and REJECTED are final.
    ALLOWED_TRANSITIONS = {
        "APPLIED": ["UNDER_REVIEW", "SHORTLISTED", "REJECTED"],
        "UNDER_REVIEW": ["SHORTLISTED", "REJECTED"],
        "SHORTLISTED": ["INTERVIEW", "REJECTED"],
        "INTERVIEW": ["OFFERED", "REJECTED"],
        "OFFERED": [],
        "REJECTED": [],
    }

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="applications"
    )
    job = models.ForeignKey(JobPosting, on_delete=models.CASCADE, related_name="applications")
    status = models.CharField(max_length=14, choices=Status.choices, default=Status.APPLIED)
    applied_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-applied_at"]
        constraints = [
            models.UniqueConstraint(fields=["student", "job"], name="one_application_per_job")
        ]

    def __str__(self):
        return f"{self.student.username} -> {self.job} [{self.status}]"

    def allowed_next(self):
        """List of (value, label) statuses this application may move to."""
        labels = dict(self.Status.choices)
        return [(s, labels[s]) for s in self.ALLOWED_TRANSITIONS.get(self.status, [])]

    def can_move_to(self, new_status):
        return new_status in self.ALLOWED_TRANSITIONS.get(self.status, [])


class ApplicationEvent(models.Model):
    """One row per status change - this is what the student's timeline shows."""

    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="events")
    status = models.CharField(max_length=14, choices=Application.Status.choices)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    note = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]


class AdminActionLog(models.Model):
    """Audit record of an admin approving or rejecting a company / posting."""

    class Action(models.TextChoices):
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    class TargetType(models.TextChoices):
        COMPANY = "COMPANY", "Company"
        JOB = "JOB", "Job posting"

    # PROTECT: an admin with audit history can't be deleted and erase the trail.
    admin = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="admin_actions"
    )
    action = models.CharField(max_length=10, choices=Action.choices)
    target_type = models.CharField(max_length=10, choices=TargetType.choices)
    target_id = models.PositiveIntegerField()
    target_label = models.CharField(max_length=200, help_text="Snapshot of the name at review time")
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.action} {self.target_type} #{self.target_id} by admin #{self.admin_id}"
