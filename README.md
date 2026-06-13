# Trackr — Full-Stack Expense Management App


Trackr is a production-grade, full-stack expense management application built with **FastAPI**, **React 19**, **PostgreSQL**, and **Redis**. It supports personal expense tracking, group bill splitting, UPI-based settlements, visual analytics, and real-time notifications.

**Live:** [trackr.vercel.app](https://trackr-frontend-one.vercel.app/) — Backend on Railway, Frontend on Vercel

---

## Features

- JWT authentication with Argon2 password hashing
- Personal expense tracking with 7 categories and monthly budget limits
- Email alerts when monthly limit is exceeded
- Group expense splitting — equal or custom amounts per member
- UPI settlement deeplinks (Google Pay, PhonePe, any UPI app)
- Balance calculation with greedy debt simplification algorithm
- In-app notifications and activity audit log
- CSV and PDF export with ReportLab
- OTP-based email change flow backed by Redis
- Dark mode with localStorage persistence
- Fully responsive — mobile and desktop

---

## System Design
┌─────────────────┐     HTTPS      ┌──────────────────┐

│  React Frontend │ ─────────────▶ │  FastAPI Backend │

│  (Vercel)       │                │  (Railway)       │

└─────────────────┘                └────────┬─────────┘

│

┌─────────────┼─────────────┐

▼             ▼             ▼

┌──────────┐ ┌──────────┐ ┌──────────┐

│PostgreSQL│ │  Redis   │ │  Resend  │

│ (Railway)│ │(OTP/Cache)│ │ (Email)│

└──────────┘ └──────────┘ └──────────┘

**Redis is used for:**
- OTP storage with TTL for email-change verification (replaces in-memory storage)
- Future: session caching, notification unread counts

**Why not Kafka?** Trackr is a monolith. Kafka suits microservices with high-throughput event streams. Adding it here would be over-engineering. Planned for v2 if the architecture splits.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 19, Vite, React Router v7, Tailwind CSS v4, Recharts |
| Backend | FastAPI, SQLAlchemy, Alembic, Pydantic |
| Auth | JWT, Argon2 password hashing |
| Database | PostgreSQL 15 |
| Cache | Redis 7 |
| Email | Resend API |
| Export | ReportLab (PDF), Python csv (CSV) |
| Deployment | Railway (backend + DB), Vercel (frontend) |
| Container | Docker, Docker Compose |

---

## Getting Started

### Prerequisites
- Docker and Docker Compose
- Python 3.11+
- Node.js 18+

### Backend — Local Development

```bash
git clone  https://github.com/Charan152315/trackr-backend.git
cd trackr-backend

# Copy env file
cp .env.example .env

# Run with Docker
docker-compose -f docker-compose-dev.yml up --build

# Or without Docker
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

### Frontend — Local Development

```bash
git clone  https://github.com/Charan152315/trackr-frontend.git
cd trackr-frontend
npm install
cp .env.example .env        # set VITE_API_URL=http://localhost:8000
npm run dev
```

### Environment Variables

Backend `.env`:
```env
DATABASE_HOSTNAME=localhost
DATABASE_PORT=5432
DATABASE_NAME=trackr
DATABASE_USERNAME=postgres
DATABASE_PASSWORD=yourpassword
SECRET_KEY=your-secret-key-min-32-chars
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REDIS_URL=redis://localhost:6379
RESEND_API_KEY=re_your_key
SMTP_FROM_NAME=Trackr
SMTP_FROM_EMAIL=noreply@yourdomain.com
FRONTEND_URL=http://localhost:5173
```

---

## API Reference

### Auth
POST /auth/register     — Create account

POST /auth/login        — Get JWT token

POST /auth/forgot-password

POST /auth/reset-password

### Expenses
GET    /expenses/              — List all personal expenses

POST   /expenses/              — Create expense

PUT    /expenses/{id}          — Update expense

DELETE /expenses/{id}          — Delete expense

GET    /expenses/summary/monthly    — Monthly summary with group share

GET    /expenses/breakdown/categories

GET    /expenses/export?format=csv|pdf

### Groups
GET    /groups/                — List user's groups

POST   /groups/                — Create group

DELETE /groups/{id}            — Delete group

POST   /groups/{id}/add_member

DELETE /groups/{id}/remove_member

GET    /groups/{id}/members

POST   /groups/{id}/expenses   — Add group expense

GET    /groups/{id}/expenses

DELETE /groups/{id}/expenses/{expense_id}

GET    /groups/{id}/balances

GET    /groups/{id}/summary

POST   /groups/{id}/settlements

POST   /groups/{id}/settlements/{id}/confirm

POST   /groups/{id}/settlements/{id}/reject

### Users
GET    /users/me               — Current user profile

PUT    /users/upi              — Update UPI ID

POST   /users/upi/verify       — Verify UPI

PUT    /users/set_limit        — Set monthly budget

POST   /users/change-email/request

POST   /users/change-email/confirm

### Notifications & Activity
GET    /notifications/

POST   /notifications/{id}/read

POST   /notifications/read-all

DELETE /notifications/clear

GET    /activity/

---

## Project Structure
app/

├── main.py

├── models.py

├── schemas.py

├── database.py

├── auth.py

├── config.py

├── utils.py

├── email.py

├── redis_client.py

└── routes/

├── auth.py

├── expense_routes.py

├── group_routes.py

├── settlements.py

├── user_routes.py

├── notifications.py

└── activity.py

---

## Deployment

**Backend → Railway**
1. Connect GitHub repo to Railway
2. Add PostgreSQL and Redis services
3. Set all environment variables
4. Railway auto-deploys on push

**Frontend → Vercel**
1. Connect GitHub repo to Vercel
2. Set `VITE_API_URL` to Railway backend URL
3. Add `vercel.json` for SPA routing

---

## Author

**Charan Sri Chintamaneni**
Student @ NIT Raipur — Backend + DevOps

[LinkedIn](https://linkedin.com/in/charansri-chintamaneni) · [GitHub](https://github.com/Charan152315)

---

> Built as a full-stack SaaS project demonstrating FastAPI, React, PostgreSQL, Redis, Docker, and production deployment.