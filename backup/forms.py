from django import forms


class LoginForm(forms.Form):
    """Simple login form."""

    password = forms.CharField(widget=forms.PasswordInput(attrs={"class": "form-control"}))
