from fastapi import FastAPI
from app.database import engine
from app import models
from app.models import Base
import os
from app.routes import auth,expense_routes,user_routes,group_routes
from fastapi.middleware.cors import CORSMiddleware
from app.routes import settlements
from app.routes import notifications, activity


#Base.metadata.create_all(bind=engine)

app=FastAPI(title="Expense Tracker API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173",
                   "https://trackr-frontend-one.vercel.app/",
                   "https://trackr-frontend-one.vercel.app",
                   ], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

app.include_router(notifications.router)
app.include_router(activity.router)
app.include_router(settlements.router)
app.include_router(auth.router)
app.include_router(expense_routes.router)
app.include_router(user_routes.router)
app.include_router(group_routes.router)


@app.get("/")
def root():
    return {"message": "Expense Tracker API running"}