import re

from django import forms

from .models import PiholeConfig


class PiholeConfigForm(forms.ModelForm):
    """Form for Pi-hole backup configuration.

    Pi-hole connection settings (URL, password, SSL) are configured via
    environment variables using the env_prefix pattern. See ADR-0014.
    """

    class Meta:
        model = PiholeConfig
        fields = [
            "name",
            "env_prefix",
            "backup_frequency",
            "backup_time",
            "backup_day",
            "max_backups",
            "max_age_days",
            "is_active",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "env_prefix": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g., PRIMARY"}),
            "backup_frequency": forms.Select(attrs={"class": "form-select"}),
            "backup_time": forms.TimeInput(attrs={"class": "form-control", "type": "time"}),
            "backup_day": forms.Select(attrs={"class": "form-select"}),
            "max_backups": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "max_age_days": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean_env_prefix(self):
        value = self.cleaned_data.get("env_prefix", "").strip().upper()
        if value and not re.match(r"^[A-Z0-9_]+$", value):
            raise forms.ValidationError("Only letters, numbers, and underscores are allowed.")
        # Require non-empty prefix for new instances to avoid multiple configs
        # sharing the same legacy PIHOLE_URL/PIHOLE_PASSWORD env vars
        if not value and not (self.instance and self.instance.pk):
            raise forms.ValidationError("An environment variable prefix is required for new instances.")
        # Check uniqueness among other configs
        qs = PiholeConfig.objects.filter(env_prefix=value)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if value and qs.exists():
            raise forms.ValidationError(f"Another instance is already using the prefix '{value}'.")
        return value


class LoginForm(forms.Form):
    """Simple login form."""

    password = forms.CharField(widget=forms.PasswordInput(attrs={"class": "form-control"}))
