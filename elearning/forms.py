from django import forms
from django.utils.text import slugify
from .models import (
    Course, Module, Lesson, Quiz, Question, Assignment, AssignmentSubmission,
    Discussion, DiscussionReply, CourseReview, LearnerProfile, Announcement,
)


class LearnerProfileForm(forms.ModelForm):
    class Meta:
        model = LearnerProfile
        fields = ['full_name', 'phone_number', 'bio', 'avatar']
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Jina kamili'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Namba ya simu'}),
            'bio': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Kuhusu wewe...'}),
            'avatar': forms.FileInput(attrs={'class': 'form-control'}),
        }


class CourseForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = ['title', 'short_description', 'description', 'level', 'subject',
                  'education_level', 'thumbnail', 'is_free', 'price_tzs', 'is_published']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Jina la kozi'}),
            'short_description': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Maelezo mafupi'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 5, 'placeholder': 'Maelezo kamili ya kozi'}),
            'level': forms.Select(attrs={'class': 'form-select'}),
            'subject': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Hisabati, Kiswahili'}),
            'education_level': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Sekondari, Msingi'}),
            'thumbnail': forms.FileInput(attrs={'class': 'form-control'}),
            'is_free': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'price_tzs': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Bei kwa TZS'}),
            'is_published': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean_title(self):
        title = self.cleaned_data['title']
        if not self.instance.pk:
            slug = slugify(title)
            if Course.objects.filter(slug=slug).exists():
                raise forms.ValidationError("Kozi yenye jina hili tayari ipo. Tafadhali chagua jina lingine.")
        return title


class ModuleForm(forms.ModelForm):
    class Meta:
        model = Module
        fields = ['title', 'description', 'order']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Jina la moduli'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Maelezo ya moduli'}),
            'order': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
        }


class LessonForm(forms.ModelForm):
    class Meta:
        model = Lesson
        fields = ['module', 'title', 'content_type', 'content', 'video_url',
                  'video_embed', 'document', 'duration_minutes', 'order', 'is_published']
        widgets = {
            'module': forms.Select(attrs={'class': 'form-select'}),
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Jina la somo'}),
            'content_type': forms.Select(attrs={'class': 'form-select'}),
            'content': forms.Textarea(attrs={'class': 'form-control', 'rows': 10, 'placeholder': 'Maandishi ya somo...'}),
            'video_url': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://youtube.com/watch?v=...'}),
            'video_embed': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': '<iframe>...</iframe>'}),
            'document': forms.FileInput(attrs={'class': 'form-control'}),
            'duration_minutes': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'order': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'is_published': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class QuizForm(forms.ModelForm):
    class Meta:
        model = Quiz
        fields = ['module', 'title', 'description', 'time_limit_minutes',
                  'pass_percentage', 'max_attempts', 'is_published']
        widgets = {
            'module': forms.Select(attrs={'class': 'form-select'}),
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Jina la mtihani'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'time_limit_minutes': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'pass_percentage': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'max': 100}),
            'max_attempts': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'is_published': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class QuestionForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = ['question_type', 'text', 'options', 'correct_answer', 'explanation', 'points', 'order']
        widgets = {
            'question_type': forms.Select(attrs={'class': 'form-select', 'onchange': 'toggleOptions(this)'}),
            'text': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Andika swali lako...'}),
            'options': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 3,
                'placeholder': 'Chaguo kwa kila mstari:\nA. Chaguo la kwanza\nB. Chaguo la pili\nC. Chaguo la tatu\nD. Chaguo la nne',
                'id': 'options-field',
            }),
            'correct_answer': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Kwa multiple choice: andika herufi (A, B, C, D)',
            }),
            'explanation': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'points': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'order': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
        }



class AssignmentForm(forms.ModelForm):
    class Meta:
        model = Assignment
        fields = ['module', 'title', 'description', 'instructions', 'due_date',
                  'max_points', 'file_required', 'allow_late_submission', 'is_published']
        widgets = {
            'module': forms.Select(attrs={'class': 'form-select'}),
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Jina la kazi'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'instructions': forms.Textarea(attrs={'class': 'form-control', 'rows': 5, 'placeholder': 'Maagizo kamili kwa wanafunzi...'}),
            'due_date': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'max_points': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'file_required': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'allow_late_submission': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_published': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class AssignmentSubmissionForm(forms.ModelForm):
    class Meta:
        model = AssignmentSubmission
        fields = ['file', 'text_content']
        widgets = {
            'file': forms.FileInput(attrs={'class': 'form-control'}),
            'text_content': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 6,
                'placeholder': 'Andika jibu lako hapa...',
            }),
        }


class AssignmentGradingForm(forms.ModelForm):
    class Meta:
        model = AssignmentSubmission
        fields = ['score', 'feedback']
        widgets = {
            'score': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'feedback': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Maoni kwa mwanafunzi...'}),
        }


class DiscussionForm(forms.ModelForm):
    class Meta:
        model = Discussion
        fields = ['title', 'content']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Kichwa cha mjadala'}),
            'content': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Andika mjadala wako...'}),
        }


class DiscussionReplyForm(forms.ModelForm):
    class Meta:
        model = DiscussionReply
        fields = ['content']
        widgets = {
            'content': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 3,
                'placeholder': 'Andika jibu lako...',
            }),
        }


class CourseReviewForm(forms.ModelForm):
    class Meta:
        model = CourseReview
        fields = ['rating', 'comment']
        widgets = {
            'rating': forms.NumberInput(attrs={
                'class': 'form-control', 'min': 1, 'max': 5,
                'placeholder': 'Kiwango (1-5)',
            }),
            'comment': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 3,
                'placeholder': 'Maoni yako kuhusu kozi hii...',
            }),
        }


class AnnouncementForm(forms.ModelForm):
    class Meta:
        model = Announcement
        fields = ['title', 'content', 'is_important']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Kichwa cha tangazo'}),
            'content': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Maelezo ya tangazo...'}),
            'is_important': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
