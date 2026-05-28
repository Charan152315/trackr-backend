from fastapi import APIRouter,Depends,HTTPException,status
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordRequestForm
from .. import models,schemas,utils,database,auth
from secrets import token_urlsafe
from .. import email as email_utils

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)

@router.post("/login", response_model=schemas.Token)
def login(user_credentials:OAuth2PasswordRequestForm=Depends(),db:Session=Depends(database.get_db)):
   
    user=db.query(models.User).filter(models.User.username==user_credentials.username).first()

    if not user:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,detail="Invalid Credentials")

    if not utils.verify_password(user_credentials.password,user.password):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,detail="Invalid Credentials")

    access_token=auth.create_access_token(data={"user_id":user.id,"username": user.username})

    return {"access_token":access_token,"token_type":"bearer"}

@router.post("/forgot-password", response_model=schemas.MessageResponse)
def forgot_password(request: schemas.ForgotPasswordRequest, db: Session = Depends(database.get_db)):
    """Send password reset email"""
    user = db.query(models.User).filter(models.User.email == request.email).first()
    
    # Always return success message for security (don't reveal if email exists)
    if not user:
        return {"message": "If the email exists, a password reset link has been sent."}
    
    # Generate reset token
    reset_token = auth.create_reset_token(user.email)
    
    # Send email
    email_sent = email_utils.send_password_reset_email(user.email, reset_token)
    
    if not email_sent:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send email. Please try again later."
        )
    
    return {"message": "If the email exists, a password reset link has been sent."}

@router.post("/reset-password", response_model=schemas.MessageResponse)
def reset_password(request: schemas.ResetPasswordRequest, db: Session = Depends(database.get_db)):
    """Reset password using token"""
    # Verify token
    email = auth.verify_reset_token(request.token)
    
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token"
        )
    
    # Find user
    user = db.query(models.User).filter(models.User.email == email).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Update password
    user.password = utils.hash_password(request.new_password)
    db.commit()
    
    return {"message": "Password has been reset successfully"}

@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=schemas.UserOut)
def register(user: schemas.UserCreate, db: Session = Depends(database.get_db)):
    existing_email = db.query(models.User).filter(
        models.User.email == user.email
    ).first()
    if existing_email:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    existing_username = db.query(models.User).filter(
        models.User.username == user.username
    ).first()
    if existing_username:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already taken")

    new_user = models.User(
        username=user.username,
        email=user.email,
        password=utils.hash_password(user.password),
        monthly_limit=user.monthly_limit
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user