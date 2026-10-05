from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import BRANCHES, Application, Company, JobPosting, StudentProfile, User


class BootstrapMixin:
    """Give every widget the right Bootstrap CSS class."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxSelectMultiple):
                widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(widget, forms.Select):
                widget.attrs.setdefault("class", "form-select")
            else:
                widget.attrs.setdefault("class", "form-control")


class RegisterForm(BootstrapMixin, UserCreationForm):
    # Only Student and Recruiter can self-register. Admin accounts are created
    # by `createsuperuser` / the seed command, never through this form.
    role = forms.ChoiceField(
        choices=[(User.Role.STUDENT, "Student"), (User.Role.RECRUITER, "Company recruiter")],
        initial=User.Role.STUDENT,
    )

    class Meta:
        model = User
        fields = ("username", "first_name", "last_name", "email", "role")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["first_name"].required = True
        self.fields["email"].required = True

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = self.cleaned_data["role"]  # validated against the two choices above
        if commit:
            user.save()
        return user


class StudentProfileForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = StudentProfile
        fields = ("branch", "cgpa", "graduation_year", "resume_link")
        widgets = {"cgpa": forms.NumberInput(attrs={"step": "0.01", "min": "0", "max": "10"})}


class CompanyForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Company
        fields = ("name", "industry", "website", "location", "description")
        widgets = {"description": forms.Textarea(attrs={"rows": 4})}


class JobPostingForm(BootstrapMixin, forms.ModelForm):
    # Stored as a comma-separated string on the model; edited as checkboxes here.
    allowed_branches = forms.MultipleChoiceField(
        choices=BRANCHES,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Leave all unticked to allow every department.",
    )

    class Meta:
        model = JobPosting
        fields = (
            "title",
            "job_type",
            "location",
            "compensation",
            "description",
            "min_cgpa",
            "allowed_branches",
            "deadline",
        )
        widgets = {
            "description": forms.Textarea(attrs={"rows": 5}),
            "deadline": forms.DateInput(attrs={"type": "date"}),
            "min_cgpa": forms.NumberInput(attrs={"step": "0.01", "min": "0", "max": "10"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial["allowed_branches"] = self.instance.allowed_branch_list()

    def clean_allowed_branches(self):
        return ",".join(self.cleaned_data["allowed_branches"])


class ReviewForm(BootstrapMixin, forms.Form):
    note = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Optional for approvals. Required when rejecting - the recruiter will see it.",
    )


class StatusForm(BootstrapMixin, forms.Form):
    status = forms.ChoiceField(choices=Application.Status.choices)
