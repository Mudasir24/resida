# Apartment Management Platform

A multi-tenant apartment management platform built with Flask and PostgreSQL as part of the CS50x final project. Each apartment gets its own branded space at `/apartments/<slug>` with separate roles for admins and residents.

## Features

- **Multi-tenant** — each apartment is fully isolated under its own URL slug
- **Invite-only registration** — admin sends invite codes to residents via email; no open sign-ups
- **Dual roles** — admins manage the apartment; residents have a read/interact view
- **Payments & billing** — admin creates payments, bills are auto-generated per resident; residents submit proof of payment; admin confirms
- **Expense tracking** — log community expenses by category with receipt uploads and monthly filtering
- **Works & checkpoints** — track ongoing/planned maintenance works with progress checkpoints and photo uploads
- **Complaints board** — residents submit complaints with photos; admins update status and comment
- **Analytics dashboards** — dedicated dashboards for both admins (full insights) and residents (community view)

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Flask 3.0, Python |
| Database | PostgreSQL via psycopg v3 |
| File storage | Cloudinary |
| Auth | Session-based, Werkzeug password hashing |
| Email | SMTP (Gmail) |

## Setup

1. Clone the repo and create a virtual environment:

```bash
python -m venv .venv
.venv\Scripts\activate      # Windows
source .venv/bin/activate   # Mac/Linux
pip install -r requirements.txt
```

2. Create a `.env` file in the project root:

```env
SECRET_KEY=
DATABASE_URI=
CLOUDINARY_CLOUD_NAME=
CLOUDINARY_API_KEY=
CLOUDINARY_API_SECRET=
SMTP_USER=
SMTP_PASSWORD=
DEFAULT_APARTMENT_PHOTO=
FLASK_DEBUG=false
```

3. Run the app:

```bash
flask run
```
