from backend.views import OrderViewSet
from celery import shared_task

@shared_task
def cancel_pending_orders():
    order_view = OrderViewSet()
    cancelled_orders_count = order_view.cancel_pending_orders()
    return f"Cancelled {cancelled_orders_count} pending orders."
