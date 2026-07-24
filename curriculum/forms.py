from django import forms
from field_app.models import LogbookEntry


class SchemeOfWorkForm(forms.Form):
    education_level = forms.ChoiceField(
        choices=[],
        widget=forms.Select(attrs={'class': 'form-control', 'id': 'education_level'}),
        label="Education Level"
    )
    class_level = forms.ChoiceField(
        choices=[],
        widget=forms.Select(attrs={'class': 'form-control', 'id': 'class_level'}),
        label="Class",
        required=True
    )
    subject = forms.ChoiceField(
        choices=[],
        widget=forms.Select(attrs={'class': 'form-control', 'id': 'subject'}),
        label="Subject",
        required=True
    )
    term = forms.ChoiceField(
        choices=[('I', 'Term I'), ('II', 'Term II'), ('III', 'Term III')],
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    year = forms.IntegerField(initial=2026, min_value=2000, max_value=2100,
                              widget=forms.NumberInput(attrs={'class': 'form-control'}))
    syllabus = forms.CharField(initial='New Syllabus',
                               widget=forms.TextInput(attrs={'class': 'form-control'}))
    total_weeks = forms.IntegerField(min_value=1, max_value=52,
                                     widget=forms.NumberInput(attrs={'class': 'form-control'}))
    periods_per_week = forms.IntegerField(min_value=1, max_value=50,
                                          widget=forms.NumberInput(attrs={'class': 'form-control'}))
    start_date = forms.DateField(required=False,
                                 widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}))
    end_date = forms.DateField(required=False,
                               widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}))
    reference_source = forms.ChoiceField(
        choices=[],
        widget=forms.Select(attrs={'class': 'form-control', 'id': 'reference_source'}),
        label="Reference Source",
        required=False
    )
    reference_file = forms.FileField(
        required=False,
        widget=forms.FileInput(attrs={'class': 'form-control', 'id': 'reference_file'}),
        label="Or Upload Reference"
    )
    teacher_name = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control'}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from field_app.models import EducationLevel, Subject, Textbook

        self.fields['education_level'].choices = [('', 'Select Education Level')] + [
            (level.id, level.name) for level in EducationLevel.objects.all()
        ]
        self.fields['reference_source'].choices = [('', 'Select Reference Source')] + [
            (textbook.id, f"{textbook.title} ({textbook.get_education_level_display()})")
            for textbook in Textbook.objects.filter(is_active=True)
        ]


class LogbookForm(forms.ModelForm):
    class Meta:
        model = LogbookEntry
        fields = [
            'other_activities',
            'challenges_faced',
            'lessons_learned',
        ]
        widgets = {
            'other_activities': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Mikutano, majukumu ya shule, ziara, n.k...',
                'class': 'form-control',
            }),
            'challenges_faced': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Changamoto ulizokutana nazo leo...',
                'class': 'form-control',
            }),
            'lessons_learned': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Mafunzo na tafakari ya kibinafsi...',
                'class': 'form-control',
            }),
        }
        labels = {
            'other_activities': 'Shughuli Nyingine (Zisizo za Kufundisha)',
            'challenges_faced': 'Changamoto / Vikwazo',
            'lessons_learned': 'Tafakari ya Kibinafsi / Mafunzo',
        }
