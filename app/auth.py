from fastapi import Depends,status,HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError,jwt
from sqlalchemy.orm import Session
from datetime import datetime,timedelta,timezone
from . import models,database,schemas
from .config import settings
oauth2_scheme=OAuth2PasswordBearer(tokenUrl="login")

SECRET_KEY= settings.secret_key
ALGORITHM= settings.algorithm
ACCESS_TOKEN_EXPIRE_MINUTES= settings.access_token_expire_minutes

def create_access_token(data:dict):
    to_encode=data.copy()
    expire=datetime.now(timezone.utc)+timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode["exp"]=expire  
    encoded_jwt = jwt.encode(to_encode,SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_access_token(token:str,credentials_exception):
    try:
        payload=jwt.decode(token,SECRET_KEY,algorithms=[ALGORITHM])
        user_id:str=payload.get("user_id")
        username: str = payload.get("username")
        if user_id is None or username is None:
         raise credentials_exception
        return schemas.TokenData(id=user_id,username=username)
    except JWTError:
        raise credentials_exception

def get_current_user(token:str = Depends(oauth2_scheme),db:Session=Depends(database.get_db)):
    credentials_exception=HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
        detail=f"Could not validate credentials",headers={"WWW-Authenticate": "Bearer"},)

    token_data=verify_access_token(token,credentials_exception)
    user=db.query(models.User).filter(models.User.id==int(token_data.id)).first()

    if not user:
        raise credentials_exception

    return user

def create_reset_token(email: str):
    """Create a password reset token"""
    to_encode = {
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=30)  # 30 minutes expiry
    }
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_reset_token(token: str):
    """Verify password reset token and return email"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("email")
        if email is None:
            return None
        return email
    except JWTError:
        return None