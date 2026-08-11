from django import forms
from .models import FeeItem, Payment


class FeeItemForm(forms.ModelForm):
    class Meta:
        model = FeeItem
        fields = ['name', 'category', 'amount', 'academic_year', 'year_of_study',
                  'description', 'due_date', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'mfano: Ada ya Mwaka'}),
            'category': forms.Select(attrs={'class': 'form-control'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'mfano: 300000'}),
            'academic_year': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'mfano: 2026/2027'}),
            'year_of_study': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '1 au 2 (wazi = yote)'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'due_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class PaymentSubmissionForm(forms.Form):
    """Mwanafunzi anawasilisha malipo yake — msimamizi wa chuo anathibitisha."""

    amount = forms.DecimalField(
        max_digits=12, decimal_places=2, label='Kiasi Ulicholipa (TZS)',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'mfano: 300000'}),
    )
    method = forms.ChoiceField(
        choices=Payment.METHOD_CHOICES, label='Njia ya Malipo',
        widget=forms.Select(attrs={'class': 'form-control'}),
    )
    reference = forms.CharField(
        max_length=100, label='Namba ya Kumbukumbu (Reference)',
        help_text='Kumbukumbu kutoka M-Pesa/Tigo/Benki ulipolipa kwa namba ya malipo.',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'mfano: SWE7K9L2M1'}),
    )
    notes = forms.CharField(
        max_length=255, required=False, label='Maelezo (si lazima)',
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
