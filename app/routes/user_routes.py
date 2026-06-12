from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from .. import schemas, models, utils, database, auth, email as email_utils
from ..auth import create_reset_token
from ..config import settings
import random

from app.redis_client import redis_client
# we use redis for this _otp_store = {}  # {user_id: {otp, new_email, expires}}

import logging
import traceback

router = APIRouter(
    prefix="/users",
    tags=["Users"]
)

logger = logging.getLogger(__name__)


# ==================== CREATE USER ====================
@router.post("/", status_code=status.HTTP_201_CREATED, response_model=schemas.UserOut)
def create_user(user: schemas.UserCreate, db: Session = Depends(database.get_db)):
    """Create a new user account."""
    try:
        # Check if email exists
        existing_email = db.query(models.User).filter(
            models.User.email == user.email
        ).first()
        
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_406_NOT_ACCEPTABLE,
                detail="Email already registered"
            )

        # Check if username exists
        existing_username = db.query(models.User).filter(
            models.User.username == user.username
        ).first()
        
        if existing_username:
            raise HTTPException(
                status_code=status.HTTP_406_NOT_ACCEPTABLE,
                detail="Username already taken"
            )

        # Hash password
        hashed_password = utils.hash_password(user.password)
        
        # Create new user
        new_user = models.User(
            username=user.username,
            email=user.email,
            password=hashed_password,
            monthly_limit=user.monthly_limit
        )
        
        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        logger.info(f"New user created: {new_user.email}")
        return new_user

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating user: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


# ==================== GET ALL USERS ====================
@router.get("/search", response_model=schemas.UserOut)
def search_user(
    username: str,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    user = db.query(models.User).filter(
        models.User.username == username
    ).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return user


# ==================== GET CURRENT USER ====================
@router.get("/me", response_model=schemas.UserWithUpi)
def get_current_user(
    db: Session = Depends(database.get_db),
    user: models.User = Depends(auth.get_current_user)
):
    """Get current user's profile with UPI info."""
    return user


# ==================== SET MONTHLY LIMIT ====================
@router.put("/set_limit", status_code=status.HTTP_200_OK)
def set_monthly_limit(
    limit: float,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Set monthly expense limit."""
    if limit < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Monthly limit must be non-negative"
        )

    current_user.monthly_limit = limit
    db.commit()
    db.refresh(current_user)

    return {
        "message": f"Monthly limit set to {limit}",
        "monthly_limit": current_user.monthly_limit
    }


# ==================== UPDATE UPI ====================
@router.put("/upi", response_model=schemas.UpiStatus, status_code=status.HTTP_200_OK)
def update_upi(
    upi_data: schemas.UpiUpdate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """
    Update UPI ID (marks as unverified).
    Must call verify endpoint separately.
    """

    # Check if UPI already exists for another user
    existing_upi = db.query(models.User).filter(
        models.User.upi_id == upi_data.upi_id,
        models.User.id != current_user.id
    ).first()
    
    if existing_upi:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This UPI is already registered by another user"
        )

    # Update UPI and reset verification
    current_user.upi_id = upi_data.upi_id
    current_user.upi_verified = False
    current_user.upi_verified_at = None
    db.commit()
    db.refresh(current_user)

    logger.info(f"UPI updated for user: {current_user.id}")

    return schemas.UpiStatus(
        user_id=current_user.id,
        username=current_user.username,
        upi_id=current_user.upi_id,
        upi_verified=current_user.upi_verified,
        upi_verified_at=current_user.upi_verified_at
    )


# ==================== VERIFY UPI ====================
@router.post("/upi/verify", response_model=schemas.UpiStatus, status_code=status.HTTP_200_OK)
def verify_upi(
    payload: schemas.VerifyUPIRequest,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """
    Verify UPI ID.
    In production, this would validate OTP or call UPI service.
    For now, mock verification.
    """
    if not current_user.upi_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No UPI ID set. Please set UPI first."
        )

    if current_user.upi_id != payload.upi_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="UPI ID does not match the registered UPI"
        )

    # TODO: In production, verify OTP here
    # For now, we trust the user

    current_user.upi_verified = True
    current_user.upi_verified_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(current_user)

    logger.info(f"UPI verified for user: {current_user.id}")

    return schemas.UpiStatus(
        user_id=current_user.id,
        username=current_user.username,
        upi_id=current_user.upi_id,
        upi_verified=current_user.upi_verified,
        upi_verified_at=current_user.upi_verified_at
    )


# ==================== GET USER BY ID ====================
@router.get("/{user_id}", response_model=schemas.UserOut)
def get_user_by_id(
    user_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Get user profile by ID."""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    return user

# ==================== EMAIL CONFIRMATION ====================
@router.post("/change-email/request")
def request_email_change(
    payload: schemas.ForgotPasswordRequest,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    new_email = payload.email
    existing = db.query(models.User).filter(
        models.User.email == new_email,
        models.User.id != current_user.id
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already in use")

    otp = str(random.randint(100000, 999999))
    redis_client.setex(
        f"email_otp:{current_user.id}",
        600,
        f"{otp}:{new_email}"
    )

    from app.email import send_email
    try:
        send_email(
            new_email,
            "Your email change OTP — Trackr",
            f"""
            <div style="font-family:Arial;padding:20px;max-width:500px">
                <h2 style="color:#38bdf8">Verify your new email</h2>
                <p>Hi {current_user.username},</p>
                <p>Your OTP to confirm email change is:</p>
                <div style="font-size:2rem;font-weight:800;letter-spacing:0.3em;color:#0c1a2e;
                    background:#38bdf8;padding:16px 24px;border-radius:10px;
                    display:inline-block;margin:12px 0;">
                    {otp}
                </div>
                <p>This OTP expires in 10 minutes.</p>
                <p style="color:#6b7280;font-size:12px">If you didn't request this, ignore this email.</p>
            </div>
            """
        )
    except Exception as e:
        logger.error(f"Email OTP send failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to send OTP email")

    return {"message": f"OTP sent to {new_email}"}


@router.post("/change-email/confirm")
def confirm_email_change(
    payload: dict,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    otp_input = payload.get("otp")

    stored = redis_client.get(
        f"email_otp:{current_user.id}"
    )

    if not stored:
        raise HTTPException(
            status_code=400,
            detail="No OTP request found. Please request again."
        )

    stored_otp, new_email = stored.split(":", 1)

    if stored_otp != otp_input:
        raise HTTPException(
            status_code=400,
            detail="Incorrect OTP"
        )

    existing = db.query(models.User).filter(
        models.User.email == new_email,
        models.User.id != current_user.id
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail="Email already taken"
        )

    current_user.email = new_email
    db.commit()

    redis_client.delete(
        f"email_otp:{current_user.id}"
    )

    return {
        "message": "Email updated successfully"
    }