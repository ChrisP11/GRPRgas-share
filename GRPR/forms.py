from django import forms

class DateForm(forms.Form):
    gDate = forms.DateField(
        widget=forms.DateInput(attrs={
            'type': 'date',  # HTML5 date picker
            'class': 'form-control',
        }),
        label='Select a date',
    )
