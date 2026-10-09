from celery import shared_task


@shared_task(bind=True, time_limit=600, soft_time_limit=560)
def run_ess_fill(self, profile_id, run_id):
    """Jaza ESS kwa profile moja (queue='default' — ndiyo worker inayosikiliza)."""
    from .essfill import run_fill
    return run_fill(profile_id, run_id)