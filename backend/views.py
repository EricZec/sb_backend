from django.db import transaction
from django_filters.rest_framework import DjangoFilterBackend
from django.contrib.auth.tokens import default_token_generator
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from rest_framework import viewsets, permissions, status, mixins, generics
from rest_framework.decorators import action
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from .serializers import UserCreateSerializer
from . import models, serializers, filters
from django.db.models import Q
from .paginations import PageNumberPagination
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.http import HttpResponse
from django.shortcuts import redirect
from rest_framework.views import APIView
from rest_framework.pagination import PageNumberPagination
from datetime import datetime, timedelta
from django.utils import timezone
import requests
import midtransclient
import json

def activate_account(request, uid, token):
    activation_url = f"http://127.0.0.1:8000/auth/users/activation/"
    data = {
        "uid": uid,
        "token": token,
    }
    print(uid)
    print(token)
    
    response = requests.post(activation_url, data=data)
    
    if response.status_code == 204:  # Account activated successfully
        return redirect('http://localhost:4200/login')  # Redirect to your Angular login page
    else:
        # Handle activation error, maybe redirect to an error page
        return redirect('http://your-angular-app-url/activation-error')

class CustomPagination(PageNumberPagination):
    page_size = 20



def get_cart_for_user(user):
    customer = get_object_or_404(models.Customer, user=user)
    cart, _ = models.Cart.objects.get_or_create(customer=customer)
    return cart


class OrderViewSet(mixins.CreateModelMixin,
                   mixins.RetrieveModelMixin,
                   mixins.ListModelMixin,
                   viewsets.GenericViewSet):
    serializer_class = serializers.OrderSerializer
    permission_classes = [permissions.AllowAny ]
    pagination_class = PageNumberPagination
    filterset_class = filters.OrderFilter
  
    def get_queryset(self):
        user = self.request.user
        queryset = models.Order.objects.all().order_by('-id')
        
        if not user.is_staff:
            queryset = queryset.filter(customer=user)

        # Apply filters from request parameters
        order_time_min = self.request.query_params.get('order_time_min')
        if order_time_min:
            queryset = queryset.filter(order_time__gte=order_time_min)

        order_time_max = self.request.query_params.get('order_time_max')
        if order_time_max:
            queryset = queryset.filter(order_time__lte=order_time_max)

        status = self.request.query_params.get('status')
        if status:
            queryset = queryset.filter(status=status)
        
        return queryset
        
    def create(self, request, *args, **kwargs):
        cart = get_cart_for_user(self.request.user)
        cart_items = cart.cartitem_set.all()

        if cart_items.count() == 0:
            return Response(status=status.HTTP_400_BAD_REQUEST)
        
        notifications_to_send = []

        with transaction.atomic():
            order = models.Order.objects.create(customer=cart.customer)
            
            order_items = []
            for cart_item in cart_items:
                product = cart_item.product
                if cart_item.quantity > cart_item.product.inventory:
                    return Response(status=status.HTTP_400_BAD_REQUEST)
                order_items.append(models.OrderItem(
                    order=order,
                    product=cart_item.product,
                    unit_price=cart_item.product.unit_price,
                    quantity=cart_item.quantity
                ))
                cart_item.delete()
                product.inventory -= cart_item.quantity
                product.save()
                
                if product.inventory < product.limit:
                    notifications_to_send.append(product)

            models.OrderItem.objects.bulk_create(order_items, unique_fields=['order', 'product'])
            cart.delete()
            admin_users = get_user_model().objects.filter(is_staff=True)
            recipient_emails = [user.email for user in admin_users]

            for product in notifications_to_send:
                subject = f"Produk: {product.title}"
                message = f"Jumlah Stok dari {product.title} sudah melewati limit. Jumlah stok yang ada sekarang: {product.inventory}"
                send_mail(subject, message, settings.EMAIL_HOST_USER , recipient_emails)

            return Response(data={'order_number': order.order_number}, status=status.HTTP_201_CREATED)
    
    def complete_payment(self, request, order_id):
        try:
            order = models.Order.objects.get(pk=order_id)
        except models.Order.DoesNotExist:
            return Response({"error": "Order not found"}, status=404)

        if order.is_pending:
            order.complete_payment()
            return Response({"message": "Payment completed successfully"}, status=200)
        else:
            return Response({"error": "Order is not in the pending state"}, status=400)

    def ship_order(self, request, order_id):
        try:
            order = models.Order.objects.get(pk=order_id)
        except models.Order.DoesNotExist:
            return Response({"error": "Order not found"}, status=404)

        if order.status == models.Order.STATUS_PROCESSED:
            shipping_reference = request.data.get('shipping_reference', '')
            order.ship(shipping_reference)
            return Response({"message": "Order shipped successfully"}, status=200)
        else:
            return Response({"error": "Order is not in the processed state"}, status=400)

    def cancel_order(self, request, order_id):
        try:
            order = models.Order.objects.get(pk=order_id)
        except models.Order.DoesNotExist:
            return Response({"error": "Order not found"}, status=404)

        if order.status in [models.Order.STATUS_AWAITING_PAYMENT, models.Order.STATUS_PROCESSED]:
            order.cancel()
            return Response({"message": "Order has been canceled successfully"}, status=200)
        else:
            return Response({"error": "Order cannot be canceled in the current state"}, status=400)
        
    def cancel_pending_orders(self):
        # Calculate the datetime threshold for checking orders
        threshold_datetime = timezone.now() - timedelta(minutes=5)

        # Fetch orders that are still in the "awaiting payment" state
        pending_orders = models.Order.objects.filter(
            status=models.Order.STATUS_AWAITING_PAYMENT,
            created_at__lte=threshold_datetime
        )

        # Loop through pending orders and cancel them
        for order in pending_orders:
            # Use the @transition decorator to change status to cancelled
            if order.status in [models.Order.STATUS_AWAITING_PAYMENT, models.Order.STATUS_PROCESSED]:
                order.cancel()
                order.save()
                # Restore product inventory
                for order_item in order.orderitem_set.all():
                    order_item.product.inventory += order_item.quantity
                    order_item.product.save()

        return len(pending_orders)

    


class CartItemViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        print("get_queryset method is running")
        return models.CartItem.objects.filter(cart=get_cart_for_user(self.request.user))

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['cart'] = get_cart_for_user(self.request.user)
        return context

    def get_serializer_class(self, *args, **kwargs):
        if self.action in ['create', 'partial_update']:
            return serializers.WriteCartItemSerializer
        else:
            return serializers.CartItemSerializer

class CategoryViewSet(viewsets.ModelViewSet):
    queryset = models.Category.objects.all()
    serializer_class = serializers.CategorySerializer

class ProductViewSet(mixins.ListModelMixin,
                     mixins.RetrieveModelMixin,mixins.CreateModelMixin, viewsets.GenericViewSet):
    queryset = models.Product.objects.all()
    lookup_field = 'slug'
    filter_backends = [DjangoFilterBackend]
    filterset_class = filters.ProductFilter
    pagination_class = CustomPagination

    def get_serializer_class(self):
        if self.action in ['create', 'partial_update']:
            return serializers.CreateProductSerializer
        elif self.action == 'featured':
            return serializers.FeaturedProductSerializer
        else:
            return serializers.ProductSerializer

    @action(detail=False)
    def featured(self, request):
        queryset = models.FeaturedProduct.objects.all()[:8]
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=["GET", "POST"])  # Add POST to support product creation
    def create_product(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = serializer.save()  # Save the product to the database
        return Response(serializers.ProductSerializer(product).data, status=status.HTTP_201_CREATED)
    
    @action(detail=False, methods=["PUT"])
    def update_product(self, request, slug=None):
        product = self.get_object()  # Get the product using the slug or ID
        serializer = serializers.CreateProductSerializer(product, data=request.data, partial=True)  # Use CreateProductSerializer class
        serializer.is_valid(raise_exception=True)
        updated_product = serializer.save()  # Save the updated product to the database
        return Response(serializers.ProductSerializer(updated_product).data, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=["DELETE"])  # Use detail=True for a specific product
    def delete_product(self, request, slug=None):
        product = self.get_object()  # Get the product using the slug or ID
        product.delete()  # Delete the product
        return Response(status=status.HTTP_204_NO_CONTENT)
    
    def get_queryset(self):
        queryset = super().get_queryset()
        sort_param = self.request.query_params.get('sort', None)
        search_query = self.request.query_params.get('q', None)
        price_sort = self.request.query_params.get('price_sort', None)
        
        
        # Apply search filtering using Q objects
        if search_query:
            queryset = queryset.filter(
                Q(title__icontains=search_query) | Q(description__icontains=search_query)
            )

        if sort_param == 'oldest':
            queryset = queryset.order_by('create_at')
        else:
            queryset = queryset.order_by('-create_at')

        if price_sort == 'cheap':
            queryset = queryset.order_by('unit_price')
        elif price_sort == 'expensive':
            queryset = queryset.order_by('-unit_price')


        return queryset
    
    
    
class CustomerViewSet(viewsets.ModelViewSet):
    class Permission(permissions.IsAdminUser):
        def has_permission(self, request, view):
            # Give non-admin permission to create customer object if the user is authenticated
            # and the object hasn't been created before.
            if view.action == 'create' and request.user \
                    and models.Customer.objects.filter(user=request.user.id).count() == 0:
                return True

            # Use implementation IsAdminUser if the action is `list`
            if view.action == 'list':
                return super().has_permission(request, view)

            # else allow all other actions which are object level ones
            # (handled by `has_object_permission`)
            return True

        def has_object_permission(self, request, view, customer):
            # Only allow if it is their own customer instance
            if request.user == customer.user:
                return True
            return False
    queryset = models.Customer.objects.all()
    serializer_class = serializers.CustomerSerializer
    permission_classes = [Permission]

    @action(detail=False, methods=["GET", "PUT", "PATCH"], permission_classes=[permissions.IsAuthenticated])
    def me(self, request):
        user = request.user
        customer = get_object_or_404(models.Customer, user_id=user.id)

        method = request.method

        if method == 'GET':
            serializer = serializers.CustomerSerializer(customer)
            return Response(serializer.data)

        serializer = serializers.UpdateCustomerSerializer(customer, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        
        user.first_name = serializer.validated_data.get('first_name', user.first_name)
        user.last_name = serializer.validated_data.get('last_name', user.last_name)
        customer.phone = serializer.validated_data.get('phone', customer.phone)
        customer.address = serializer.validated_data.get('address', customer.address)

        user.save()
        serializer.save()

        return Response(request.data, status=status.HTTP_200_OK)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def perform_destroy(self, customer):
        super().perform_destroy(customer)
        customer.user.delete()


class ReviewViewSet(viewsets.ModelViewSet):
    class IsPurchasedItemOwner(permissions.BasePermission):
        def has_permission(self, request, view):
            data = request.data
            if view.action == "create" and "order_item" in data:
                order_item = get_object_or_404(models.OrderItem, id=data['order_item'])
                return order_item.order.customer.user == request.user
            return super().has_permission(request, view)

        def has_object_permission(self, request, view, review):
            return review.order_item.order.customer.user == request.user

    permission_classes = [IsPurchasedItemOwner]

    def get_queryset(self):
        return models.Review.objects.filter(order_item__order__customer__user=self.request.user)

    def get_serializer_class(self):
        if self.action in ["create", "update"]:
            return serializers.CreateReviewSerializer
        else:
            return serializers.ReviewSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        order_item = serializer.validated_data['order_item']

        if order_item.review_set.all().count() > 0 or order_item.order.status != models.Order.STATUS_COMPLETED:
            return Response(status=status.HTTP_400_BAD_REQUEST)

        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)


class CreateUserCustomer(generics.CreateAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = serializers.CreateUserCustomerSerializer
    queryset = models.Customer.objects.all()

    def post(self, request):
        with transaction.atomic():
            customer_serializer = serializers.CreateCustomerSerializer(data=request.data)
            customer_serializer.is_valid(raise_exception=True)
            user_serializer = UserCreateSerializer(data=request.data)
            user_serializer.is_valid(raise_exception=True)
            user_serializer.validated_data["is_active"] = True

            user = user_serializer.save()
            customer_serializer.save(user=user)

            return Response(request.data, status=status.HTTP_201_CREATED)
        

class Transaction(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def post(self, request, *args, **kwargs):
        snap = midtransclient.Snap(
            is_production=False,
            server_key='SB-Mid-server-9wxNnpOoWkHvRUD3NTSKSe7M',
            client_key='SB-Mid-client-MHo6kf5ZIKL22nxC'
        )
        data = json.loads(request.body)
        order_id = data['transaction_details']['order_number']
        gross_amount = data['transaction_details']['total_price']
        print("Received order_id:", order_id)
        print("Received gross_amount:", gross_amount)
        param = {
            "transaction_details": {
                "order_id": order_id,
                "gross_amount": gross_amount
            },
            "credit_card": {
                "secure": True
            }
        }
        transaction = snap.create_transaction(param)
        transaction_token = transaction['token']
        print('transaction_token:')
        print(transaction_token)
        transaction_redirect_url = transaction['redirect_url']
        print('transaction_redirect_url:')
        print(transaction_redirect_url)
        response_data = {
            'transaction_token': transaction_token,
            'transaction_redirect_url': transaction_redirect_url
        }
        return Response(response_data)
    
class HelloWorldView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        data = {'message': 'Hello, World!'}
        return Response(data)
    
class VerifyAdminStatusView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUser]

    def get(self, request):
        # The user is an admin as permission_classes IsAdminUser will handle it.
        return Response({'is_admin': True})