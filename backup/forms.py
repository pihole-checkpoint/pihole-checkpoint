from django import forms
from .models import PiholeConfig


class PiholeConfigForm(forms.ModelForm):
    """Form for Pi-hole configuration."""

    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        required=True
    )

    class Meta:
        model = PiholeConfig
        fields = [
            'name', 'pihole_url', 'password', 'verify_ssl',
            'backup_frequency', 'backup_time', 'backup_day',
            'max_backups', 'max_age_days', 'is_active'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'pihole_url': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://192.168.1.100'}),
            'verify_ssl': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'backup_frequency': forms.Select(attrs={'class': 'form-select'}),
            'backup_time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'backup_day': forms.Select(attrs={'class': 'form-select'}),
            'max_backups': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'max_age_days': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make password not required when editing existing config
        if self.instance and self.instance.pk:
            self.fields['password'].required = False
            self.fields['password'].help_text = 'Leave blank to keep current password'

    def clean_password(self):
        password = self.cleaned_data.get('password')
        # If editing and password is blank, keep the existing one
        if self.instance and self.instance.pk and not password:
            return self.instance.password
        return password


class LoginForm(forms.Form):
    """Simple login form."""
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control'}))
