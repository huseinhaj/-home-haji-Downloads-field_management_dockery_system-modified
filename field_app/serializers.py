from rest_framework import serializers
from .models import (
    Region, District, School, Subject,
    StudentTeacher, Assessor, LogbookEntry,
    AcademicYear, FinalAssessment,
)


class RegionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Region
        fields = ['id', 'name']


class DistrictSerializer(serializers.ModelSerializer):
    region_name = serializers.CharField(source='region.name', read_only=True)

    class Meta:
        model = District
        fields = ['id', 'name', 'region', 'region_name']


class SchoolSerializer(serializers.ModelSerializer):
    district_name = serializers.CharField(source='district.name', read_only=True)
    region_name = serializers.CharField(source='district.region.name', read_only=True)

    class Meta:
        model = School
        fields = ['id', 'name', 'school_code', 'level', 'district', 'district_name', 'region_name', 'current_students']


class SubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = ['id', 'name', 'level']


class AcademicYearSerializer(serializers.ModelSerializer):
    class Meta:
        model = AcademicYear
        fields = ['id', 'year', 'is_active']


class LogbookEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = LogbookEntry
        fields = [
            'id', 'date', 'day_of_week', 'activity_type',
            'topic_taught', 'class_taught', 'num_students_present',
            'other_activities', 'supervisor_remarks', 'head_teacher_remarks',
            'created_at',
        ]
        read_only_fields = ['supervisor_remarks', 'head_teacher_remarks', 'created_at']


class StudentTeacherSerializer(serializers.ModelSerializer):
    school_name = serializers.CharField(source='selected_school.name', read_only=True)

    class Meta:
        model = StudentTeacher
        fields = ['id', 'full_name', 'phone_number', 'selected_school', 'school_name', 'approval_status']
