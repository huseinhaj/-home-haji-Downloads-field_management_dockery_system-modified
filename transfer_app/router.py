class TransferRouter:
    """Routes transfer_app models to the 'transfer' database."""

    def db_for_read(self, model, **hints):
        if model._meta.app_label == 'transfer_app':
            return 'transfer'
        return None

    def db_for_write(self, model, **hints):
        if model._meta.app_label == 'transfer_app':
            return 'transfer'
        return None

    def allow_relation(self, obj1, obj2, **hints):
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if app_label == 'transfer_app':
            return db == 'transfer'
        if db == 'transfer':
            return False
        return None
