from django.contrib import admin
from .models import TLMTeacher, Testimonial, LessonNote, SubjectTopic, TopicSubtopic

admin.site.register(TLMTeacher)
admin.site.register(Testimonial)
admin.site.register(LessonNote)
admin.site.register(SubjectTopic)
admin.site.register(TopicSubtopic)
