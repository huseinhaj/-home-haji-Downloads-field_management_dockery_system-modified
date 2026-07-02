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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Load all exams initially or filtered by exam_type if provided in data
        exam_type = self.data.get('exam_type')
        if exam_type:
            self.fields['exam'].queryset = Exam.objects.filter(exam_type=exam_type).order_by('-year', '-date')
        else:
            self.fields['exam'].queryset = Exam.objects.all().order_by('-year', '-date')

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

