class ResultsRouter:
    """Routes results app models to the 'results' database."""

    def db_for_read(self, model, **hints):
        if model._meta.app_label == 'results':
            return 'results'
        return None

    def db_for_write(self, model, **hints):
        if model._meta.app_label == 'results':
            return 'results'
        return None

    def allow_relation(self, obj1, obj2, **hints):
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if app_label == 'results':
            return db == 'results'
        if db == 'results':
            return False
        return None
