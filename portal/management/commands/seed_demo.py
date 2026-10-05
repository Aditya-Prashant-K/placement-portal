"""Populate the database with demo data.

    python manage.py seed_demo           # add demo data (safe to re-run)
    python manage.py seed_demo --reset   # wipe portal data first, then seed

Every demo account uses the password  Demo@1234
"""
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from portal import services
from portal.models import (
    AdminActionLog,
    Application,
    ApprovalStatus,
    Company,
    JobPosting,
    StudentProfile,
    User,
)

PASSWORD = "Demo@1234"

ADMINS = [
    ("admin", "Priya", "Raman"),
    ("admin2", "Karthik", "Iyer"),
]

STUDENTS = [
    # username, first, last, branch, cgpa, grad year
    ("student", "Aarav", "Sharma", "CSE", "8.70", 2027),
    ("student2", "Diya", "Menon", "ECE", "7.20", 2027),
    ("student3", "Rohan", "Gupta", "MECH", "6.40", 2027),
    ("student4", "Ananya", "Rao", "IT", "9.10", 2027),
    ("student5", "Vikram", "Nair", "CSE", "7.90", 2027),
    ("student6", "Sneha", "Pillai", "EEE", "8.20", 2027),
    ("student7", "Arjun", "Reddy", "CSE", "9.40", 2027),
    ("student8", "Meera", "Joshi", "CIVIL", "7.60", 2027),
]

# username, first, last, company fields, company decision
RECRUITERS = [
    (
        "recruiter", "Neha", "Kapoor",
        dict(name="Nimbus Cloud Systems", industry="Cloud infrastructure",
             website="https://example.com/nimbus", location="Bengaluru",
             description="Builds managed infrastructure for Indian startups."),
        ApprovalStatus.APPROVED,
    ),
    (
        "recruiter2", "Rahul", "Verma",
        dict(name="Quantix Analytics", industry="Data & analytics",
             website="https://example.com/quantix", location="Chennai",
             description="Analytics consulting for retail and logistics."),
        ApprovalStatus.APPROVED,
    ),
    (
        "recruiter3", "Fatima", "Sheikh",
        dict(name="Voltline Motors", industry="Electric vehicles",
             website="https://example.com/voltline", location="Pune",
             description="EV drivetrains and battery management systems."),
        ApprovalStatus.PENDING,  # left in the admin queue on purpose
    ),
]

# company name, job fields, decision
JOBS = [
    ("Nimbus Cloud Systems",
     dict(title="Software Development Engineer", job_type="FULL_TIME", location="Bengaluru",
          compensation="18 LPA", min_cgpa=Decimal("8.00"), allowed_branches="CSE,IT",
          description="Build and operate backend services in Python and Go.\nWork on APIs used by thousands of customers."),
     ApprovalStatus.APPROVED),
    ("Nimbus Cloud Systems",
     dict(title="Cloud Support Intern", job_type="INTERNSHIP", location="Remote",
          compensation="35,000/month", min_cgpa=Decimal("7.00"), allowed_branches="CSE,IT,ECE,EEE",
          description="Six-month internship helping customers debug deployments on Linux and AWS."),
     ApprovalStatus.APPROVED),
    ("Quantix Analytics",
     dict(title="Data Analyst", job_type="FULL_TIME", location="Chennai",
          compensation="9 LPA", min_cgpa=Decimal("6.50"), allowed_branches="",
          description="SQL, dashboards and stakeholder reporting. Open to all branches."),
     ApprovalStatus.APPROVED),
    ("Quantix Analytics",
     dict(title="Machine Learning Engineer", job_type="FULL_TIME", location="Chennai",
          compensation="16 LPA", min_cgpa=Decimal("8.50"), allowed_branches="CSE,IT",
          description="Forecasting models for retail demand."),
     ApprovalStatus.PENDING),  # waiting in the admin queue
    ("Quantix Analytics",
     dict(title="Sales Intern", job_type="INTERNSHIP", location="Chennai",
          compensation="10,000/month", min_cgpa=Decimal("5.00"), allowed_branches="",
          description="Cold outreach to retail chains."),
     ApprovalStatus.REJECTED),  # shows a rejection in the audit log
    ("Voltline Motors",
     dict(title="Battery Systems Engineer", job_type="FULL_TIME", location="Pune",
          compensation="12 LPA", min_cgpa=Decimal("7.50"), allowed_branches="EEE,ECE,MECH",
          description="Design and test battery management systems."),
     ApprovalStatus.PENDING),
]

# (student username, job title, status path after APPLIED)
APPLICATIONS = [
    ("student", "Software Development Engineer", ["UNDER_REVIEW", "SHORTLISTED", "INTERVIEW"]),
    ("student", "Data Analyst", ["SHORTLISTED"]),
    ("student4", "Software Development Engineer", ["SHORTLISTED", "INTERVIEW", "OFFERED"]),
    ("student7", "Software Development Engineer", []),
    ("student5", "Cloud Support Intern", ["UNDER_REVIEW"]),
    ("student6", "Cloud Support Intern", ["REJECTED"]),
    ("student2", "Cloud Support Intern", []),
    ("student2", "Data Analyst", ["UNDER_REVIEW"]),
    ("student8", "Data Analyst", []),
]


class Command(BaseCommand):
    help = "Populate the database with demo users, companies, postings and applications."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete existing portal data first.")

    @transaction.atomic
    def handle(self, *args, **opts):
        if opts["reset"]:
            AdminActionLog.objects.all().delete()
            Application.objects.all().delete()
            JobPosting.objects.all().delete()
            Company.objects.all().delete()
            User.objects.filter(is_superuser=False).delete()
            self.stdout.write("Cleared existing portal data.")

        if User.objects.filter(username="admin").exists() and not opts["reset"]:
            self.stdout.write(self.style.WARNING(
                "Demo data already present. Use --reset to start fresh."))
            return

        admins = [self._user(u, f, l, User.Role.ADMIN, staff=True) for u, f, l in ADMINS]

        students = {}
        for username, first, last, branch, cgpa, year in STUDENTS:
            user = self._user(username, first, last, User.Role.STUDENT)
            StudentProfile.objects.update_or_create(
                user=user,
                defaults=dict(branch=branch, cgpa=Decimal(cgpa), graduation_year=year,
                              resume_link=f"https://example.com/resumes/{username}.pdf"),
            )
            students[username] = user

        companies, recruiters = {}, {}
        for i, (username, first, last, fields, decision) in enumerate(RECRUITERS):
            user = self._user(username, first, last, User.Role.RECRUITER)
            company = Company.objects.create(owner=user, **fields)
            if decision != ApprovalStatus.PENDING:
                services.review(company, admins[i % len(admins)], decision,
                                "Verified company registration documents.")
            companies[company.name] = company
            recruiters[company.name] = user

        jobs = {}
        deadline = timezone.localdate() + timedelta(days=30)
        for i, (company_name, fields, decision) in enumerate(JOBS):
            job = JobPosting.objects.create(company=companies[company_name], deadline=deadline, **fields)
            if decision == ApprovalStatus.APPROVED:
                services.review(job, admins[i % len(admins)], decision, "Criteria look reasonable.")
            elif decision == ApprovalStatus.REJECTED:
                services.review(job, admins[0], decision,
                                "Stipend below the institute's minimum for internships.")
            jobs[job.title] = job

        for username, title, path in APPLICATIONS:
            job = jobs[title]
            application, reasons = services.apply_to_job(students[username], job)
            if application is None:
                raise RuntimeError(f"Seed data error: {username} -> {title}: {reasons}")
            recruiter = recruiters[job.company.name]
            for status in path:
                services.change_status(application, status, recruiter)

        self.stdout.write(self.style.SUCCESS(
            f"Seeded {User.objects.count()} users, {Company.objects.count()} companies, "
            f"{JobPosting.objects.count()} postings, {Application.objects.count()} applications, "
            f"{AdminActionLog.objects.count()} audit log entries."))
        self.stdout.write(f"All demo accounts use the password: {PASSWORD}")
        self.stdout.write("  Admin:     admin / admin2")
        self.stdout.write("  Recruiter: recruiter (Nimbus, approved), recruiter2 (Quantix, approved), "
                          "recruiter3 (Voltline, pending)")
        self.stdout.write("  Student:   student (CSE, 8.70), student2 (ECE, 7.20), student3 (MECH, 6.40), "
                          "... student8")

    def _user(self, username, first, last, role, staff=False):
        user = User(username=username, first_name=first, last_name=last, role=role,
                    email=f"{username}@example.com", is_staff=staff)
        user.set_password(PASSWORD)
        user.save()
        return user
