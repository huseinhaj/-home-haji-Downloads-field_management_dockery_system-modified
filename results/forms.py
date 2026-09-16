import json

from django import forms
from django.core.exceptions import ValidationError
import pandas as pd

from .models import Exam, Subject, TeacherAccount
from .utils import extract_subject_columns, load_results_dataframe

class ExamUploadForm(forms.Form):
    EXAM_TYPE_CHOICES = [('', '--- Select Exam Type ---'), *Exam.EXAM_TYPE_CHOICES]

    exam_type = forms.ChoiceField(
        choices=EXAM_TYPE_CHOICES,
        required=True,
        widget=forms.Select(attrs={
            'class': 'form-control',
            'hx-get': '/filter_exams/',
            'hx-target': '#id_exam',
            'hx-trigger': 'change'
        })
    )

    exam = forms.ModelChoiceField(
        queryset=Exam.objects.none(),
        widget=forms.Select(attrs={'class': 'form-control', 'id': 'id_exam'}),
        required=True,
    )

    file = forms.FileField(
        label='Upload Results File',
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.xlsx,.csv'}),
        required=True,
    )

    def __init__(self, *args, school=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Scoped to the academic officer's own school; load all their exams
        # initially, or filtered by exam_type if provided in data.
        base_qs = Exam.objects.filter(school=school) if school else Exam.objects.none()
        exam_type = self.data.get('exam_type')
        if exam_type:
            self.fields['exam'].queryset = base_qs.filter(exam_type=exam_type).order_by('-year', '-date')
        else:
            self.fields['exam'].queryset = base_qs.order_by('-year', '-date')

    def clean_file(self):
        file = self.cleaned_data.get('file')
        if not file:
            raise ValidationError("No file was uploaded.")

        try:
            df = load_results_dataframe(file)

            required_columns = ['First Name', 'Last Name', 'Gender']
            for col in required_columns:
                if col not in df.columns:
                    raise ValidationError(f"Missing required student column: {col}")

            subject_cols = extract_subject_columns(df)
            if not subject_cols:
                raise ValidationError("No subject columns found. Ensure the file has subject columns beyond First Name, Last Name, and Gender.")

            # Check all subject columns have numeric values
            for col in [column for column in subject_cols if column in subject_names]:
                non_null = df[col].dropna()
                if not non_null.empty and pd.to_numeric(non_null, errors='coerce').isna().any():
                    raise ValidationError(f"Subject '{col}' contains non-numeric values. All scores must be numbers.")

            file.seek(0)
        except ValidationError:
            raise
        except Exception as e:
            raise ValidationError(f"Error reading file: {str(e)}")

        return file

    def clean(self):
        cleaned_data = super().clean()
        exam_type = cleaned_data.get('exam_type')
        exam = cleaned_data.get('exam')
        if exam_type and exam and exam.exam_type != exam_type:
            raise ValidationError("Selected exam doesn't match the selected exam type.")
        return cleaned_data


class TeacherAccountForm(forms.ModelForm):
    def __init__(self, *args, school=None, **kwargs):
        super().__init__(*args, **kwargs)
        from .utils import subjects_for_school
        if 'subjects' in self.fields:
            self.fields['subjects'].queryset = subjects_for_school(school)

    class Meta:
        model = TeacherAccount
        fields = ['email', 'full_name', 'role', 'subjects']
        widgets = {
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'full_name': forms.TextInput(attrs={'class': 'form-control'}),
            'role': forms.Select(attrs={'class': 'form-control'}),
            'subjects': forms.SelectMultiple(attrs={'class': 'form-control'}),
        }

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if TeacherAccount.objects.filter(email__iexact=email).exists():
            raise ValidationError("Email hii tayari ipo kwenye mfumo.")
        return email


class TeacherSubjectsForm(forms.ModelForm):
    """Edit role + subjects for an existing teacher account."""
    def __init__(self, *args, school=None, **kwargs):
        super().__init__(*args, **kwargs)
        from .utils import subjects_for_school
        if 'subjects' in self.fields:
            self.fields['subjects'].queryset = subjects_for_school(school)

    class Meta:
        model = TeacherAccount
        fields = ['role', 'subjects']
        widgets = {
            'role': forms.Select(attrs={'class': 'form-control'}),
            'subjects': forms.SelectMultiple(attrs={'class': 'form-control', 'size': 8}),
        }


class TeacherSelfSubjectsForm(forms.ModelForm):
    """Self-service: a teacher picks the subject(s) they teach themselves.

    Deliberately excludes 'role' — a teacher must never be able to grant
    themselves academic access through this form.

    Masomo yanayoonekana yanalingana na aina ya shule (primary/secondary)
    kupitia subjects_for_school — msingi haoni Physics, sekondari haoni
    Hisabati. Shule bila level (None) inaona yote kama zamani.
    """

    def __init__(self, *args, school=None, **kwargs):
        super().__init__(*args, **kwargs)
        from .utils import subjects_for_school
        if 'subjects' in self.fields:
            self.fields['subjects'].queryset = subjects_for_school(school)

    class Meta:
        model = TeacherAccount
        fields = ['subjects']
        widgets = {
            'subjects': forms.CheckboxSelectMultiple(),
        }



class MultiFileInput(forms.FileInput):
    """FileInput inayokubali files nyingi kwa wakati mmoja (Django 5+)."""
    allow_multiple_selected = True


class ScanUploadForm(forms.Form):
    """Picha za karatasi zilizoscaniwa (kutoka ADF au folder)."""
    images = forms.FileField(
        label='Picha za karatasi',
        widget=MultiFileInput(attrs={'accept': 'image/*'}),
    )
    note = forms.CharField(
        label='Maelezo (hiari)', max_length=200, required=False,
        widget=forms.TextInput(attrs={'class': 'input',
                                      'placeholder': 'Mf: Stack ya 1'}),
    )


class ScanKeyForm(forms.Form):
    """Answer key kwa muundo wa JSON: {"1": "A", "2": "C", ...}"""
    key = forms.CharField(
        label='Answer key (JSON)',
        widget=forms.Textarea(attrs={'rows': 10, 'style': 'font-family:monospace'}),
    )

    def clean_key(self):
        raw = self.cleaned_data['key'].strip()
        if not raw:
            return {}
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            raise forms.ValidationError('Muundo wa JSON si sahihi.')
        if not isinstance(obj, dict):
            raise forms.ValidationError('Inabidi kuwa dictionary: {"1": "A", ...}')
        clean = {}
        for k, v in obj.items():
            v = str(v).strip().upper()
            if v not in ('A', 'B', 'C', 'D'):
                raise forms.ValidationError(
                    f'Swali {k}: jibu linabidi liwe A, B, C au D (limewekwa: {v})')
            clean[str(k).strip()] = v
        return clean
