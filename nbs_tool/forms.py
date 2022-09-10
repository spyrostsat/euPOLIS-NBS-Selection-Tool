from flask_wtf import FlaskForm, RecaptchaField
from flask_login import current_user
from wtforms import StringField, PasswordField, EmailField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Length, EqualTo, ValidationError
from nbs_tool.models import User

class RegistrationForm(FlaskForm):
    username = StringField(label="Username", validators=[DataRequired(), Length(min=4, max=20)])
    email = EmailField(label="Email", validators=[DataRequired()])
    password = PasswordField(label="Password", validators=[DataRequired(), Length(min=6),
                                                           EqualTo('confirm_password', message='Passwords must match')])
    confirm_password = PasswordField(label="Confirm Password", validators=[DataRequired(), Length(min=6)])
    recaptcha = RecaptchaField()
    submit = SubmitField(label="Sign Up")

    # I don't need to call these custom validators anywhere. I gave these exact names 'validate_{field}' so that
    # flask knows these are validators, and it is automatically checking them when submiting the registration form
    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user:
            raise ValidationError('This username is taken. Please use a different one.')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('This email is taken. Please use a different one.')


class LoginForm(FlaskForm):
    email = EmailField(label="Email", validators=[DataRequired()])
    password = PasswordField(label="Password", validators=[DataRequired(), Length(min=6)])
    recaptcha = RecaptchaField()
    remember = BooleanField(label="Remember Me")
    submit = SubmitField(label="Login")


class UpdateAccountForm(FlaskForm):
    username = StringField(label="Username", validators=[DataRequired(), Length(min=4, max=20)])
    email = EmailField(label="Email", validators=[DataRequired()])
    submit = SubmitField(label="Update Account Settings")

    def validate_username(self, username):
        if username.data != current_user.username:
            user = User.query.filter_by(username=username.data).first()
            if user:
                raise ValidationError('This username is taken. Please use a different one.')

    def validate_email(self, email):
        if email.data != current_user.email:
            user = User.query.filter_by(email=email.data).first()
            if user:
                raise ValidationError('This email is taken. Please use a different one.')


class RequestResetForm(FlaskForm):
    email = EmailField(label="Email", validators=[DataRequired()])
    submit = SubmitField(label="Request Password Reset")

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user is None:
            raise ValidationError('There is no account with that email.')


class ResetPasswordForm(FlaskForm):
    password = PasswordField(label="New Password", validators=[DataRequired(), Length(min=6),
                                                           EqualTo('confirm_password', message='Passwords must match')])
    confirm_password = PasswordField(label="Confirm New Password", validators=[DataRequired(), Length(min=6)])
    submit = SubmitField(label="Reset Password")
