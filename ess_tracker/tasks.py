from celery import shared_task


@shared_task(bind=True, time_limit=600, soft_time_limit=560)
def run_ess_fill(self, profile_id, run_id):
    """Jaza ESS kwa profile moja (queue='default' — ndiyo worker inayosikiliza)."""
    from .essfill import run_fill
    return run_fill(profile_id, run_id)


@shared_task(bind=True, time_limit=600, soft_time_limit=560)
def run_ess_sync(self, profile_id, run_id):
    """Sawazisha majina ya task/sub-task na ESS (queue='default')."""
    from .essfill import run_sync
    return run_sync(profile_id, run_id)


@shared_task(bind=True, time_limit=600, soft_time_limit=560)
def run_ess_push(self, profile_id, run_id):
    """Tuma majina ya local kwenda ESS official (queue='default')."""
    from .essfill import run_push
    return run_push(profile_id, run_id)