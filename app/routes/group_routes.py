from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from .. import models, schemas, database, auth
import logging
from datetime import datetime,timezone
from .notifications import create_notification
from .activity import log_activity

router = APIRouter(
    prefix="/groups",
    tags=["Groups"]
)

logger = logging.getLogger(__name__)


# ==================== CREATE GROUP ====================
@router.post("/", response_model=schemas.GroupOut, status_code=status.HTTP_201_CREATED)
def create_group(
    group: schemas.GroupCreate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Create a new group and add creator as admin."""
    new_group = models.Group(name=group.name, owner_id=current_user.id)
    db.add(new_group)
    db.commit()
    db.refresh(new_group)

    # Add creator as admin member
    group_member = models.GroupMember(
        user_id=current_user.id,
        group_id=new_group.id,
        role="admin"
    )
    db.add(group_member)
    db.commit()

    return schemas.GroupOut(
        id=new_group.id,
        name=new_group.name,
        owner_id=new_group.owner_id,
        owner_username=current_user.username,
        created_at=new_group.created_at,
    )


# ==================== GET ALL GROUPS FOR USER ====================
@router.get("/", response_model=list[schemas.GroupOut])
def get_user_groups(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Get all groups the current user is a member of."""
    group_ids = db.query(models.GroupMember.group_id).filter(
        models.GroupMember.user_id == current_user.id
    ).subquery()

    groups = db.query(models.Group).filter(models.Group.id.in_(group_ids)).all()
    response = []

    for group in groups:
        owner = db.query(models.User).filter(models.User.id == group.owner_id).first()
        response.append(schemas.GroupOut(
            id=group.id,
            name=group.name,
            owner_id=group.owner_id,
            owner_username=owner.username if owner else None,
            created_at=group.created_at
        ))
    return response


# ==================== DELETE GROUP ====================
@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_group(
    group_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Delete group (owner only)."""
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    
    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group not found"
        )

    if group.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the group owner can delete this group"
        )

    # Delete all related data (cascade handled by DB)
    db.delete(group)
    db.commit()


# ==================== ADD MEMBER ====================
@router.post("/{group_id}/add_member", status_code=status.HTTP_201_CREATED)
def add_member(
    group_id: int,
    member_data: schemas.AddMemberRequest,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Send a group invite request to a user (admin only). User must accept."""
    admin_member = db.query(models.GroupMember).filter(
        and_(
            models.GroupMember.group_id == group_id,
            models.GroupMember.user_id == current_user.id,
            models.GroupMember.role == "admin"
        )
    ).first()
    if not admin_member:
        raise HTTPException(status_code=403, detail="Only admins can invite members")

    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    user_to_add = db.query(models.User).filter(models.User.username == member_data.username).first()
    if not user_to_add:
        raise HTTPException(status_code=404, detail="User not found")

    if user_to_add.id == current_user.id:
        raise HTTPException(status_code=400, detail="You can't invite yourself")

    existing = db.query(models.GroupMember).filter(
        and_(models.GroupMember.group_id == group_id, models.GroupMember.user_id == user_to_add.id)
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="User already in group")

    pending = db.query(models.GroupInviteRequest).filter(
        and_(
            models.GroupInviteRequest.group_id == group_id,
            models.GroupInviteRequest.invited_user_id == user_to_add.id,
            models.GroupInviteRequest.status == "pending"
        )
    ).first()
    if pending:
        raise HTTPException(status_code=400, detail="Invite already sent and pending")

    invite_req = models.GroupInviteRequest(
        group_id=group_id,
        invited_user_id=user_to_add.id,
        invited_by_id=current_user.id,
        status="pending"
    )
    db.add(invite_req)
    db.commit()
    db.refresh(invite_req)

    log_activity(db, current_user.id, "invite_member", f"Invited {user_to_add.username} to {group.name}", "group", group_id)

    return {"message": f"Invite sent to {member_data.username}"}

# ==================== REMOVE MEMBER ====================
@router.delete("/{group_id}/remove_member", status_code=status.HTTP_200_OK)
def remove_member(
    group_id: int,
    member_data: schemas.RemoveMemberRequest,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Remove member from group (admin only)."""
    # Check if current user is admin
    admin_member = db.query(models.GroupMember).filter(
        and_(
            models.GroupMember.group_id == group_id,
            models.GroupMember.user_id == current_user.id,
            models.GroupMember.role == "admin"
        )
    ).first()
    
    if not admin_member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can remove members"
        )

    # Find user to remove
    user_to_remove = db.query(models.User).filter(
        models.User.username == member_data.username
    ).first()
    
    if not user_to_remove:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Prevent admin from removing themselves
    if user_to_remove.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admins cannot remove themselves"
        )

    # Find and delete member
    member_entry = db.query(models.GroupMember).filter(
        and_(
            models.GroupMember.group_id == group_id,
            models.GroupMember.user_id == user_to_remove.id
        )
    ).first()
    
    if not member_entry:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User not in group"
        )

    db.delete(member_entry)
    db.commit()

    return {"message": f"{member_data.username} removed successfully"}


# ==================== LIST GROUP MEMBERS ====================
@router.get("/{group_id}/members", response_model=list[schemas.GroupMemberOut])
def list_group_members(
    group_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """List all members in a group (members only)."""
    # Verify user is member
    member_check = db.query(models.GroupMember).filter(
        and_(
            models.GroupMember.group_id == group_id,
            models.GroupMember.user_id == current_user.id
        )
    ).first()
    
    if not member_check:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this group"
        )

    # Fetch members with join
    members = db.query(models.GroupMember, models.User).join(
        models.User,
        models.GroupMember.user_id == models.User.id
    ).filter(
        models.GroupMember.group_id == group_id
    ).all()

    return [
        schemas.GroupMemberOut(
            user_id=user.id,
            username=user.username,
            role=member.role,
            upi_id=user.upi_id,
            upi_verified=user.upi_verified,
            joined_at=member.joined_at
        )
        for member, user in members
    ]


# ==================== GROUP EXPENSES - CREATE ====================
@router.post("/{group_id}/expenses", status_code=status.HTTP_201_CREATED)
def create_group_expense(
    group_id: int,
    expense: schemas.GroupExpenseCreate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Create group expense and split it."""
    # Verify group exists and user is member
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group not found"
        )

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

    # Create expense
    new_expense = models.GroupExpense(
        group_id=group_id,
        paid_by_id=expense.paid_by_id,
        amount=expense.amount,
        description=expense.description,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    db.add(new_expense)
    db.commit()
    db.refresh(new_expense)

    # Handle splits
    if expense.even_split:
        # Split equally among all members
        members = db.query(models.GroupMember).filter(
            models.GroupMember.group_id == group_id
        ).all()

        if not members:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No members in group"
            )

        share = round(expense.amount / len(members), 2)
        for group_member in members:
            split = models.Split(
                group_expense_id=new_expense.id,
                user_id=group_member.user_id,
                amount=share
            )
            db.add(split)
    else:
        # Custom splits
        if not expense.custom_splits:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Custom splits required"
            )

        for split_input in expense.custom_splits:
            split = models.Split(
                group_expense_id=new_expense.id,
                user_id=split_input.user_id,
                amount=split_input.amount
            )
            db.add(split)

    db.commit()

    #Activity log
    log_activity(db, current_user.id, "add_expense", f"Added expense '{expense.description}' ₹{expense.amount}", "group", group_id)
    for gm in db.query(models.GroupMember).filter(models.GroupMember.group_id == group_id).all():
        if gm.user_id != current_user.id:
            create_notification(db, gm.user_id, "New group expense", f"{current_user.username} added ₹{expense.amount} in {group.name}", "info")

    # Check monthly limit for payer
    payer = db.query(models.User).filter(models.User.id == expense.paid_by_id).first()
    if payer and payer.monthly_limit and float(payer.monthly_limit) > 0:
        now = datetime.now(timezone.utc)
        from sqlalchemy import func, extract
        personal_total = db.query(func.sum(models.Expense.amount)).filter(
            models.Expense.owner_id == payer.id,
            extract('month', models.Expense.created_at) == now.month,
            extract('year', models.Expense.created_at) == now.year
        ).scalar() or 0

        group_total = db.query(func.sum(models.GroupExpense.amount)).filter(
            models.GroupExpense.paid_by_id == payer.id,
            extract('month', models.GroupExpense.created_at) == now.month,
            extract('year', models.GroupExpense.created_at) == now.year
        ).scalar() or 0

        combined = float(personal_total) + float(group_total)

        if combined > float(payer.monthly_limit):
            try:
                from app.email import send_email
                send_email(
                    payer.email,
                    "⚠️ Monthly Limit Exceeded — Trackr",
                    f"""
                    <div style="font-family:Arial;padding:20px;max-width:500px">
                        <h2 style="color:#ef4444">⚠️ Monthly Limit Exceeded</h2>
                        <p>Hi {payer.username},</p>
                        <p>Your combined spending this month is <strong>₹{combined:.2f}</strong>,
                        exceeding your limit of <strong>₹{float(payer.monthly_limit):.2f}</strong>.</p>
                        <p>This includes both personal and group expenses.</p>
                        <p style="color:#6b7280;font-size:12px">— Trackr Team</p>
                    </div>
                    """
                )
                logger.info(f"Group limit exceeded email sent to {payer.email}")
            except Exception as email_err:
                logger.error(f"Failed to send group limit email: {email_err}")

    paid_by_user = db.query(models.User).filter(
        models.User.id == current_user.id
    ).first()

    return {
        "message": "Group expense created successfully",
        "expense": {
            "id": new_expense.id,
            "group_id": new_expense.group_id,
            "amount": new_expense.amount,
            "description": new_expense.description,
            "paid_by": {
                "user_id": current_user.id,
                "username": paid_by_user.username
            }
        }
    }


# ==================== GROUP EXPENSES - LIST ====================
@router.get("/{group_id}/expenses")
def get_group_expenses(
    group_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Get all expenses for a group."""
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

    expenses = db.query(models.GroupExpense).filter(
        models.GroupExpense.group_id == group_id
    ).order_by(models.GroupExpense.created_at.desc()).all()

    result = []
    for e in expenses:
        paid_by_user = db.query(models.User).filter(
            models.User.id == e.paid_by_id
        ).first()
        
        splits = db.query(models.Split).filter(
            models.Split.group_expense_id == e.id
        ).all()

        split_data = []
        for split in splits:
            split_user = db.query(models.User).filter(
                models.User.id == split.user_id
            ).first()
            split_data.append({
                "user_id": split.user_id,
                "username": split_user.username if split_user else None,
                "amount": split.amount
            })

        result.append({
            "id": e.id,
            "group_id": e.group_id,
            "amount": e.amount,
            "description": e.description,
            "paid_by": {
                "user_id": e.paid_by_id,
                "username": paid_by_user.username if paid_by_user else None
            },
            "splits": split_data,
            "created_at": e.created_at
        })

    return {"expenses": result}


# ==================== GROUP EXPENSES - DELETE ====================
@router.delete("/{group_id}/expenses/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_group_expense(
    group_id: int,
    expense_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Delete group expense (admin or creator only)."""
    expense = db.query(models.GroupExpense).filter(
        and_(
            models.GroupExpense.id == expense_id,
            models.GroupExpense.group_id == group_id
        )
    ).first()
    
    if not expense:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Expense not found"
        )

    # Check permissions: admin or creator
    is_admin = db.query(models.GroupMember).filter(
        and_(
            models.GroupMember.group_id == group_id,
            models.GroupMember.user_id == current_user.id,
            models.GroupMember.role == "admin"
        )
    ).first()

    if not is_admin and expense.paid_by_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this expense"
        )

    # Delete splits then expense
    db.query(models.Split).filter(
        models.Split.group_expense_id == expense_id
    ).delete()
    db.commit()

    desc = expense.description
    amt = expense.amount
    db.delete(expense)
    db.commit()
    
    log_activity(db, current_user.id, "delete_expense", f"Deleted group expense '{desc}' ₹{amt}", "group", group_id)


# ==================== GROUP EXPENSES - UPDATE DESCRIPTION ====================
@router.put("/{group_id}/expenses/{expense_id}")
def update_group_expense(
    group_id: int,
    expense_id: int,
    payload: dict,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Update expense description (admin or creator only)."""
    expense = db.query(models.GroupExpense).filter(
        and_(
            models.GroupExpense.id == expense_id,
            models.GroupExpense.group_id == group_id
        )
    ).first()
    
    if not expense:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Expense not found"
        )

    # Check permissions
    is_admin = db.query(models.GroupMember).filter(
        and_(
            models.GroupMember.group_id == group_id,
            models.GroupMember.user_id == current_user.id,
            models.GroupMember.role == "admin"
        )
    ).first()

    if not is_admin and expense.paid_by_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this expense"
        )

    if "description" in payload:
        expense.description = payload["description"]
        expense.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(expense)

    return {
        "message": "Expense updated",
        "expense": {
            "id": expense.id,
            "description": expense.description,
            "amount": expense.amount,
            "updated_at": expense.updated_at
        }
    }


# ==================== CALCULATE BALANCES ====================
@router.get("/{group_id}/balances")
def calculate_group_balances(
    group_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Calculate who owes whom in the group."""
    try:
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
                detail="Not a member of this group"
            )

        balances = {}
        
        # Calculate from expenses and splits
        expenses = db.query(models.GroupExpense).filter(
            models.GroupExpense.group_id == group_id
        ).all()

        for expense in expenses:
            paid_by = expense.paid_by_id
            splits = db.query(models.Split).filter(
                models.Split.group_expense_id == expense.id
            ).all()

            for split in splits:
                balances.setdefault(split.user_id, 0.0)
                balances.setdefault(paid_by, 0.0)
                balances[split.user_id] -= split.amount
                balances[paid_by] += split.amount

        # Adjust for confirmed settlements only
        settlements = db.query(models.Settlement).filter(
            and_(
                models.Settlement.group_id == group_id,
                models.Settlement.status == "confirmed"
            )
        ).all()
        
        for s in settlements:
            balances.setdefault(s.from_user_id, 0.0)
            balances.setdefault(s.to_user_id, 0.0)
            balances[s.from_user_id] += s.amount
            balances[s.to_user_id] -= s.amount

        # Simplify balances (creditors vs debtors)
        creditors, debtors = [], []
        for user_id, balance in balances.items():
            rounded = round(balance, 2)
            if rounded > 0:
                creditors.append([user_id, rounded])
            elif rounded < 0:
                debtors.append([user_id, -rounded])

        # Fetch usernames
        all_user_ids = [uid for uid, _ in creditors + debtors]
        users = db.query(models.User.id, models.User.username).filter(
            models.User.id.in_(all_user_ids)
        ).all()
        user_map = {u.id: u.username for u in users}

        # Greedy matching algorithm
        result = []
        i, j = 0, 0
        while i < len(debtors) and j < len(creditors):
            debtor_id, debt = debtors[i]
            creditor_id, credit = creditors[j]
            amount = min(debt, credit)
            
            result.append({
                "from": {
                    "user_id": debtor_id,
                    "username": user_map.get(debtor_id, "Unknown")
                },
                "to": {
                    "user_id": creditor_id,
                    "username": user_map.get(creditor_id, "Unknown")
                },
                "amount": round(amount, 2)
            })
            
            debtors[i][1] -= amount
            creditors[j][1] -= amount
            if debtors[i][1] == 0:
                i += 1
            if creditors[j][1] == 0:
                j += 1

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error calculating balances: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to calculate balances"
        )
    
@router.get("/{group_id}/summary")
def get_group_summary(
    group_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    member = db.query(models.GroupMember).filter(
        and_(
            models.GroupMember.group_id == group_id,
            models.GroupMember.user_id == current_user.id
        )
    ).first()
    if not member:
        raise HTTPException(status_code=403, detail="Not a member")

    expenses = db.query(models.GroupExpense).filter(
        models.GroupExpense.group_id == group_id
    ).all()

    total = sum(float(e.amount) for e in expenses)

    # Per member spend
    member_spend = {}
    members = db.query(models.GroupMember, models.User).join(
        models.User, models.GroupMember.user_id == models.User.id
    ).filter(models.GroupMember.group_id == group_id).all()

    for gm, u in members:
        paid = sum(float(e.amount) for e in expenses if e.paid_by_id == u.id)
        splits = db.query(models.Split).join(
            models.GroupExpense,
            models.Split.group_expense_id == models.GroupExpense.id
        ).filter(
            models.GroupExpense.group_id == group_id,
            models.Split.user_id == u.id
        ).all()
        owed = sum(float(s.amount) for s in splits)
        member_spend[u.username] = {
            "paid": round(paid, 2),
            "owed": round(owed, 2),
            "net": round(paid - owed, 2)
        }

    return {
        "group_id": group_id,
        "total_expenses": len(expenses),
        "total_amount": round(total, 2),
        "member_summary": member_spend
    }