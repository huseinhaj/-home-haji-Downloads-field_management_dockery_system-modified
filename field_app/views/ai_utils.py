# Re-export AI client from the app-level module so views package imports work.
from field_app.ai_utils import client, model_name  # noqa: F401
