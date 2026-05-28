from pydantic import BaseModel, EmailStr, Field, validator
from typing import List, Optional
from datetime import datetime
import re

# ==================== USER SCHEMAS ====================
class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=6)
    monthly_limit: Optional[float] = Field(0, ge=0)


    @validator('username')
    def username_alphanumeric(cls, v):
        assert v.isalnum(), 'Username must be alphanumeric'
        return v


class UserOut(BaseModel):
    id: int
    username: str
    email: EmailStr
    created_at: datetime
    monthly_limit: float

    class Config:
        from_attributes = True


class UserWithUpi(BaseModel):
    id: int
    username: str
    email: str
    created_at: datetime
    monthly_limit: float
    upi_id: Optional[str] = None
    upi_verified: bool = False
    upi_verified_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ==================== UPI SCHEMAS ====================
class UpiUpdate(BaseModel):
    upi_id: str = Field(..., min_length=5, max_length=50)

    @validator('upi_id')
    def validate_upi_format(cls, v):
        if not re.match(r'^[a-zA-Z0-9._-]+@[a-zA-Z]{3,}$', v):
            raise ValueError('Invalid UPI ID format')
        return v


class UpiStatus(BaseModel):
    user_id: int
    username: str
    upi_id: Optional[str] = None
    upi_verified: bool
    upi_verified_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class VerifyUPIRequest(BaseModel):
    upi_id: str = Field(..., min_length=5, max_length=50)
    otp: Optional[str] = None

    @validator('upi_id')
    def validate_upi_format(cls, v):
        if not re.match(r'^[a-zA-Z0-9._-]+@[a-zA-Z]{3,}$', v):
            raise ValueError('Invalid UPI ID format')
        return v


# ==================== TOKEN SCHEMAS ====================
class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    id: Optional[int] = None
    username: Optional[str] = None

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

class MessageResponse(BaseModel):
    message: str

# ==================== EXPENSE SCHEMAS ====================
class ExpenseBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=100)
    amount: float = Field(..., gt=0)
    category: str = Field(..., min_length=1, max_length=50)


class ExpenseCreate(ExpenseBase):
    pass


class ExpenseUpdate(ExpenseBase):
    pass


class ExpenseOut(ExpenseBase):
    id: int
    owner_id: int
    created_at: datetime

    class Config:
        from_attributes = True


# ==================== GROUP SCHEMAS ====================
class GroupCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class GroupOut(BaseModel):
    id: int
    name: str
    owner_id: int
    owner_username: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class AddMemberRequest(BaseModel):
    username: str = Field(..., min_length=1)


class RemoveMemberRequest(BaseModel):
    username: str = Field(..., min_length=1)


class GroupMemberOut(BaseModel):
    user_id: int
    username: str
    role: str
    upi_id: Optional[str] = None
    upi_verified: bool = False
    joined_at: datetime

    class Config:
        from_attributes = True


# ==================== SPLIT & GROUP EXPENSE SCHEMAS ====================
class SplitInput(BaseModel):
    user_id: int = Field(..., gt=0)
    amount: float = Field(..., gt=0)


class SplitOut(BaseModel):
    user_id: int
    username: str
    amount: float

    class Config:
        from_attributes = True


class GroupExpenseCreate(BaseModel):
    group_id: int = Field(..., gt=0)
    paid_by_id: int = Field(..., gt=0)
    amount: float = Field(..., gt=0)
    description: str = Field(..., min_length=1, max_length=255)
    even_split: bool = True
    custom_splits: Optional[List[SplitInput]] = None

    @validator('custom_splits')
    def validate_splits(cls, v, values):
        if not values.get('even_split') and not v:
            raise ValueError('Custom splits required when even_split is False')
        if v:
            total = sum(split.amount for split in v)
            if round(total, 2) != round(values.get('amount', 0), 2):
                raise ValueError('Split amounts must sum to total expense amount')
        return v


class GroupExpenseOut(BaseModel):
    id: int
    group_id: int
    paid_by_id: int
    amount: float
    description: str
    splits: List[SplitOut]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class GroupExpenseResponse(BaseModel):
    id: int
    group_id: int
    amount: float
    description: str
    paid_by: dict
    splits: List[dict]
    created_at: datetime


# ==================== SETTLEMENT SCHEMAS ====================
class SettlementCreate(BaseModel):
    to_user_id: int = Field(..., gt=0)
    amount: float = Field(..., gt=0)
    proof_url: Optional[str] = None

    @validator('amount')
    def validate_amount(cls, v):
        if v <= 0:
            raise ValueError('Amount must be greater than 0')
        return round(v, 2)


class SettlementOut(BaseModel):
    id: int
    group_id: int
    from_user_id: int
    to_user_id: int
    amount: float
    proof_url: Optional[str] = None
    status: str
    created_at: datetime
    confirmed_at: Optional[datetime] = None
    rejected_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SettlementConfirmRequest(BaseModel):
    pass


class SettlementRejectRequest(BaseModel):
    reason: Optional[str] = None


# ==================== BALANCE SCHEMAS ====================
class BalanceTransfer(BaseModel):
    from_user: dict
    to_user: dict
    amount: float


class GroupBalances(BaseModel):
    group_id: int
    balances: List[BalanceTransfer]


# ==================== API RESPONSE WRAPPER ====================
class ApiResponse(BaseModel):
    success: bool
    message: str
    data: Optional[dict] = None
    error: Optional[str] = None

    class Config:
        from_attributes = True