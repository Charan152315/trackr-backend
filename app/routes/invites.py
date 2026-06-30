from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import and_
from .. import models, schemas, database, auth
from datetime import datetime, timezone, timedelta
import secrets
import logging
from .notifications import create_notification
from .activity import log_activity

router = APIRouter(prefix="/groups", tags=["Invites"])
logger = logging.getLogger(__name__)


def generate_invite_code():
    return secrets.token_urlsafe(6)[:8]


# ==================== CREATE INVITE LINK ====================
@router.post("/{group_id}/invite", status_code=status.HTTP_201_CREATED)
def create_invite(
    group_id: int,
    payload: dict,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Generate an invite link. Only admins can create invites."""
    member = db.query(models.GroupMember).filter(
        and_(
            models.GroupMember.group_id == group_id,
            models.GroupMember.user_id == current_user.id,
            models.GroupMember.role == "admin"
        )
    ).first()
    if not member:
        raise HTTPException(status_code=403, detail="Only admins can create invite links")

    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    expiry_hours = payload.get("expiry_hours")  # null = never expires
    expires_at = None
    if expiry_hours:
        expires_at = datetime.now(timezone.utc) + timedelta(hours=expiry_hours)

    code = generate_invite_code()
    invite = models.GroupInvite(
        group_id=group_id,
        code=code,
        created_by=current_user.id,
        expires_at=expires_at,
        is_active=True
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)

    log_activity(db, current_user.id, "create_invite", f"Created invite link for {group.name}", "group", group_id)

    return {
        "code": invite.code,
        "expires_at": invite.expires_at,
        "group_name": group.name
    }


# ==================== GET ACTIVE INVITES FOR GROUP ====================
@router.get("/{group_id}/invites")
def get_group_invites(
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

    invites = db.query(models.GroupInvite).filter(
        and_(
            models.GroupInvite.group_id == group_id,
            models.GroupInvite.is_active == True
        )
    ).order_by(models.GroupInvite.created_at.desc()).all()

    now = datetime.now(timezone.utc)
    result = []
    for inv in invites:
        if inv.expires_at and inv.expires_at < now:
            continue
        result.append({
            "code": inv.code,
            "expires_at": inv.expires_at,
            "created_at": inv.created_at
        })
    return result


# ==================== REVOKE INVITE ====================
@router.delete("/{group_id}/invite/{code}")
def revoke_invite(
    group_id: int,
    code: str,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    member = db.query(models.GroupMember).filter(
        and_(
            models.GroupMember.group_id == group_id,
            models.GroupMember.user_id == current_user.id,
            models.GroupMember.role == "admin"
        )
    ).first()
    if not member:
        raise HTTPException(status_code=403, detail="Only admins can revoke invites")

    invite = db.query(models.GroupInvite).filter(
        and_(models.GroupInvite.code == code, models.GroupInvite.group_id == group_id)
    ).first()
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found")

    invite.is_active = False
    db.commit()
    return {"message": "Invite revoked"}


# ==================== PREVIEW INVITE (public-ish, no join) ====================
@router.get("/invite/{code}/preview")
def preview_invite(
    code: str,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Shows group info before joining — used by the invite landing page."""
    invite = db.query(models.GroupInvite).filter(models.GroupInvite.code == code).first()
    if not invite or not invite.is_active:
        raise HTTPException(status_code=404, detail="Invite link is invalid or has been revoked")

    if invite.expires_at and invite.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="This invite link has expired")

    group = db.query(models.Group).filter(models.Group.id == invite.group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group no longer exists")

    member_count = db.query(models.GroupMember).filter(
        models.GroupMember.group_id == group.id
    ).count()

    already_member = db.query(models.GroupMember).filter(
        and_(
            models.GroupMember.group_id == group.id,
            models.GroupMember.user_id == current_user.id
        )
    ).first() is not None

    owner = db.query(models.User).filter(models.User.id == group.owner_id).first()

    return {
        "group_id": group.id,
        "group_name": group.name,
        "owner_username": owner.username if owner else None,
        "member_count": member_count,
        "already_member": already_member
    }


# ==================== JOIN VIA INVITE (instant join) ====================
@router.post("/invite/{code}/join", status_code=status.HTTP_200_OK)
def join_via_invite(
    code: str,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    invite = db.query(models.GroupInvite).filter(models.GroupInvite.code == code).first()
    if not invite or not invite.is_active:
        raise HTTPException(status_code=404, detail="Invite link is invalid or has been revoked")

    if invite.expires_at and invite.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="This invite link has expired")

    group = db.query(models.Group).filter(models.Group.id == invite.group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group no longer exists")

    existing = db.query(models.GroupMember).filter(
        and_(
            models.GroupMember.group_id == group.id,
            models.GroupMember.user_id == current_user.id
        )
    ).first()
    if existing:
        return {"message": "Already a member", "group_id": group.id}

    new_member = models.GroupMember(
        user_id=current_user.id,
        group_id=group.id,
        role="member"
    )
    db.add(new_member)
    db.commit()

    create_notification(
        db, group.owner_id,
        "New member joined",
        f"{current_user.username} joined '{group.name}' via invite link",
        "info"
    )
    log_activity(db, current_user.id, "join_group", f"Joined {group.name} via invite", "group", group.id)

    return {"message": f"Joined {group.name}!", "group_id": group.id}


# ==================== LEAVE GROUP ====================
@router.post("/{group_id}/leave", status_code=status.HTTP_200_OK)
def leave_group(
    group_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Leave a group — blocked if user has outstanding balance."""
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    if group.owner_id == current_user.id:
        raise HTTPException(
            status_code=400,
            detail="Group owner cannot leave. Transfer ownership or delete the group instead."
        )

    member = db.query(models.GroupMember).filter(
        and_(
            models.GroupMember.group_id == group_id,
            models.GroupMember.user_id == current_user.id
        )
    ).first()
    if not member:
        raise HTTPException(status_code=400, detail="You are not a member of this group")

    # Check outstanding balance
    balances = {}
    expenses = db.query(models.GroupExpense).filter(models.GroupExpense.group_id == group_id).all()
    for expense in expenses:
        paid_by = expense.paid_by_id
        splits = db.query(models.Split).filter(models.Split.group_expense_id == expense.id).all()
        for split in splits:
            balances.setdefault(split.user_id, 0.0)
            balances.setdefault(paid_by, 0.0)
            balances[split.user_id] -= float(split.amount)
            balances[paid_by] += float(split.amount)

    confirmed = db.query(models.Settlement).filter(
        and_(models.Settlement.group_id == group_id, models.Settlement.status == "confirmed")
    ).all()
    for s in confirmed:
        balances[s.from_user_id] = balances.get(s.from_user_id, 0) + float(s.amount)
        balances[s.to_user_id] = balances.get(s.to_user_id, 0) - float(s.amount)

    my_balance = round(balances.get(current_user.id, 0.0), 2)
    if abs(my_balance) > 0.01:
        if my_balance < 0:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot leave — you owe ₹{abs(my_balance):.2f} in this group. Settle up first."
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot leave — ₹{my_balance:.2f} is owed to you in this group. Settle up first."
            )

    db.delete(member)
    db.commit()

    log_activity(db, current_user.id, "leave_group", f"Left {group.name}", "group", group_id)
    create_notification(
        db, group.owner_id,
        "Member left",
        f"{current_user.username} left '{group.name}'",
        "info"
    )

    return {"message": f"Left {group.name}"}

@router.get("/invite-requests/pending")
def get_my_pending_invites(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Get all pending group invites for the current user."""
    requests = db.query(models.GroupInviteRequest).filter(
        and_(
            models.GroupInviteRequest.invited_user_id == current_user.id,
            models.GroupInviteRequest.status == "pending"
        )
    ).order_by(models.GroupInviteRequest.created_at.desc()).all()

    result = []
    for r in requests:
        group = db.query(models.Group).filter(models.Group.id == r.group_id).first()
        inviter = db.query(models.User).filter(models.User.id == r.invited_by_id).first()
        if group:
            result.append({
                "id": r.id,
                "group_id": group.id,
                "group_name": group.name,
                "invited_by": inviter.username if inviter else "Unknown",
                "created_at": r.created_at
            })
    return result


@router.post("/invite-requests/{request_id}/accept")
def accept_invite_request(
    request_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    req = db.query(models.GroupInviteRequest).filter(
        and_(
            models.GroupInviteRequest.id == request_id,
            models.GroupInviteRequest.invited_user_id == current_user.id
        )
    ).first()
    if not req:
        raise HTTPException(status_code=404, detail="Invite not found")
    if req.status != "pending":
        raise HTTPException(status_code=400, detail=f"Invite already {req.status}")

    group = db.query(models.Group).filter(models.Group.id == req.group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group no longer exists")

    existing = db.query(models.GroupMember).filter(
        and_(models.GroupMember.group_id == req.group_id, models.GroupMember.user_id == current_user.id)
    ).first()
    if not existing:
        new_member = models.GroupMember(user_id=current_user.id, group_id=req.group_id, role="member")
        db.add(new_member)

    req.status = "accepted"
    req.resolved_at = datetime.now(timezone.utc)
    db.commit()

    create_notification(db, req.invited_by_id, "Invite accepted", f"{current_user.username} joined '{group.name}'", "success")
    log_activity(db, current_user.id, "join_group", f"Joined {group.name}", "group", req.group_id)

    return {"message": f"Joined {group.name}!", "group_id": req.group_id}


@router.post("/invite-requests/{request_id}/reject")
def reject_invite_request(
    request_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    req = db.query(models.GroupInviteRequest).filter(
        and_(
            models.GroupInviteRequest.id == request_id,
            models.GroupInviteRequest.invited_user_id == current_user.id
        )
    ).first()

    if not req:
        raise HTTPException(status_code=404, detail="Invite not found")

    if req.status != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Invite already {req.status}"
        )

    group = db.query(models.Group).filter(
        models.Group.id == req.group_id
    ).first()

    if not group:
        raise HTTPException(status_code=404, detail="Group no longer exists")

    req.status = "rejected"
    req.resolved_at = datetime.now(timezone.utc)

    db.commit()

    create_notification(
        db,
        req.invited_by_id,
        "Invite declined",
        f"{current_user.username} declined your invitation to '{group.name}'",
        "warning"
    )
    
    log_activity(
        db,
        current_user.id,
        "reject_invite",
        f"Declined invitation to {group.name}",
        "group",
        req.group_id
    )
    return {"message": "Invite declined"}