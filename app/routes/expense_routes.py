from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func, extract
from .. import models, schemas, database, auth
from datetime import datetime,timezone
from fastapi.responses import StreamingResponse
import csv
import io
import logging
from app.routes.activity import log_activity

router = APIRouter(
    prefix="/expenses",
    tags=["Expenses"]
)

logger = logging.getLogger(__name__)

# ==================== CREATE EXPORT PDF/CSV ====================

@router.get("/export")
def export_expenses(
    format: str = "csv",
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    expenses = db.query(models.Expense).filter(
        models.Expense.owner_id == current_user.id
    ).order_by(
        models.Expense.created_at.desc()
    ).all()

    # ---------- CSV EXPORT ----------
    if format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)

        writer.writerow([
            "ID",
            "Title",
            "Amount",
            "Category",
            "Date"
        ])

        for e in expenses:
            writer.writerow([
                e.id,
                e.title,
                float(e.amount),
                e.category,
                e.created_at.strftime("%Y-%m-%d %H:%M")
            ])

        output.seek(0)

        return StreamingResponse(
            io.BytesIO(output.getvalue().encode()),
            media_type="text/csv",
            headers={
                "Content-Disposition":
                f"attachment; filename=trackr_expenses_{datetime.now(timezone.utc).strftime('%Y%m%d')}.csv"
            }
        )

    # ---------- PDF EXPORT ----------
    elif format == "pdf":
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib import colors
            from reportlab.platypus import (
                SimpleDocTemplate,
                Table,
                TableStyle,
                Paragraph,
                Spacer
            )
            from reportlab.lib.styles import (
                getSampleStyleSheet,
                ParagraphStyle
            )
            from reportlab.lib.units import cm

            buffer = io.BytesIO()

            doc = SimpleDocTemplate(
                buffer,
                pagesize=A4,
                topMargin=2 * cm,
                bottomMargin=2 * cm
            )

            styles = getSampleStyleSheet()
            elements = []

            title_style = ParagraphStyle(
                "title",
                parent=styles["Heading1"],
                fontSize=20,
                textColor=colors.HexColor("#0ea5e9"),
                spaceAfter=6
            )

            sub_style = ParagraphStyle(
                "sub",
                parent=styles["Normal"],
                fontSize=11,
                textColor=colors.HexColor("#64748b"),
                spaceAfter=20
            )

            elements.append(
                Paragraph(
                    "Trackr — Expense Report",
                    title_style
                )
            )

            elements.append(
                Paragraph(
                    f"User: {current_user.username} | Generated: "
                    f"{datetime.now(timezone.utc).strftime('%d %b %Y')}",
                    sub_style
                )
            )

            elements.append(
                Spacer(1, 0.3 * cm)
            )

            data = [[
                "#",
                "Title",
                "Amount (₹)",
                "Category",
                "Date"
            ]]

            total = 0

            for e in expenses:
                data.append([
                    str(e.id),
                    e.title[:35],
                    f"{float(e.amount):.2f}",
                    e.category or "—",
                    e.created_at.strftime("%d %b %Y")
                ])
                total += float(e.amount)

            # Total row
            data.append([
                "",
                "TOTAL",
                f"{total:.2f}",
                "",
                ""
            ])

            table = Table(
                data,
                colWidths=[
                    1.2 * cm,
                    7 * cm,
                    3 * cm,
                    3.5 * cm,
                    3.5 * cm
                ]
            )

            table.setStyle(TableStyle([
                ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#0ea5e9")),
                ("TEXTCOLOR", (0,0), (-1,0), colors.white),
                ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
                ("FONTSIZE", (0,0), (-1,0), 10),
                ("ALIGN", (0,0), (-1,-1), "LEFT"),
                ("ALIGN", (2,0), (2,-1), "RIGHT"),
                ("ROWBACKGROUNDS", (0,1), (-1,-2),
                    [colors.HexColor("#f8fafc"), colors.white]),
                ("BACKGROUND", (0,-1), (-1,-1),
                    colors.HexColor("#e0f7ff")),
                ("FONTNAME", (0,-1), (-1,-1),
                    "Helvetica-Bold"),
                ("GRID", (0,0), (-1,-1),
                    0.3, colors.HexColor("#e2e8f0")),
                ("TOPPADDING", (0,0), (-1,-1), 5),
                ("BOTTOMPADDING", (0,0), (-1,-1), 5),
                ("LEFTPADDING", (0,0), (-1,-1), 8),
            ]))

            elements.append(table)

            doc.build(elements)

            buffer.seek(0)

            return StreamingResponse(
                buffer,
                media_type="application/pdf",
                headers={
                    "Content-Disposition":
                    f"attachment; filename=trackr_expenses_{datetime.now(timezone.utc).strftime('%Y%m%d')}.pdf"
                }
            )

        except ImportError:
            raise HTTPException(
                status_code=500,
                detail="reportlab not installed. Run: pip install reportlab"
            )

    # ---------- INVALID FORMAT ----------
    else:
        raise HTTPException(
            status_code=400,
            detail="Format must be csv or pdf"
        )

# ==================== CREATE EXPENSE ====================
@router.post("/", status_code=status.HTTP_201_CREATED, response_model=schemas.ExpenseOut)
def create_expense(
    expense: schemas.ExpenseCreate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Create a new personal expense."""
    new_expense = models.Expense(
        title=expense.title,
        amount=expense.amount,
        category=expense.category,
        owner_id=current_user.id
    )
    
    db.add(new_expense)
    db.commit()
    db.refresh(new_expense)
    
    log_activity(db, current_user.id, "add_expense", f"Added expense '{expense.title}' ₹{expense.amount} [{expense.category}]", "expense", new_expense.id)

    # Check monthly limit and send alert if crossed
    if current_user.monthly_limit and float(current_user.monthly_limit) > 0:
        now = datetime.now(timezone.utc)
        total = db.query(func.sum(models.Expense.amount)).filter(
            models.Expense.owner_id == current_user.id,
            extract('month', models.Expense.created_at) == now.month,
            extract('year', models.Expense.created_at) == now.year
        ).scalar() or 0

        if float(total) > float(current_user.monthly_limit):
            try:
                from app.email import send_email
                send_email(
                    current_user.email,
                    "⚠️ Monthly Limit Exceeded — Trackr",
                    f"""
                    <div style="font-family:Arial;padding:20px;max-width:500px">
                        <h2 style="color:#ef4444">⚠️ Monthly Limit Exceeded</h2>
                        <p>Hi {current_user.username},</p>
                        <p>You have spent <strong>₹{float(total):.2f}</strong> this month,
                        exceeding your limit of
                        <strong>₹{float(current_user.monthly_limit):.2f}</strong>.</p>
                        <p>Review your expenses on your dashboard.</p>
                        <p style="color:#6b7280;font-size:12px">— Trackr Team</p>
                    </div>
                    """
                )
                logger.info(f"Limit exceeded email sent to {current_user.email}")
            except Exception as email_err:
                logger.error(f"Failed to send limit email: {email_err}")

    logger.info(f"Expense created: {current_user.id}, Amount: {new_expense.amount}")
    return new_expense


# ==================== GET ALL EXPENSES ====================
@router.get("/", response_model=list[schemas.ExpenseOut])
def get_expenses(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Get all personal expenses for current user."""
    expenses = db.query(models.Expense).filter(
        models.Expense.owner_id == current_user.id
    ).order_by(models.Expense.created_at.desc()).all()

    return expenses


# ==================== GET EXPENSE BY ID ====================
@router.get("/{expense_id}", response_model=schemas.ExpenseOut)
def get_expense_by_id(
    expense_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Get a specific expense by ID."""
    expense = db.query(models.Expense).filter(
        models.Expense.id == expense_id,
        models.Expense.owner_id == current_user.id
    ).first()

    if not expense:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Expense not found"
        )

    return expense


# ==================== UPDATE EXPENSE ====================
@router.put("/{expense_id}", response_model=schemas.ExpenseOut)
def update_expense(
    expense_id: int,
    updated_data: schemas.ExpenseUpdate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Update a personal expense."""
    expense_query = db.query(models.Expense).filter(
        models.Expense.id == expense_id,
        models.Expense.owner_id == current_user.id
    )
    
    expense = expense_query.first()

    if not expense:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Expense not found"
        )

    # Check if anything actually changed
    if (expense.title == updated_data.title and 
        expense.amount == updated_data.amount and 
        expense.category == updated_data.category):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No changes provided"
        )

    expense_query.update(updated_data.dict(), synchronize_session=False)
    db.commit()
    db.refresh(expense)

    logger.info(f"Expense updated: {expense_id}")
    return expense


# ==================== DELETE EXPENSE ====================
@router.delete("/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_expense(
    expense_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Delete a personal expense."""
    expense_query = db.query(models.Expense).filter(
        models.Expense.id == expense_id,
        models.Expense.owner_id == current_user.id
    )
    
    expense = expense_query.first()

    if not expense:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Expense not found"
        )

    expense_query.delete(synchronize_session=False)
    db.commit()

    logger.info(f"Expense deleted: {expense_id}")


# ==================== GET MONTHLY SUMMARY ====================
@router.get("/summary/monthly", status_code=status.HTTP_200_OK)
def get_expense_monthly_summary(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Get monthly expense summary with breakdown by category."""
    now = datetime.utcnow()
    start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end_date = now

    # Calculate total expenses this month using extract for month/year
    personal_total = db.query(func.sum(models.Expense.amount)).filter(
            models.Expense.owner_id == current_user.id,
            extract('month', models.Expense.created_at) == now.month,
            extract('year', models.Expense.created_at) == now.year
        ).scalar() or 0

    group_share = db.query(func.sum(models.Split.amount)).join(
            models.GroupExpense,
            models.Split.group_expense_id == models.GroupExpense.id
        ).filter(
            models.Split.user_id == current_user.id,
            extract('month', models.GroupExpense.created_at) == now.month,
            extract('year', models.GroupExpense.created_at) == now.year
        ).scalar() or 0

    total_amount = float(personal_total) + float(group_share)


    # Check if exceeded limit
    warning = None
    if current_user.monthly_limit and total_amount > current_user.monthly_limit:
        warning = f"You have exceeded your monthly limit of ₹{current_user.monthly_limit:.2f}"

    # Category breakdown for current month
    category_summary = db.query(
        models.Expense.category,
        func.sum(models.Expense.amount).label("total")
    ).filter(
        models.Expense.owner_id == current_user.id,
        extract('month', models.Expense.created_at) == now.month,
        extract('year', models.Expense.created_at) == now.year
    ).group_by(models.Expense.category).all()

    category_breakdown = {
        category: float(total) for category, total in category_summary
    }

    # Total expense count for current month
    total_expenses = db.query(models.Expense).filter(
        models.Expense.owner_id == current_user.id,
        extract('month', models.Expense.created_at) == now.month,
        extract('year', models.Expense.created_at) == now.year
    ).count()

    return {
        "total_spent": round(float(total_amount), 2),
        "personal_spent": round(float(personal_total), 2),
        "group_share": round(float(group_share), 2),
        "by_category": category_breakdown,
        "total_expenses": total_expenses,
        "month": now.strftime("%B %Y"),
        "limit": current_user.monthly_limit,
        "warning": warning
    }


# ==================== GET CATEGORY BREAKDOWN ====================
@router.get("/breakdown/categories")
def get_category_breakdown(
    days: int = 30,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Get expense breakdown by category for last N days or current month."""
    if days <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Days must be greater than 0"
        )

    # For current month analysis
    now = datetime.utcnow()
    
    # Use current month instead of last N days for consistency
    category_summary = db.query(
        models.Expense.category,
        func.sum(models.Expense.amount).label("total"),
        func.count(models.Expense.id).label("count")
    ).filter(
        models.Expense.owner_id == current_user.id,
        extract('month', models.Expense.created_at) == now.month,
        extract('year', models.Expense.created_at) == now.year
    ).group_by(models.Expense.category).all()

    # Calculate total for percentage calculation
    total_all_categories = sum(float(total) for _, total, _ in category_summary)

    breakdown = [
        {
            "category": category,
            "total": round(float(total), 2),
            "count": count,
            "average": round(float(total) / count, 2) if count > 0 else 0,
            "percentage": round((float(total) / total_all_categories * 100), 1) if total_all_categories > 0 else 0
        }
        for category, total, count in category_summary
    ]

    return {
        "period_days": days,
        "month": now.strftime("%B %Y"),
        "total_amount": round(total_all_categories, 2),
        "breakdown": breakdown
    }


# ==================== GET EXPENSE STATISTICS ====================
@router.get("/stats/overview")
def get_expense_statistics(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Get overall expense statistics."""
    now = datetime.utcnow()
    
    # Current month
    current_month_total = db.query(func.sum(models.Expense.amount)).filter(
        models.Expense.owner_id == current_user.id,
        extract('month', models.Expense.created_at) == now.month,
        extract('year', models.Expense.created_at) == now.year
    ).scalar() or 0
    
    # Last month
    last_month = now.month - 1 if now.month > 1 else 12
    last_month_year = now.year if now.month > 1 else now.year - 1
    
    last_month_total = db.query(func.sum(models.Expense.amount)).filter(
        models.Expense.owner_id == current_user.id,
        extract('month', models.Expense.created_at) == last_month,
        extract('year', models.Expense.created_at) == last_month_year
    ).scalar() or 0
    
    # Calculate change percentage
    if last_month_total > 0:
        change_percentage = ((current_month_total - last_month_total) / last_month_total) * 100
    else:
        change_percentage = 100 if current_month_total > 0 else 0
    
    # Top category this month
    top_category = db.query(
        models.Expense.category,
        func.sum(models.Expense.amount).label("total")
    ).filter(
        models.Expense.owner_id == current_user.id,
        extract('month', models.Expense.created_at) == now.month,
        extract('year', models.Expense.created_at) == now.year
    ).group_by(models.Expense.category).order_by(func.sum(models.Expense.amount).desc()).first()
    
    return {
        "current_month_total": round(float(current_month_total), 2),
        "last_month_total": round(float(last_month_total), 2),
        "change_percentage": round(change_percentage, 1),
        "top_category": top_category[0] if top_category else None,
        "top_category_amount": round(float(top_category[1]), 2) if top_category else 0,
        "monthly_limit": current_user.monthly_limit,
        "limit_remaining": round(current_user.monthly_limit - float(current_month_total), 2) if current_user.monthly_limit else None
    }

