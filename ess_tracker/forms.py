from django import forms

from .models import MODE_CHOICES, SubTask, Task, TeacherProfile


class ProfileForm(forms.ModelForm):
    ess_password = forms.CharField(
        label='Password ya ESS (e-Utendaji)',
        required=False,
        widget=forms.PasswordInput(render_value=True),
        help_text='Imehifadhiwa kwa usimbaji. Ikitolewa tupu tupu, password ya zamani inasalia.')

    class Meta:
        model = TeacherProfile
        fields = ['full_name', 'phone', 'school', 'ess_username']
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'school': forms.Select(attrs={'class': 'form-select'}),
            'ess_username': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get('full_name'):
            cleaned['full_name'] = self.instance.user.email or ''
        return cleaned

    def save(self, commit=True):
        profile = super().save(commit=False)
        new_pw = self.cleaned_data.get('ess_password')
        if new_pw:
            profile.set_ess_password(new_pw)
        elif not profile.ess_password:
            profile.ess_password = ''
        if commit:
            profile.save()
        return profile


class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ['name', 'somo', 'kidato', 'start', 'end']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control',
                                            'placeholder': 'TASK — mf. kutekeleza majukumu ya ufundishaji wa somo la hisabati...'}),
            'somo': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'hisabati'}),
            'kidato': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'kwanza'}),
            'start': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'end': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
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
    maazimio = forms.IntegerField(initial=2, required=False,
                                  widget=forms.NumberInput(attrs={'class': 'form-control'}))
    nukuu = forms.DecimalField(required=False, label='Nukuu (jumla ya mwaka)',
                               widget=forms.NumberInput(attrs={'class': 'form-control'}))
    zana = forms.DecimalField(required=False, label='Zana (jumla ya mwaka)',
                              widget=forms.NumberInput(attrs={'class': 'form-control'}))
    majaribio = forms.IntegerField(initial=5, required=False,
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