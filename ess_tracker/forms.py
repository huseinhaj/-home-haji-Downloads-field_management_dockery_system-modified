from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model
from django.db.models import Q

from .models import MODE_CHOICES, Holiday, SubTask, Task, TeacherProfile

CustomUser = get_user_model()


class TeacherRegistrationForm(forms.Form):
    """Kujisajili kwa mwalimu wa ESS kwa kutumia username na password ZAKE ZA ESS."""

    ess_username = forms.CharField(label='Username ya ESS (e-Tendaji)', max_length=255)
    password1 = forms.CharField(label='Password ya ESS', widget=forms.PasswordInput(
        attrs={'placeholder': '********', 'autocomplete': 'new-password'}))
    password2 = forms.CharField(
        label='Thibitisha password', widget=forms.PasswordInput(
            attrs={'placeholder': '********', 'autocomplete': 'new-password'}))

    def clean_ess_username(self):
        u = (self.cleaned_data.get('ess_username') or '').strip()
        if not u:
            raise forms.ValidationError('Weka username yako ya ESS.')
        if TeacherProfile.objects.filter(ess_username__iexact=u).exists():
            raise forms.ValidationError('Username hii ya ESS tayari imesajiliwa. Ingia tu.')
        return u

    def clean(self):
        cleaned = super().clean()
        pw1 = cleaned.get('password1')
        pw2 = cleaned.get('password2')
        if pw1 and pw1 != pw2:
            self.add_error('password2', 'Password mbili hazilingani.')
        return cleaned

    def build_user_and_profile(self) -> tuple:
        """Unda CustomUser (usiotumika moja kwa moja) + TeacherProfile ya ESS.

        CustomUser ina password isiyotumika (mwalimu hakimbaji kwa email);
        kuingia ni kwa ESS username + password pekee.
        """
        username = self.cleaned_data['ess_username'].strip()
        email = _ess_email_for_username(username)
        base, i = email, 0
        while CustomUser.objects.filter(email=email).exists():
            i += 1
            root = base.split('@')[0]
            email = f'{root}-{i}@eutendaji.moe.go.tz'
        user = CustomUser.objects.create_user(email=email, password=None)
        user.is_active = True
        user.save()
        profile = TeacherProfile(user=user, full_name=username, ess_username=username)
        profile.set_ess_password(self.cleaned_data['password1'])
        profile.save()
        return user, profile


def _ess_email_for_username(username: str) -> str:
    import re
    safe = re.sub(r'[^a-z0-9._-]+', '', username.lower())
    return f'{safe}@eutendaji.moe.go.tz'


class ProfileForm(forms.ModelForm):
    ess_password = forms.CharField(
        label='Password yako ya ESS (e-Tendaji)',
        required=False,
        widget=forms.PasswordInput(render_value=True),
        help_text='Imehifadhiwa kwa usimbaji. Ikitolewa tupu, password ya zamani inasalia.')

    class Meta:
        model = TeacherProfile
        fields = ['full_name', 'phone', 'school', 'ess_username']
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'school': forms.Select(attrs={'class': 'form-select'}),
            'ess_username': forms.TextInput(attrs={'class': 'form-control'}),
        }
        labels = {
            'ess_username': 'Username yako ya ESS (e-Tendaji)',
            'full_name': 'Majina kamili',
            'school': 'Shule',
        }

    school_open = forms.DateField(
        label='Tarehe shule inavyofunguliwa (mwaka huu)',
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        help_text='Kuanzia tarehe hii mfumo utaanza kujaza maendeleo yako.',
        input_formats=['%Y-%m-%d', '%d/%m/%Y'])

    school_close = forms.DateField(
        label='Tarehe shule inavyofungwa (mwisho wa mwaka)',
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        help_text='Kufika tarehe hii sub-tasks zote zitakuwa zimefikia 100%.',
        input_formats=['%Y-%m-%d', '%d/%m/%Y'])

    entries_per_week = forms.ChoiceField(
        label='Mfumo ujaze maendeleo yako mara ngapi kwa wiki?',
        required=False,
        choices=[(2, 'Mara 2 kwa wiki'), (3, 'Mara 3 kwa wiki'),
                 (4, 'Mara 4 kwa wiki'), (5, 'Mara 5 kwa wiki')],
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text='Hesabu ya mwaka mzima (tarehe ya kufungua hadi kufunga) '
                  'itagawanywa kwa mara hizi ili ufikie 100% tarehe ya kufunga. '
                  'Mfumo hujaza siku zilizogawanywa kiotomatiki (mf. mara 3 = '
                  'Jumatatu, Jumatano, Ijumaa).')

    auto_subtasks = forms.ModelMultipleChoiceField(
        label='Sub-task za kujaza kiotomatiki',
        required=False,
        queryset=SubTask.objects.none(),
        widget=forms.SelectMultiple(attrs={'class': 'form-select', 'size': '10'}),
        help_text='Chagua sub-task ambazo mfumo ujaze kiotomatiki. '
                  'Bila kuchagua = sub-task zote zinazohitaji.')

    holidays = forms.ModelMultipleChoiceField(
        label='Likizo (chagua zinazohusu mwaka huu)',
        required=False,
        queryset=Holiday.objects.none(),
        widget=forms.SelectMultiple(attrs={'class': 'form-select', 'size': '6'}),
        help_text='Siku hizi zitatolewa kwenye hesabu ya siku 194 za shule.')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['school_open'].initial = self.instance.school_open
            self.fields['school_close'].initial = self.instance.school_close
            self.fields['entries_per_week'].initial = self.instance.entries_per_week
            self.fields['auto_subtasks'].queryset = SubTask.objects.filter(
                task__profile=self.instance).order_by('task_id', 'position')
            self.fields['auto_subtasks'].initial = self.instance.auto_subtask_ids()
            self.fields['holidays'].queryset = Holiday.objects.filter(
                Q(profile__isnull=True) | Q(profile=self.instance))
            self.fields['holidays'].initial = self.instance.holidays.all()
        else:
            self.fields['holidays'].queryset = Holiday.objects.filter(profile__isnull=True)

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get('full_name'):
            cleaned['full_name'] = self.instance.user.email or ''
        uname = (cleaned.get('ess_username') or '').strip()
        if uname:
            dup = TeacherProfile.objects.filter(ess_username__iexact=uname)
            if self.instance and self.instance.pk:
                dup = dup.exclude(pk=self.instance.pk)
            if dup.exists():
                self.add_error('ess_username',
                               'Username hii ya ESS inatumiwa na mwalimu mwingine.')
        open_d = cleaned.get('school_open')
        close_d = cleaned.get('school_close')
        if open_d and close_d and close_d <= open_d:
            self.add_error(
                'school_close',
                'Tarehe ya kufunga lazima iwe baada ya tarehe ya kufungua.')
        return cleaned

    def save(self, commit=True):
        profile = super().save(commit=False)
        new_pw = self.cleaned_data.get('ess_password')
        if new_pw:
            profile.set_ess_password(new_pw)
        elif not profile.ess_password:
            profile.ess_password = ''
        profile.school_open = self.cleaned_data.get('school_open')
        profile.school_close = self.cleaned_data.get('school_close')
        profile.entries_per_week = int(self.cleaned_data.get('entries_per_week') or 3)
        chosen = self.cleaned_data.get('auto_subtasks') or []
        profile.auto_subtasks = ','.join(str(s.id) for s in chosen)
        if commit:
            profile.save()
            profile.holidays.set(self.cleaned_data.get('holidays') or [])
        return profile


class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ['name', 'somo', 'kidato', 'topics_total', 'topics_taught',
                  'start', 'end']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control',
                                            'placeholder': 'TASK — mf. kutekeleza majukumu ya ufundishaji wa somo la hisabati...'}),
            'somo': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'hisabati'}),
            'kidato': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'kwanza'}),
            'topics_total': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'topics_taught': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'start': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'end': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        }
        labels = {
            'topics_total': 'Jumla ya mada za mwaka',
            'topics_taught': 'Mada zilizofundishwa hadi sasa',
        }

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('start') and cleaned.get('end') and cleaned['start'] > cleaned['end']:
            self.add_error('end', 'Tarehe ya mwisho lazima iwe baada ya tarehe ya kuanza.')
        return cleaned


class AutogenForm(forms.Form):
    """Vigezo vya kutengeneza sub-tasks 7 za kawaida (kama CSV v2)."""

    vila_per_week = forms.DecimalField(
        label='Vipindi kwa wiki', required=False, widget=forms.NumberInput(attrs={'class': 'form-control'}))
    week_count = forms.IntegerField(
        label='Jumla ya wiki', required=False, widget=forms.NumberInput(attrs={'class': 'form-control'}))
    maazimio = forms.IntegerField(initial=1, required=False,
                                  widget=forms.NumberInput(attrs={'class': 'form-control'}),
                                  help_text='Azimio la kazi: 1 kwa somo kwa mwaka')
    nukuu = forms.DecimalField(required=False, label='Nukuu (jumla ya mwaka)',
                               widget=forms.NumberInput(attrs={'class': 'form-control'}))
    zana = forms.DecimalField(required=False, label='Zana (jumla ya mwaka)',
                              widget=forms.NumberInput(attrs={'class': 'form-control'}))
    majaribio = forms.IntegerField(initial=6, required=False,
                                   widget=forms.NumberInput(attrs={'class': 'form-control'}))
    mitihani = forms.IntegerField(initial=4, required=False,
                                  widget=forms.NumberInput(attrs={'class': 'form-control'}))
    generate = forms.BooleanField(
        label='Tengeneza sub-tasks 7 za kawaida', required=False, initial=True)


class SubTaskEditForm(forms.ModelForm):
    class Meta:
        model = SubTask
        fields = ['description', 'mode', 'target', 'vila_per_week', 'week_count', 'actual_base']
        widgets = {
            'description': forms.TextInput(attrs={'class': 'form-control'}),
            'mode': forms.Select(attrs={'class': 'form-select'}, choices=MODE_CHOICES),
            'target': forms.NumberInput(attrs={'class': 'form-control', 'step': 'any'}),
            'vila_per_week': forms.NumberInput(attrs={'class': 'form-control', 'step': 'any'}),
            'week_count': forms.NumberInput(attrs={'class': 'form-control'}),
            'actual_base': forms.NumberInput(attrs={'class': 'form-control', 'step': 'any'}),
        }

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('mode') == 'periods':
            if not cleaned.get('vila_per_week') and not cleaned.get('week_count'):
                self.add_error('vila_per_week',
                               'Sub task ya vipindi kwa wiki inahitaji vila kwa wiki na wiki jumla.')
        return cleaned