import os
from django.conf import settings
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sb_backend.settings')
settings.configure()

app = Celery('sb_backend')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

@app.task
def cancel_pending_orders():
    from backend.views import OrderViewSet
    order_view = OrderViewSet()
    cancelled_orders_count = order_view.cancel_pending_orders()
    return f"Cancelled {cancelled_orders_count} pending orders."
