from django import forms
from .models import SchemeOfWork
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth import get_user_model
User = get_user_model()
from field_app.models import CustomUser 
from .models import LogbookEntry
from .models import StudentTeacher
# field_app/forms.py
from .models import LogbookEntry, StudentTeacher, Region  # 🔴 ADD Region HERE
from django import forms
from .models import Assessor, School

class AssessorLoginForm(AuthenticationForm):
    username = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Username or Email',
            'autocomplete': 'username'
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Password',
            'autocomplete': 'current-password'
        })
    )
class DocumentUploadForm(forms.Form):
    ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'txt', 'csv', 'xlsx', 'xls'}
    MAX_SIZE_MB = 10

    file = forms.FileField()

    def clean_file(self):
        f = self.cleaned_data['file']
        ext = f.name.rsplit('.', 1)[-1].lower() if '.' in f.name else ''
        if ext not in self.ALLOWED_EXTENSIONS:
            raise forms.ValidationError(
                f"Aina ya faili hairuhusiwi. Ruhusiwa: {', '.join(sorted(self.ALLOWED_EXTENSIONS))}"
            )
        if f.size > self.MAX_SIZE_MB * 1024 * 1024:
            raise forms.ValidationError(f"Faili ni kubwa mno. Ukubwa wa juu: {self.MAX_SIZE_MB}MB")
        return f

# Custom login form using email instead of username
class CustomLoginForm(AuthenticationForm):
    username = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'academic-input w-full pl-10 pr-3 py-3 rounded-lg',
            'placeholder': 'student@university.edu',
            'id': 'email'
        }),
        label='University Email'
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'academic-input w-full pl-10 pr-10 py-3 rounded-lg',
            'placeholder': '••••••••',
            'id': 'password'
        }),
        label='Password'
    )


class StudentRegistrationForm(UserCreationForm):
    full_name = forms.CharField(max_length=100, label="Full Name")
    phone_number = forms.CharField(max_length=15, label="Phone Number")

    class Meta:
        model = CustomUser
        fields = ('email', 'password1', 'password2', 'full_name', 'phone_number')  # hizi mbili za mwisho si field za model moja kwa moja

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = user.email  # Optional if username not used
        if commit:
            user.save()
            StudentTeacher.objects.create(
                user=user,
                full_name=self.cleaned_data['full_name'],
                phone_number=self.cleaned_data['phone_number']
            )
        return user


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

class StudentTeacherForm(forms.ModelForm):
    class Meta:
        model = StudentTeacher
        fields = ['full_name', 'phone_number']
# forms.py


# forms.py - REPLACE RegionFieldInputForm with this

class RegionFieldInputForm(forms.Form):
    academic_year = forms.CharField(
        max_length=20,
        label="Academic Year",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'e.g., 2025/2026'
        }),
        help_text="Format: YYYY/YYYY (e.g., 2025/2026)"
    )
    
    regions_to_hide = forms.CharField(
        label="Regions to HIDE (PIN)",
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 5,
            'placeholder': 'Dar es Salaam, Arusha, Mwanza, Kilimanjaro, Tanga'
        }),
        help_text="Enter region names separated by commas. These regions will be HIDDEN from students.",
        required=True
    )
    
    def clean_academic_year(self):
        year = self.cleaned_data['academic_year']
        if '/' not in year:
            raise forms.ValidationError("Use format YYYY/YYYY (e.g., 2025/2026)")
        
        parts = year.split('/')
        if len(parts) != 2:
            raise forms.ValidationError("Use format YYYY/YYYY (e.g., 2025/2026)")
        
        try:
            start_year = int(parts[0])
            end_year = int(parts[1])
            if end_year != start_year + 1:
                raise forms.ValidationError("End year should be start year + 1 (e.g., 2025/2026)")
        except ValueError:
            raise forms.ValidationError("Years must be numbers")
        
        return year
    
    def clean_regions_to_hide(self):
        regions = self.cleaned_data['regions_to_hide']
        # Clean and validate region names
        region_list = [r.strip().lower() for r in regions.split(',') if r.strip()]
        
        if not region_list:
            raise forms.ValidationError("Please enter at least one region name")
        
        # Check if regions exist in database
        existing_regions = Region.objects.values_list('name', flat=True)
        existing_regions_lower = [r.lower() for r in existing_regions]
        
        invalid_regions = []
        for region in region_list:
            if region not in existing_regions_lower:
                invalid_regions.append(region)
        
        if invalid_regions:
            raise forms.ValidationError(
                f"These regions don't exist: {', '.join(invalid_regions)}. "
                f"Available regions: {', '.join(existing_regions[:10])}..."
            )
        
        # Return original case for display
        original_case_regions = []
        for r in region_list:
            for er in existing_regions:
                if er.lower() == r:
                    original_case_regions.append(er)
                    break
        
        return original_case_regions

class BulkAssignForm(forms.Form):
    assessors = forms.ModelMultipleChoiceField(
        queryset=Assessor.objects.filter(is_active=True),
        widget=forms.SelectMultiple(attrs={'class': 'form-control select2-multiple'}),
        required=True,
        label="Select Assessors"
    )
    
    schools = forms.ModelMultipleChoiceField(
        queryset=School.objects.all(),
        widget=forms.SelectMultiple(attrs={'class': 'form-control select2-multiple'}),
        required=True,
        label="Select Schools"
    )
    
    assessment_date = forms.DateField(
        required=True,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        label="Assessment Date"
    )
    
    def clean(self):
        cleaned_data = super().clean()
        assessors = cleaned_data.get('assessors', [])
        
        # Check each assessor has email
        for assessor in assessors:
            if not assessor.email:
                raise forms.ValidationError(
                    f"Assessor '{assessor.full_name}' doesn't have an email. "
                    f"Please add email in admin panel first."
                )
        
        return cleaned_data
# forms.py


# forms.py - Ongeza hii

class SchemeOfWorkForm(forms.Form):
    education_level = forms.ChoiceField(
        choices=[],  # Itajazwa dynamically
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
    year = forms.IntegerField(initial=2026, min_value=2000, max_value=2100, widget=forms.NumberInput(attrs={'class': 'form-control'}))
    syllabus = forms.CharField(initial='New Syllabus', widget=forms.TextInput(attrs={'class': 'form-control'}))
    total_weeks = forms.IntegerField(min_value=1, max_value=52, widget=forms.NumberInput(attrs={'class': 'form-control'}))
    periods_per_week = forms.IntegerField(min_value=1, max_value=50, widget=forms.NumberInput(attrs={'class': 'form-control'}))
    start_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}))
    end_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}))
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
        from .models import EducationLevel, ClassLevel, Subject, Textbook
        
        # Education levels
        self.fields['education_level'].choices = [('', 'Select Education Level')] + [
            (level.id, level.name) for level in EducationLevel.objects.all()
        ]
        
        # Reference sources (textbooks)
        self.fields['reference_source'].choices = [('', 'Select Reference Source')] + [
            (textbook.id, f"{textbook.title} ({textbook.get_education_level_display()})") 
            for textbook in Textbook.objects.filter(is_active=True)
        ]
