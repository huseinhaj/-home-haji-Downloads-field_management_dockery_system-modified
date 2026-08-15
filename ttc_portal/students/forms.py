from django import forms
from django.contrib.auth import get_user_model
from .models import Student

User = get_user_model()


class StudentRegistrationForm(forms.Form):
    """Registration for student teachers (self-service)."""

    college = forms.ModelChoiceField(
        queryset=None, label='Chuo Chako',
        widget=forms.Select(attrs={'class': 'form-control', 'id': 'id_college'}),
    )
    program = forms.ModelChoiceField(
        queryset=None, required=False, label='Programu (Diploma)',
        widget=forms.Select(attrs={'class': 'form-control', 'id': 'id_program'}),
    )
    full_name = forms.CharField(
        max_length=255, label='Jina Kamili',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'mfano: Juma Hassan Mussa'}),
    )
    registration_number = forms.CharField(
        max_length=50, label='Namba ya Usajili (Registration Number)',
        help_text='Ikiwa hujapata bado, weka barua pepe yako itatumika kuingia.',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'mfano: KAS/2026/014'}),
    )
    admission_year = forms.IntegerField(
        initial=2026, min_value=2000, max_value=2100, label='Mwaka wa Kujiunga',
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
    )
    year_of_study = forms.ChoiceField(
        choices=[(1, 'Mwaka wa 1'), (2, 'Mwaka wa 2'), (3, 'Mwaka wa 3')], label='Mwaka wa Masomo',
        widget=forms.Select(attrs={'class': 'form-control'}),
    )
    gender = forms.ChoiceField(
        choices=[('', '--- Chagua ---'), ('M', 'Male'), ('F', 'Female')],
        required=False, label='Jinsia',
        widget=forms.Select(attrs={'class': 'form-control'}),
    )
    phone_number = forms.CharField(
        max_length=15, label='Namba ya Simu',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'mfano: 0712 345 678'}),
    )
    email = forms.EmailField(
        label='Barua Pepe (Email)', required=False,
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'jina@gmail.com'}),
    )
    password = forms.CharField(
        min_length=6, label='Nywila',
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Weka nywila (angalau herufi 6)'}),
    )
    confirm_password = forms.CharField(
        label='Rudia Nywila',
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Andika nywila tena'}),
    )

    def __init__(self, *args, **kwargs):
        from colleges.models import College, Program
        super().__init__(*args, **kwargs)
        self.fields['college'].queryset = College.objects.filter(is_active=True)
        self.fields['program'].queryset = Program.objects.all()

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get('password')
        p2 = cleaned.get('confirm_password')
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError('Nywila mbili hazifanani. Tafadhali rudia.')
        reg_no = (cleaned.get('registration_number') or '').strip()
        email = (cleaned.get('email') or '').strip()
        username = reg_no or email
        if not username:
            raise forms.ValidationError('Tafadhali jaza namba ya usajili AU barua pepe.')
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError(
                f'Akaunti yenye "{username}" tayari ipo. Ikiwa ni yako, ingia moja kwa moja.'
            )
        # Programu lazima iwe ya chuo kilichochaguliwa (server-side guard)
        college = cleaned.get('college')
        program = cleaned.get('program')
        if program and college and program.college_id != college.id:
            self.add_error(
                'program', 'Programu hii si ya chuo ulichokichagua. Tafadhali chagua tena.'
            )
        return cleaned


class CompleteStudentForm(forms.Form):
    """Kamilisha usajili kwa akaunti ya mwanafunzi ambayo bado haina Student profile.

    Akaunti kama hizi zinaweza kutokea kama mtumiaji aliundwa kupitia Django admin
    (CustomUser tu, bila Student). Badala ya kumdundisha, mwanafunzi anajaza chuo
    chake na taarifa nyingine, na profile inaundwa kwenye akaunti yake ya sasa.
    """

    college = forms.ModelChoiceField(
        queryset=None, label='Chuo Chako',
        widget=forms.Select(attrs={'class': 'form-control', 'id': 'id_college'}),
    )
    program = forms.ModelChoiceField(
        queryset=None, required=False, label='Programu (Diploma)',
        widget=forms.Select(attrs={'class': 'form-control', 'id': 'id_program'}),
    )
    full_name = forms.CharField(
        max_length=255, label='Jina Kamili',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'mfano: Juma Hassan Mussa'}),
    )
    registration_number = forms.CharField(
        max_length=50, label='Namba ya Usajili (Registration Number)',
        help_text='Inaonekana kwenye kitambulisho chako cha chuo — mfano: KAS/2026/014.',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'mfano: KAS/2026/014'}),
    )
    admission_year = forms.IntegerField(
        initial=2026, min_value=2000, max_value=2100, label='Mwaka wa Kujiunga',
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
    )
    year_of_study = forms.ChoiceField(
        choices=[(1, 'Mwaka wa 1'), (2, 'Mwaka wa 2'), (3, 'Mwaka wa 3')], label='Mwaka wa Masomo',
        widget=forms.Select(attrs={'class': 'form-control'}),
    )
    gender = forms.ChoiceField(
        choices=[('', '--- Chagua ---'), ('M', 'Male'), ('F', 'Female')],
        required=False, label='Jinsia',
        widget=forms.Select(attrs={'class': 'form-control'}),
    )
    phone_number = forms.CharField(
        max_length=15, label='Namba ya Simu',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'mfano: 0712 345 678'}),
    )
    email = forms.EmailField(
        label='Barua Pepe (Email)', required=False,
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'jina@gmail.com'}),
    )

    def __init__(self, *args, **kwargs):
        from colleges.models import College, Program
        super().__init__(*args, **kwargs)
        self.fields['college'].queryset = College.objects.filter(is_active=True)
        self.fields['program'].queryset = Program.objects.all()

    def clean_registration_number(self):
        reg_no = (self.cleaned_data.get('registration_number') or '').strip()
        if not reg_no:
            raise forms.ValidationError('Tafadhali jaza namba yako ya usajili.')
        if Student.objects.filter(registration_number__iexact=reg_no).exists():
            raise forms.ValidationError(
                f'Namba ya usajili "{reg_no}" tayari imetumika. Angalia tena.'
            )
        return reg_no

    def clean(self):
        cleaned = super().clean()
        # Programu lazima iwe ya chuo kilichochaguliwa (server-side guard)
        college = cleaned.get('college')
        program = cleaned.get('program')
        if program and college and program.college_id != college.id:
            self.add_error(
                'program', 'Programu hii si ya chuo ulichokichagua. Tafadhali chagua tena.'
            )
        return cleaned


class AdminStudentForm(StudentRegistrationForm):
    """College admin adds a student manually — password optional (auto default).

    The college is fixed to the admin's own college (hidden field, forced in the
    view) so an admin can never register a student into another college.
    """

    password = forms.CharField(
        required=False, min_length=6, label='Nywila (si lazima)',
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Wacha tupu kwa nywila ya mwisho = namba ya usajili'}),
    )
    confirm_password = forms.CharField(
        required=False, label='Rudia Nywila',
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Chuo kinawekwa kwa msimamizi — sio sehemu ya fomu inayoonekana
        self.fields['college'].required = False
        self.fields['college'].widget = forms.HiddenInput()
