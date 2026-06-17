from celery import shared_task
from django.core.mail import send_mail


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_email_task(self, subject, message, from_email, recipient_list, html_message=None):
    """Generic async email sender. Retries up to 3x on failure."""
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=from_email,
            recipient_list=recipient_list,
            html_message=html_message,
            fail_silently=False,
        )
    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=2)
def send_assessor_welcome_email_task(self, assessor_id, temp_password, login_url):
    """Send welcome credentials email to a newly created/assigned assessor."""
    try:
        from .models import Assessor
        from .views.utils import get_assessor_email_template
        assessor = Assessor.objects.select_related('user', 'school').get(id=assessor_id)
        school = assessor.school
        html_content = get_assessor_email_template(
            assessor=assessor,
            school=school,
            temp_password=temp_password,
            is_new_account=True,
            assignments_count=1,
            login_url=login_url,
        )
        send_mail(
            subject='Maelezo ya Kuingia — IMS Field Management',
            message=f'Karibu {assessor.full_name}. Login: {login_url}',
            from_email=None,
            recipient_list=[assessor.user.email],
            html_message=html_content,
            fail_silently=False,
        )
    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=2)
def send_board_link_email_task(self, head_name, head_email, school_name, district_name, login_url):
    """Send board login link to a school head."""
    try:
        send_mail(
            subject=f'Kiungo cha IMS — {school_name}',
            message=(
                f'Habari {head_name},\n\n'
                f'Shule yako ({school_name}, {district_name}) imepata wanafunzi wa mafunzo.\n\n'
                f'Ingia hapa: {login_url}\n\n— IMS'
            ),
            from_email=None,
            recipient_list=[head_email],
            fail_silently=False,
        )
    except Exception as exc:
        raise self.retry(exc=exc)
