"""
DRF ViewSets for the public/internal REST API (/api/v1/).
Read-only for geographic/reference data; authenticated CRUD for student data.
"""
from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from .models import (
    Region, District, School, Subject, AcademicYear,
    LogbookEntry, StudentTeacher,
)
from .serializers import (
    RegionSerializer, DistrictSerializer, SchoolSerializer,
    SubjectSerializer, AcademicYearSerializer,
    LogbookEntrySerializer, StudentTeacherSerializer,
)


class RegionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Region.objects.all().order_by('name')
    serializer_class = RegionSerializer
    permission_classes = [permissions.IsAuthenticated]
    search_fields = ['name']


class DistrictViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = District.objects.select_related('region').order_by('name')
    serializer_class = DistrictSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ['region']
    search_fields = ['name']

    @action(detail=True, url_path='schools')
    def schools(self, request, pk=None):
        district = self.get_object()
        schools = School.objects.filter(district=district).order_by('name')
        serializer = SchoolSerializer(schools, many=True)
        return Response(serializer.data)


class SchoolViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = School.objects.select_related('district__region').order_by('name')
    serializer_class = SchoolSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ['district', 'level']
    search_fields = ['name', 'school_code']


class SubjectViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Subject.objects.all().order_by('name')
    serializer_class = SubjectSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ['level']
    search_fields = ['name']


class AcademicYearViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AcademicYear.objects.all().order_by('-year')
    serializer_class = AcademicYearSerializer
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, url_path='active')
    def active(self, request):
        year = AcademicYear.objects.filter(is_active=True).first()
        if not year:
            return Response({'detail': 'No active academic year.'}, status=404)
        return Response(AcademicYearSerializer(year).data)


class LogbookEntryViewSet(viewsets.ModelViewSet):
    serializer_class = LogbookEntrySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        try:
            student = StudentTeacher.objects.get(user=self.request.user)
            return LogbookEntry.objects.filter(student=student).order_by('-date')
        except StudentTeacher.DoesNotExist:
            return LogbookEntry.objects.none()

    def perform_create(self, serializer):
        student = StudentTeacher.objects.get(user=self.request.user)
        serializer.save(student=student)
