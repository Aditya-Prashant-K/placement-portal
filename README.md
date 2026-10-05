# Campus Placement & Internship Portal

A role-based recruitment platform modelled on a college placement cell. It has three separate portals with enforced permission boundaries:

| Role | What they can do |
|---|---|
| **Student applicant** | Keep a profile (branch, CGPA, graduation year, resume link), browse approved openings, see eligibility before applying, apply, and track every application on a status timeline that updates live |
| **Company recruiter** | Register a company, publish postings with eligibility criteria (minimum CGPA, allowed departments, deadline), review candidate profiles, and move applicants through the hiring pipeline one at a time or in batches |
| **Placement cell admin** | Approve or reject newly registered companies and job postings before students can see them. Every decision goes into an audit log with a timestamp and the reviewer's ID |

Built with **Django 5 + SQLite + Bootstrap 5** (bundled locally, so it works offline). It needs no external services: clone it, install, seed, run.

---

## Quick start

Requires **Python 3.10+**.

```bash
git clone https://github.com/<your-username>/placement-portal.git
cd placement-portal

python -m venv venv
# Windows:      venv\Scripts\activate
# macOS/Linux:  source venv/bin/activate

pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo          # sample database population
python manage.py runserver
```

Open **http://127.0.0.1:8000** and log in with any account below.

### Sample data commands

| Command | Effect |
|---|---|
| `python manage.py seed_demo` | Creates demo users, companies, postings, applications and audit log entries. If the data already exists, it does nothing |
| `python manage.py seed_demo --reset` | Wipes all portal data and seeds again from scratch |
| `python manage.py test` | Runs the 29 automated tests |
| `python manage.py createsuperuser` | Creates your own admin. Superusers automatically get the Placement Cell Admin role |

---

## Mock login credentials

**Every demo account uses the password `Demo@1234`.**

| Role | Username | Notes |
|---|---|---|
| Admin | `admin` | Placement cell admin (Priya Raman) |
| Admin | `admin2` | Second admin, so the audit log shows different reviewer IDs |
| Recruiter | `recruiter` | Nimbus Cloud Systems (**approved**) with 2 live postings and applicants at every pipeline stage |
| Recruiter | `recruiter2` | Quantix Analytics (**approved**). Has 1 posting pending and 1 rejected |
| Recruiter | `recruiter3` | Voltline Motors (**pending approval**). Shows the waiting state |
| Student | `student` | CSE, CGPA 8.70. Has applications in Interview and Shortlisted |
| Student | `student2` | ECE, CGPA 7.20. Not eligible for the SDE role (branch and CGPA) |
| Student | `student3` | MECH, CGPA 6.40. **Use this one to see eligibility gating**: blocked from most postings |
| Student | `student4` | IT, CGPA 9.10. Has an **offer** |
| Student | `student5` to `student8` | Assorted branches and CGPAs |

### A 3-minute demo walkthrough

1. **Eligibility gating:** log in as `student3`, open *Software Development Engineer* and click **Try to apply anyway**. The server refuses and explains why (CGPA 6.40 < 8.00, MECH not in CSE/IT).
2. **Batch updates:** log in as `recruiter`, open **Applicants** for *Cloud Support Intern*, tick all and move them to *Under review*. Valid moves apply. Invalid ones (already Rejected) are skipped and reported.
3. **Live tracking:** keep `student2`'s *My applications* page open in another browser or a private window. It picks up the recruiter's change within 10 seconds without a reload.
4. **Approval + audit:** log in as `admin`, open **Approval queue**, approve *Voltline Motors* or reject a posting (a reason is required), then open **Audit log**.

---

## How the requirements are met

### Three role workflows with permission boundaries
- A custom `User` model has a `role` field (`STUDENT` / `RECRUITER` / `ADMIN`).
- Every view is wrapped in `@role_required(...)` ([`portal/decorators.py`](portal/decorators.py)). The wrong role gets **403** and anonymous users are redirected to login.
- **Object-level checks:** recruiters can only query their own company's postings and applications (`company__owner=request.user`). Students can only see their own applications. Guessing another ID in the URL returns 404.
- Public registration offers only Student or Recruiter. Admins can't be self-created.

### Server-side eligibility gating
- [`services.check_eligibility()`](portal/services.py) is the **single source of truth**. It returns a list of reasons: CGPA below the minimum, branch not allowed, deadline passed, or profile incomplete.
- [`services.apply_to_job()`](portal/services.py) calls it **before** creating an application. A crafted POST that bypasses the UI is still blocked, and a test proves this (`test_low_cgpa_is_blocked_on_server_with_notice`).
- The job list and detail pages use the same function to show "Eligible / Not eligible" badges, so the UI can't disagree with the backend.
- A database `UniqueConstraint` prevents duplicate applications.

### Approval before visibility
- Companies and postings start as `PENDING`. Students only see postings where **both the posting and its company** are `APPROVED` (`JobPosting.objects.visible()`).
- When a recruiter edits an already reviewed posting, it goes back to `PENDING`, so approved criteria can't be changed silently.

### Application tracking pipeline
- Statuses follow a defined state machine: `Applied → Under review → Shortlisted → Interview → Offered`. `Rejected` is allowed from any non-final state, and `Offered` and `Rejected` are final.
- Every change writes an `ApplicationEvent`, which renders as a timeline on separate application pages.
- **Single** transitions use per-row dropdowns that only offer valid next states. **Batch** transitions use checkboxes plus one action. Invalid moves are skipped and counted rather than forced.
- **Real-time:** the student's pages poll a small JSON endpoint (`/student/applications/status.json`) every 10 seconds and update the badges in place.

### Administrative action logs
- `AdminActionLog` stores the **reviewer ID** (FK to the admin), the action, the target type and ID, a snapshot of the target's name, the note and a **timestamp**.
- The log is written in the same database transaction as the status change, so neither can happen without the other.
- It's read-only everywhere, including Django's built-in admin. Admins with log entries can't be deleted (`on_delete=PROTECT`).
- Rejections require a reason, and the recruiter sees it.

---

## Project structure

```
config/                 Django settings and root URLs
portal/
  models.py             User, StudentProfile, Company, JobPosting, Application, ApplicationEvent, AdminActionLog
  services.py           Business rules: eligibility, pipeline transitions, admin review + audit logging
  decorators.py         role_required permission boundary
  forms.py              Forms (Bootstrap classes applied automatically)
  views_public.py       Home, register, role-based dashboard redirect
  views_student.py      Student portal
  views_recruiter.py    Recruiter portal
  views_admin.py        Placement cell admin portal
  management/commands/seed_demo.py   Sample data
  templates/portal/     One folder per portal
  tests.py              29 tests: gating, permissions, pipeline, audit log, page smoke tests
```

### URL map

| Area | URLs |
|---|---|
| Public | `/`, `/login/`, `/register/` |
| Student | `/student/`, `/student/profile/`, `/student/jobs/`, `/student/jobs/<id>/`, `/student/applications/`, `/student/applications/<id>/` |
| Recruiter | `/recruiter/`, `/recruiter/company/`, `/recruiter/jobs/new/`, `/recruiter/jobs/<id>/edit/`, `/recruiter/jobs/<id>/applicants/`, `/recruiter/applications/<id>/` |
| Admin | `/admin-portal/`, `/admin-portal/queue/`, `/admin-portal/companies/<id>/`, `/admin-portal/jobs/<id>/`, `/admin-portal/audit-log/` |

`/django-admin/` is Django's raw database inspector, for development only. The placement cell's real portal is `/admin-portal/`.

---

## Trade-offs and what I'd improve

- **Polling instead of WebSockets** for live status. With 10-second polling there's nothing extra to deploy, and it's adequate at campus scale. Django Channels would make it push-based.
- **SQLite** keeps setup to one command. For production I'd use PostgreSQL (for example on Amazon RDS) and deploy to AWS Elastic Beanstalk or EC2, with environment variables for `DJANGO_SECRET_KEY` and `DJANGO_DEBUG=0`.
- **Resume as a link** rather than an upload, as the spec allows. Next step would be S3 uploads with pre-signed URLs.
- **Email notifications** on status changes and approvals (Amazon SES) aren't implemented.
- **Recruiter verification** is manual through the admin queue. A real system would verify company email domains.
