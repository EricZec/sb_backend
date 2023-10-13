from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

urlpatterns = [
    path('create-user-customer/', views.CreateUserCustomer.as_view(), name='create-user-customer'),
    path('midtrans/snap/token/', views.Transaction.as_view(), name='midtrans_snap_token'),
    path('verify-admin-status/', views.VerifyAdminStatusView.as_view(), name='verify_admin_status'),
    path('products/<slug:slug>/update_product/', views.ProductViewSet.as_view({'put': 'update_product'}), name='update_product'),
    path('products/', views.ProductViewSet.as_view({'get': 'search_product'}), name='product-search'),
    path('products/create_product/', views.ProductViewSet.as_view({'post': 'create_product'}), name='product-create'),
    path('orders/<int:order_id>/complete_payment/', views.OrderViewSet.as_view({'post': 'complete_payment'}), name='complete_payment'),
    path('orders/<int:order_id>/cancel_order/', views.OrderViewSet.as_view({'post': 'cancel_order'}), name='cancel-order'),
    path('activate/<str:uid>/<str:token>/', views.activate_account, name='activate_account'),
    path('password/reset/confirm/<str:uid>/<str:token>/', views.reset_password, name='reset_password'),
    path('customers/<int:user_id>/change_user_active_status/', views.CustomerViewSet.as_view({'put': 'change_user_active_status'}), name='change-user-active-status'),
    
]

urlpatterns += [
    path('hello-world/', views.HelloWorldView.as_view(), name='hello-world'),
]

router = DefaultRouter()
router.register('categories', views.CategoryViewSet, basename='categories')
router.register('products', views.ProductViewSet, basename='products')
router.register('customers', views.CustomerViewSet, basename='customers')
router.register('cart-items', views.CartItemViewSet, basename='cart-items')
router.register('orders', views.OrderViewSet, basename='orders')
router.register('reviews', views.ReviewViewSet, basename='reviews')

urlpatterns += router.urls