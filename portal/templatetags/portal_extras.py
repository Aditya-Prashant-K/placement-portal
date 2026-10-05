from django import template

register = template.Library()

BADGES = {
    # approval states
    "PENDING": "warning text-dark",
    "APPROVED": "success",
    "REJECTED": "danger",
    # application pipeline
    "APPLIED": "secondary",
    "UNDER_REVIEW": "info text-dark",
    "SHORTLISTED": "primary",
    "INTERVIEW": "warning text-dark",
    "OFFERED": "success",
}


@register.filter
def badge(value):
    """Map a status string to a Bootstrap badge colour class."""
    return BADGES.get(str(value), "secondary")
