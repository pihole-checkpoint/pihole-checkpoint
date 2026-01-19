from django import forms

from .models import PiholeConfig


class PiholeConfigForm(forms.ModelForm):
    """Form for Pi-hole backup schedule configuration.

    Note: Pi-hole connection settings (URL, password, SSL) are now configured
    via environment variables. See the Settings page for connection status.
    """

    class Meta:
        model = PiholeConfig
        fields = [
            "name",
            "backup_frequency",
            "backup_time",
            "backup_day",
            "max_backups",
            "max_age_days",
            "is_active",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "backup_frequency": forms.Select(attrs={"class": "form-select"}),
            "backup_time": forms.TimeInput(attrs={"class": "form-control", "type": "time"}),
            "backup_day": forms.Select(attrs={"class": "form-select"}),
            "max_backups": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "max_age_days": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class LoginForm(forms.Form):
    """Simple login form."""

    password = forms.CharField(widget=forms.PasswordInput(attrs={"class": "form-control"}))
