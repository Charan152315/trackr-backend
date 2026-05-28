from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from .. import models, database, auth
from datetime import datetime, timezone
import logging

router = APIRouter(prefix="/notifications", tags=["Notifications"])
logger = logging.getLogger(__name__)


def create_notification(db: Session, user_id: int, title: str, message: str, type: str = "info"):
    notif = models.Notification(
        user_id=user_id,
        title=title,
        message=message,
        type=type
    )
    db.add(notif)
    db.commit()
    return notif


@router.get("/")
def get_notifications(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    notifs = db.query(models.Notification).filter(
        models.Notification.user_id == current_user.id
    ).order_by(models.Notification.created_at.desc()).limit(50).all()

    return {
        "notifications": [
            {
                "id": n.id,
                "title": n.title,
                "message": n.message,
                "type": n.type,
                "is_read": n.is_read,
                "created_at": n.created_at
            }
            for n in notifs
        ],
        "unread_count": sum(1 for n in notifs if not n.is_read)
    }


@router.post("/{notif_id}/read", status_code=status.HTTP_200_OK)
def mark_read(
    notif_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    notif = db.query(models.Notification).filter(
        models.Notification.id == notif_id,
        models.Notification.user_id == current_user.id
    ).first()
    if notif:
        notif.is_read = True
        db.commit()
    return {"message": "Marked as read"}


@router.post("/read-all", status_code=status.HTTP_200_OK)
def mark_all_read(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    db.query(models.Notification).filter(
        models.Notification.user_id == current_user.id,
        models.Notification.is_read == False
    ).update({"is_read": True})
    db.commit()
    return {"message": "All marked as read"}


@router.delete("/clear", status_code=status.HTTP_200_OK)
def clear_all(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    db.query(models.Notification).filter(
        models.Notification.user_id == current_user.id
    ).delete()
    db.commit()
    return {"message": "Cleared"}