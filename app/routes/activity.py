from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from .. import models, database, auth
import logging

router = APIRouter(prefix="/activity", tags=["Activity"])
logger = logging.getLogger(__name__)


def log_activity(db: Session, user_id: int, action: str, description: str, entity_type: str = None, entity_id: int = None):
    log = models.ActivityLog(
        user_id=user_id,
        action=action,
        description=description,
        entity_type=entity_type,
        entity_id=entity_id
    )
    db.add(log)
    db.commit()
    return log


@router.get("/")
def get_activity(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    logs = db.query(models.ActivityLog).filter(
        models.ActivityLog.user_id == current_user.id
    ).order_by(models.ActivityLog.created_at.desc()).limit(100).all()

    return {
        "activity": [
            {
                "id": l.id,
                "action": l.action,
                "description": l.description,
                "entity_type": l.entity_type,
                "entity_id": l.entity_id,
                "created_at": l.created_at
            }
            for l in logs
        ]
    }