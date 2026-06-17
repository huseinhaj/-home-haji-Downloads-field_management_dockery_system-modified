from rest_framework.routers import DefaultRouter
from .api_views import (
    RegionViewSet, DistrictViewSet, SchoolViewSet,
    SubjectViewSet, AcademicYearViewSet, LogbookEntryViewSet,
)

router = DefaultRouter()
router.register('regions', RegionViewSet, basename='api-region')
router.register('districts', DistrictViewSet, basename='api-district')
router.register('schools', SchoolViewSet, basename='api-school')
router.register('subjects', SubjectViewSet, basename='api-subject')
router.register('academic-years', AcademicYearViewSet, basename='api-year')
router.register('logbook', LogbookEntryViewSet, basename='api-logbook')

urlpatterns = router.urls
