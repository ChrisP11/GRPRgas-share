from django import forms
from django.contrib.auth.forms import PasswordChangeForm
import re

class DateForm(forms.Form):
    gDate = forms.DateField(
        widget=forms.DateInput(attrs={
            'type': 'date',  # HTML5 date picker
            'class': 'form-control',
        }),
        label='Select a date',
    )

class CustomPasswordChangeForm(PasswordChangeForm):
    def clean_new_password1(self):
        password = self.cleaned_data.get('new_password1')
        if len(password) < 8:
            raise forms.ValidationError("Password must be at least 8 characters long.")
        if not re.search(r'[A-Z]', password):
            raise forms.ValidationError("Password must contain at least one uppercase letter.")
        if not re.search(r'[a-z]', password):
            raise forms.ValidationError("Password must contain at least one lowercase letter.")
        if not re.search(r'[0-9]', password) and not re.search(r'[\W_]', password):
            raise forms.ValidationError("Password must contain at least one number or symbol.")
        return password