from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import and_
from .. import models, schemas, database, auth
import logging
from datetime import datetime, timezone
from .notifications import create_notification
from .activity import log_activity



router = APIRouter(
    prefix="/groups",
    tags=["Settlements"]
)

logger = logging.getLogger(__name__)


# ==================== CREATE SETTLEMENT ====================
@router.post("/{group_id}/settlements", response_model=schemas.SettlementOut, status_code=status.HTTP_201_CREATED)
def create_settlement(
    group_id: int,
    settlement_data: schemas.SettlementCreate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """
    Create a settlement (payment) record.
    Only the debtor (current user) can initiate a settlement.
    """
    # Verify group exists
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group not found"
        )

    # Verify current user is member of group
    member = db.query(models.GroupMember).filter(
        and_(
            models.GroupMember.group_id == group_id,
            models.GroupMember.user_id == current_user.id
        )
    ).first()
    
    if not member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this group"
        )
    
    # Verify recipient is member of group
    recipient_member = db.query(models.GroupMember).filter(
        and_(
            models.GroupMember.group_id == group_id,
            models.GroupMember.user_id == settlement_data.to_user_id
        )
    ).first()
    
    if not recipient_member:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Recipient is not a member of this group"
        )
    
    # ==================== BALANCE VALIDATION ====================

    balances_data = {}

    expenses = db.query(models.GroupExpense).filter(
        models.GroupExpense.group_id == group_id
    ).all()

    for expense in expenses:
        paid_by = expense.paid_by_id

        splits = db.query(models.Split).filter(
            models.Split.group_expense_id == expense.id
        ).all()

        for split in splits:
            balances_data.setdefault(split.user_id, 0.0)
            balances_data.setdefault(paid_by, 0.0)

            balances_data[split.user_id] -= float(split.amount)
            balances_data[paid_by] += float(split.amount)

    # Adjust for confirmed settlements
    confirmed = db.query(models.Settlement).filter(
        and_(
            models.Settlement.group_id == group_id,
            models.Settlement.status == "confirmed"
        )
    ).all()

    for s in confirmed:
        balances_data[s.from_user_id] = (
            balances_data.get(s.from_user_id, 0)
            + float(s.amount)
        )

        balances_data[s.to_user_id] = (
            balances_data.get(s.to_user_id, 0)
            - float(s.amount)
        )

    # Current user balance
    my_balance = balances_data.get(
        current_user.id,
        0.0
    )

    recipient_balance = balances_data.get(
        settlement_data.to_user_id,
        0.0
    )

    # Max amount current user owes
    max_owed = round(
        -my_balance if my_balance < 0 else 0,
        2
    )

    if settlement_data.amount <= 0:
        raise HTTPException(
            status_code=400,
            detail="Amount must be greater than 0"
        )

    if max_owed > 0 and settlement_data.amount > max_owed:
        raise HTTPException(
            status_code=400,
            detail=(
                f"You can only settle up to ₹{max_owed}. "
                f"That's what you owe."
            )
        )

    # Verify both users have valid UPI
    from_user = db.query(models.User).filter(models.User.id == current_user.id).first()
    to_user = db.query(models.User).filter(models.User.id == settlement_data.to_user_id).first()

    if not from_user.upi_id or not from_user.upi_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Your UPI is not set up or verified"
        )
    
    if not to_user.upi_id or not to_user.upi_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Recipient's UPI is not set up or verified"
        )

    # Create settlement
    new_settlement = models.Settlement(
        group_id=group_id,
        from_user_id=current_user.id,
        to_user_id=settlement_data.to_user_id,
        amount=round(settlement_data.amount, 2),
        proof_url=settlement_data.proof_url,
        status="pending"
    )
    
    db.add(new_settlement)
    db.commit()
    db.refresh(new_settlement)

    logger.info(f"Settlement created: {current_user.id} -> {settlement_data.to_user_id}, Amount: {new_settlement.amount}")

    return schemas.SettlementOut.from_orm(new_settlement)


# ==================== GET SETTLEMENTS FOR GROUP ====================
@router.get("/{group_id}/settlements", response_model=list[schemas.SettlementOut])
def get_group_settlements(
    group_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """
    Get all settlements in a group (members only).
    """
    # Verify membership
    member = db.query(models.GroupMember).filter(
        and_(
            models.GroupMember.group_id == group_id,
            models.GroupMember.user_id == current_user.id
        )
    ).first()
    
    if not member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this group"
        )

    settlements = db.query(models.Settlement).filter(
        models.Settlement.group_id == group_id
    ).order_by(models.Settlement.created_at.desc()).all()

    return [schemas.SettlementOut.from_orm(s) for s in settlements]


# ==================== GET SETTLEMENT BY ID ====================
@router.get("/{group_id}/settlements/{settlement_id}", response_model=schemas.SettlementOut)
def get_settlement(
    group_id: int,
    settlement_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """
    Get a specific settlement.
    """
    settlement = db.query(models.Settlement).filter(
        and_(
            models.Settlement.id == settlement_id,
            models.Settlement.group_id == group_id
        )
    ).first()

    if not settlement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Settlement not found"
        )

    # Verify user is involved or member
    if settlement.from_user_id != current_user.id and settlement.to_user_id != current_user.id:
        member = db.query(models.GroupMember).filter(
            and_(
                models.GroupMember.group_id == group_id,
                models.GroupMember.user_id == current_user.id
            )
        ).first()
        
        if not member:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )

    return schemas.SettlementOut.from_orm(settlement)


# ==================== CONFIRM SETTLEMENT ====================
@router.post("/{group_id}/settlements/{settlement_id}/confirm", status_code=status.HTTP_200_OK)
def confirm_settlement(
    group_id: int,
    settlement_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """
    Confirm a settlement (receiver only).
    """
    settlement = db.query(models.Settlement).filter(
        and_(
            models.Settlement.id == settlement_id,
            models.Settlement.group_id == group_id
        )
    ).first()

    if not settlement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Settlement not found"
        )

    # Only receiver can confirm
    if settlement.to_user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the receiver can confirm this settlement"
        )

    # Check if already processed
    if settlement.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Settlement is already {settlement.status}"
        )

    settlement.status = "confirmed"
    settlement.confirmed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(settlement)
    
    create_notification(
        db,
        settlement.from_user_id,
        "Settlement confirmed",
        f"Your payment of ₹{settlement.amount} was confirmed",
        "success"
    )

    log_activity(
        db,
        current_user.id,
        "confirm_settlement",
        f"Confirmed ₹{settlement.amount} settlement",
        "settlement",
        settlement_id
    )

    logger.info(f"Settlement confirmed: {settlement_id}")

    return {
        "message": "Settlement confirmed successfully",
        "settlement": schemas.SettlementOut.from_orm(settlement)
    }


# ==================== REJECT SETTLEMENT ====================
@router.post("/{group_id}/settlements/{settlement_id}/reject", status_code=status.HTTP_200_OK)
def reject_settlement(
    group_id: int,
    settlement_id: int,
    payload: schemas.SettlementRejectRequest,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """
    Reject a settlement (receiver only).
    """
    settlement = db.query(models.Settlement).filter(
        and_(
            models.Settlement.id == settlement_id,
            models.Settlement.group_id == group_id
        )
    ).first()

    if not settlement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Settlement not found"
        )

    # Only receiver can reject
    if settlement.to_user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the receiver can reject this settlement"
        )

    # Check if already processed
    if settlement.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Settlement is already {settlement.status}"
        )

    settlement.status = "rejected"
    settlement.rejected_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(settlement)

    logger.info(f"Settlement rejected: {settlement_id}, Reason: {payload.reason}")

    return {
        "message": "Settlement rejected successfully",
        "settlement": schemas.SettlementOut.from_orm(settlement)
    }


# ==================== CANCEL SETTLEMENT ====================
@router.post("/{group_id}/settlements/{settlement_id}/cancel", status_code=status.HTTP_200_OK)
def cancel_settlement(
    group_id: int,
    settlement_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """
    Cancel a pending settlement (sender only).
    """
    settlement = db.query(models.Settlement).filter(
        and_(
            models.Settlement.id == settlement_id,
            models.Settlement.group_id == group_id
        )
    ).first()

    if not settlement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Settlement not found"
        )

    # Only sender can cancel
    if settlement.from_user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the sender can cancel this settlement"
        )

    # Can only cancel pending
    if settlement.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel a {settlement.status} settlement"
        )

    db.delete(settlement)
    db.commit()

    logger.info(f"Settlement cancelled: {settlement_id}")

    return {"message": "Settlement cancelled successfully"}


# ==================== GET PENDING SETTLEMENTS FOR USER ====================
@router.get("/{group_id}/settlements/pending/my-settlements")
def get_my_pending_settlements(
    group_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """
    Get pending settlements where user is involved (as sender or receiver).
    """
    # Verify membership
    member = db.query(models.GroupMember).filter(
        and_(
            models.GroupMember.group_id == group_id,
            models.GroupMember.user_id == current_user.id
        )
    ).first()
    
    if not member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this group"
        )

    settlements = db.query(models.Settlement).filter(
        and_(
            models.Settlement.group_id == group_id,
            models.Settlement.status == "pending",
            (models.Settlement.from_user_id == current_user.id) | 
            (models.Settlement.to_user_id == current_user.id)
        )
    ).order_by(models.Settlement.created_at.desc()).all()

    return {
        "pending_settlements": [schemas.SettlementOut.from_orm(s) for s in settlements]
    }