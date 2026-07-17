import csv
import io
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, Response, current_app
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy import func, or_
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from forms import RegisterForm, LoginForm, ExpenseForm, IncomeForm, BudgetForm
from models import db, User, Category, Expense, Income, Budget

main = Blueprint("main", __name__)
DEFAULT_CATEGORIES = ["Food", "Travel", "Shopping", "Entertainment", "Bills", "Education", "Healthcare", "Other"]


def month_bounds(value=None):
    start = datetime.strptime(value, "%Y-%m").date().replace(day=1) if value else date.today().replace(day=1)
    end = (start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    return start, end


def category_choices(form):
    categories = Category.query.filter(or_(Category.user_id == current_user.id, Category.user_id.is_(None))).order_by(Category.name).all()
    form.category_id.choices = [(c.id, c.name) for c in categories]


def get_budget(month=None):
    month = month or date.today().strftime("%Y-%m")
    return Budget.query.filter_by(user_id=current_user.id, month=month).first()


@main.route("/")
def index():
    return redirect(url_for("main.dashboard" if current_user.is_authenticated else "main.login"))


@main.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    form = RegisterForm()
    if form.validate_on_submit():
        if User.query.filter_by(email=form.email.data.lower()).first():
            flash("That email is already registered.", "danger")
        else:
            user = User(name=form.name.data.strip(), email=form.email.data.lower().strip())
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.flush()
            for name in DEFAULT_CATEGORIES:
                db.session.add(Category(name=name, user_id=user.id))
            db.session.commit()
            login_user(user)
            flash("Welcome! Your account is ready.", "success")
            return redirect(url_for("main.dashboard"))
    return render_template("register.html", form=form)


@main.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower().strip()).first()
        if user and user.check_password(form.password.data):
            login_user(user, remember=True)
            return redirect(url_for("main.dashboard"))
        flash("Invalid email or password.", "danger")
    return render_template("login.html", form=form)


@main.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("main.login"))


@main.route("/dashboard")
@login_required
def dashboard():
    start, end = month_bounds()
    income = db.session.query(func.coalesce(func.sum(Income.amount), 0)).filter_by(user_id=current_user.id).scalar()
    expenses = db.session.query(func.coalesce(func.sum(Expense.amount), 0)).filter_by(user_id=current_user.id).scalar()
    monthly = db.session.query(func.coalesce(func.sum(Expense.amount), 0)).filter(Expense.user_id == current_user.id, Expense.date.between(start, end)).scalar()
    budget = get_budget()
    recent = sorted(list(current_user.expenses) + list(current_user.incomes), key=lambda x: x.date, reverse=True)[:8]
    return render_template("dashboard.html", total_income=income, total_expenses=expenses, balance=income-expenses, monthly=monthly, budget=budget, recent=recent)


@main.route("/expenses", methods=["GET", "POST"])
@login_required
def expenses():
    form = ExpenseForm()
    category_choices(form)
    if form.validate_on_submit():
        category_id = form.category_id.data
        if form.custom_category.data.strip():
            name = form.custom_category.data.strip().title()
            cat = Category.query.filter_by(name=name, user_id=current_user.id).first()
            if not cat:
                cat = Category(name=name, user_id=current_user.id)
                db.session.add(cat); db.session.flush()
            category_id = cat.id
        item = Expense(title=form.title.data.strip(), amount=form.amount.data, date=form.date.data, notes=form.notes.data.strip(), category_id=category_id, user_id=current_user.id)
        db.session.add(item); db.session.commit()
        if item.amount >= current_app.config["LARGE_EXPENSE_THRESHOLD"]:
            flash(f"Large expense alert: ₹{item.amount:,.2f} was recorded.", "warning")
        flash("Expense added.", "success")
        return redirect(url_for("main.expenses"))
    query = Expense.query.filter_by(user_id=current_user.id)
    if q := request.args.get("q", "").strip(): query = query.filter(Expense.title.ilike(f"%{q}%"))
    if cat := request.args.get("category", type=int): query = query.filter_by(category_id=cat)
    if start := request.args.get("start"): query = query.filter(Expense.date >= start)
    if end := request.args.get("end"): query = query.filter(Expense.date <= end)
    if minimum := request.args.get("min", type=float): query = query.filter(Expense.amount >= minimum)
    if maximum := request.args.get("max", type=float): query = query.filter(Expense.amount <= maximum)
    page = query.order_by(Expense.date.desc(), Expense.id.desc()).paginate(page=request.args.get("page", 1, type=int), per_page=10, error_out=False)
    categories = Category.query.filter_by(user_id=current_user.id).order_by(Category.name).all()
    return render_template("expenses.html", form=form, expenses=page, categories=categories)


@main.route("/expenses/<int:item_id>/edit", methods=["GET", "POST"])
@login_required
def edit_expense(item_id):
    item = Expense.query.filter_by(id=item_id, user_id=current_user.id).first_or_404()
    form = ExpenseForm(obj=item); category_choices(form)
    if form.validate_on_submit():
        item.title, item.amount, item.date, item.notes, item.category_id = form.title.data.strip(), form.amount.data, form.date.data, form.notes.data.strip(), form.category_id.data
        db.session.commit(); flash("Expense updated.", "success"); return redirect(url_for("main.expenses"))
    return render_template("edit_item.html", form=form, item=item, kind="Expense")


@main.route("/expenses/<int:item_id>/delete", methods=["POST"])
@login_required
def delete_expense(item_id):
    item = Expense.query.filter_by(id=item_id, user_id=current_user.id).first_or_404(); db.session.delete(item); db.session.commit()
    flash("Expense deleted.", "success"); return redirect(url_for("main.expenses"))


@main.route("/income", methods=["GET", "POST"])
@login_required
def income():
    form = IncomeForm()
    if form.validate_on_submit():
        db.session.add(Income(source=form.source.data.strip(), amount=form.amount.data, date=form.date.data, notes=form.notes.data.strip(), user_id=current_user.id)); db.session.commit()
        flash("Income added.", "success"); return redirect(url_for("main.income"))
    items = Income.query.filter_by(user_id=current_user.id).order_by(Income.date.desc()).all()
    return render_template("income.html", form=form, incomes=items)


@main.route("/income/<int:item_id>/edit", methods=["GET", "POST"])
@login_required
def edit_income(item_id):
    item = Income.query.filter_by(id=item_id, user_id=current_user.id).first_or_404(); form = IncomeForm(obj=item)
    if form.validate_on_submit():
        item.source, item.amount, item.date, item.notes = form.source.data.strip(), form.amount.data, form.date.data, form.notes.data.strip(); db.session.commit()
        flash("Income updated.", "success"); return redirect(url_for("main.income"))
    return render_template("edit_item.html", form=form, item=item, kind="Income")


@main.route("/income/<int:item_id>/delete", methods=["POST"])
@login_required
def delete_income(item_id):
    item = Income.query.filter_by(id=item_id, user_id=current_user.id).first_or_404(); db.session.delete(item); db.session.commit()
    flash("Income deleted.", "success"); return redirect(url_for("main.income"))


@main.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    form = BudgetForm(); budget = get_budget()
    if request.method == "GET" and budget: form.amount.data = budget.amount
    if form.validate_on_submit():
        if not budget: budget = Budget(month=date.today().strftime("%Y-%m"), user_id=current_user.id, amount=form.amount.data); db.session.add(budget)
        else: budget.amount = form.amount.data
        db.session.commit(); flash("Budget saved.", "success"); return redirect(url_for("main.settings"))
    return render_template("settings.html", form=form, budget=budget)


@main.route("/api/charts")
@login_required
def charts():
    start, end = month_bounds()
    rows = db.session.query(Category.name, func.sum(Expense.amount)).join(Expense).filter(Expense.user_id == current_user.id, Expense.date.between(start, end)).group_by(Category.name).all()
    monthly_rows = db.session.query(func.strftime("%Y-%m", Expense.date), func.sum(Expense.amount)).filter(Expense.user_id == current_user.id, Expense.date >= (start - timedelta(days=180))).group_by(func.strftime("%Y-%m", Expense.date)).order_by(func.strftime("%Y-%m", Expense.date)).all()
    return jsonify({"categories": {"labels": [r[0] for r in rows], "values": [r[1] for r in rows]}, "monthly": {"labels": [r[0] for r in monthly_rows], "values": [r[1] for r in monthly_rows]}})


@main.route("/reports")
@login_required
def reports():
    period = request.args.get("period", "monthly"); today = date.today()
    days = {"daily": 1, "weekly": 7, "monthly": 31, "yearly": 365}.get(period, 31)
    start = today - timedelta(days=days-1)
    items = Expense.query.filter(Expense.user_id == current_user.id, Expense.date >= start).order_by(Expense.date.desc()).all()
    total = sum(x.amount for x in items)
    return render_template("reports.html", items=items, total=total, period=period, start=start)


@main.route("/reports/download/<fmt>")
@login_required
def download_report(fmt):
    start, _ = month_bounds(request.args.get("month")); items = Expense.query.filter(Expense.user_id == current_user.id, Expense.date >= start).order_by(Expense.date).all()
    if fmt == "csv":
        output = io.StringIO(); writer = csv.writer(output); writer.writerow(["Date", "Expense", "Category", "Amount", "Notes"])
        for i in items: writer.writerow([i.date, i.title, i.category.name, i.amount, i.notes or ""])
        return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=expense-report.csv"})
    buffer = io.BytesIO(); pdf = canvas.Canvas(buffer, pagesize=letter); pdf.setTitle("Expense Report"); pdf.drawString(50, 750, "Expense Tracker — Monthly Report")
    y = 720
    for item in items:
        pdf.drawString(50, y, f"{item.date} | {item.title} ({item.category.name}) | ₹{item.amount:,.2f}"); y -= 20
        if y < 50: pdf.showPage(); y = 750
    pdf.save(); buffer.seek(0)
    return Response(buffer.getvalue(), mimetype="application/pdf", headers={"Content-Disposition": "attachment; filename=expense-report.pdf"})


@main.route("/api/ai", methods=["POST"])
@login_required
def ai_advice():
    payload = request.get_json(silent=True) or {}; question = str(payload.get("question", "Give me a monthly financial summary."))[:500]
    if not current_app.config["OPENAI_API_KEY"]: return jsonify({"error": "Set OPENAI_API_KEY in your .env file to enable AI advice."}), 503
    start, end = month_bounds(); items = Expense.query.filter(Expense.user_id == current_user.id, Expense.date.between(start, end)).all()
    summary = ", ".join(f"{x.category.name}: ₹{x.amount:.0f}" for x in items) or "No expenses this month"
    try:
        from openai import OpenAI
        client = OpenAI(api_key=current_app.config["OPENAI_API_KEY"])
        prompt = f"You are a helpful financial coach. Use only this spending data: {summary}. Question: {question}. Give concise, practical advice; do not provide investment, tax, or legal advice."
        response = client.responses.create(model=current_app.config["OPENAI_MODEL"], input=prompt)
        return jsonify({"answer": response.output_text})
    except Exception as exc:
        logging.exception("AI request failed")
        return jsonify({"error": "The AI service could not be reached. Check your API key and model configuration."}), 502
