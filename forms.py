from datetime import date
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, FloatField, DateField, TextAreaField, SelectField, SubmitField
from wtforms.validators import DataRequired, Email, Length, EqualTo, NumberRange, Optional


class RegisterForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired(), Length(max=80)])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=120)])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=8)])
    confirm_password = PasswordField("Confirm password", validators=[DataRequired(), EqualTo("password")])
    submit = SubmitField("Create account")


class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired()])
    submit = SubmitField("Sign in")


class ExpenseForm(FlaskForm):
    title = StringField("Expense", validators=[DataRequired(), Length(max=120)])
    amount = FloatField("Amount", validators=[DataRequired(), NumberRange(min=0.01)])
    date = DateField("Date", default=date.today, validators=[DataRequired()])
    category_id = SelectField("Category", coerce=int, validators=[DataRequired()])
    custom_category = StringField("New category (optional)", validators=[Optional(), Length(max=60)])
    notes = TextAreaField("Notes", validators=[Optional(), Length(max=1000)])
    submit = SubmitField("Save expense")


class IncomeForm(FlaskForm):
    source = StringField("Source", validators=[DataRequired(), Length(max=120)])
    amount = FloatField("Amount", validators=[DataRequired(), NumberRange(min=0.01)])
    date = DateField("Date", default=date.today, validators=[DataRequired()])
    notes = TextAreaField("Notes", validators=[Optional(), Length(max=1000)])
    submit = SubmitField("Save income")


class BudgetForm(FlaskForm):
    amount = FloatField("Monthly budget", validators=[DataRequired(), NumberRange(min=0.01)])
    submit = SubmitField("Save budget")
