from rest_framework import serializers, exceptions
from djoser.serializers import UserCreateSerializer, UserSerializer 
from django.contrib.auth import get_user_model
from . import models, exceptions

User = get_user_model()

class UserCreateSerializer(UserCreateSerializer):
    class Meta(UserCreateSerializer.Meta):
        fields = ['first_name', 'last_name', 'email', 'password']


class UserSerializer(UserSerializer):
    class Meta(UserSerializer.Meta):
        fields = ['first_name', 'last_name', 'email']

class CustomerSerializer(serializers.ModelSerializer):
    id = serializers.ReadOnlyField()
    first_name = serializers.CharField(source='user.first_name', read_only=True)
    last_name = serializers.CharField(source='user.last_name', read_only=True)
    email = serializers.CharField(source='user.email', read_only=True)
    is_active = serializers.BooleanField(source='user.is_active')

    class Meta:
        model = models.Customer
        fields = ['id', 'first_name', 'last_name', 'email', 'phone', 'address', 'is_active']


class UpdateCustomerSerializer(serializers.ModelSerializer):
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    is_active = serializers.BooleanField(source='user.is_active')

    class Meta:
        model = models.Customer
        fields = ['id', 'first_name', 'last_name', 'phone', 'address','is_active']


class CreateUserCustomerSerializer(serializers.ModelSerializer):
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    email = serializers.CharField()
    password = serializers.CharField(style={"input_type": "password"})

    class Meta:
        model = models.Customer
        fields = ['first_name', 'last_name', 'email', 'password', 'phone', 'address']


class CreateCustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Customer
        fields = ['phone', 'address']

class CategorySerializer(serializers.ModelSerializer):
    product_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = models.Category
        fields = ['id', 'name', 'product_count']

class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.ProductImage
        fields = ['id', 'image']


class SimpleProductSerializer(serializers.ModelSerializer):
    image = ProductImageSerializer(read_only=True)

    class Meta:
        model = models.Product
        fields = ['id', 'title', 'slug', 'unit_price', 'inventory', 'image']


class SimpleReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Review
        fields = ['id', 'rating', 'comment']


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.OrderItem
        fields = ['id', 'order_id', 'product', 'unit_price', 'quantity', 'total_price', 'review']

    product = SimpleProductSerializer()
    review = SimpleReviewSerializer()


class ReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Review
        fields = ['id', 'order_item', 'rating', 'comment']

    order_item = OrderItemSerializer()


class CreateReviewSerializer(serializers.ModelSerializer):
    order_item = serializers.PrimaryKeyRelatedField(required=True, queryset=models.OrderItem.objects.all())

    class Meta:
        model = models.Review
        fields = ['order_item', 'rating', 'comment']


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Product
        fields = ['id', 'title', 'sku', 'slug', 'category', 'description', 'unit_price', 'inventory', 'limit', 'is_active', 'images', 'average_rating', 'review_count', 'reviews']

    slug = serializers.CharField(read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)
    category = CategorySerializer(read_only=True)



class FeaturedProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.FeaturedProduct
        fields = ['id', 'product']

    product = ProductSerializer(read_only=True)

class Base64ImageField(serializers.ImageField):
    """
    A Django REST framework field for handling image-uploads through raw post data.
    It uses base64 for encoding and decoding the contents of the file.

    Heavily based on
    https://github.com/tomchristie/django-rest-framework/pull/1268

    Updated for Django REST framework 3.
    """

    def to_internal_value(self, data):
        from django.core.files.base import ContentFile
        import base64
        import six
        import uuid

        # Check if this is a base64 string
        if isinstance(data, six.string_types):
            # Check if the base64 string is in the "data:" format
            if "data:" in data and ";base64," in data:
                # Break out the header from the base64 content
                header, data = data.split(";base64,")

            # Try to decode the file. Return validation error if it fails.
            try:
                decoded_file = base64.b64decode(data)
            except TypeError:
                self.fail("invalid_image")

            # Generate file name:
            file_name = str(uuid.uuid4())[:12]  # 12 characters are more than enough.
            # Get the file name extension:
            file_extension = self.get_file_extension(file_name, decoded_file)

            complete_file_name = "%s.%s" % (
                file_name,
                file_extension,
            )

            data = ContentFile(decoded_file, name=complete_file_name)

        return super(Base64ImageField, self).to_internal_value(data)

    def get_file_extension(self, file_name, decoded_file):
        import imghdr

        extension = imghdr.what(file_name, decoded_file)
        extension = "jpg" if extension == "jpeg" else extension

        return extension


class CreateProductSerializer(serializers.ModelSerializer):
    images = ProductImageSerializer(many=True, read_only=True)
    uploaded_images = serializers.ListField(
        child=Base64ImageField(allow_empty_file=False, use_url=False),
        write_only=True,
    )

    class Meta:
        model = models.Product
        fields = ['id', 'title', 'category', 'description', 'unit_price', 'inventory', 'is_active', 'images', 'uploaded_images']
        partial = True
    
    def create(self, validated_data):
        uploaded_images = validated_data.pop("uploaded_images")
        category_data = validated_data.pop("category")


        product = models.Product.objects.create(**validated_data)
        product.category = category_data  # Use the set() method to set the categories

        for image in uploaded_images:
            models.ProductImage.objects.create(product=product, image=image)

        return product
    
    def update(self, instance, validated_data):
        uploaded_images = validated_data.pop("uploaded_images", [])
        category_data = validated_data.pop("category", None)

        # Delete existing images
        instance.images.all().delete()

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if category_data:
            instance.category = category_data

        instance.save()

        # Add new images
        for image in uploaded_images:
            models.ProductImage.objects.create(product=instance, image=image)

        return instance


class CartItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.CartItem
        fields = ['id', 'product', 'quantity', 'total_price']

    product = SimpleProductSerializer(read_only=True)


class WriteCartItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.CartItem
        fields = ['id', 'product_id', 'quantity']

    product_id = serializers.IntegerField()

    def validate_product_id(self, product_id):
        if not models.Product.objects.filter(pk=product_id).exists():
            raise serializers.ValidationError('No product with the given id was found')
        return product_id

    def update(self, cart_item, validated_data):
        if validated_data['quantity'] > cart_item.product.inventory:
            raise exceptions.QuantityError()
        return super().update(cart_item, validated_data)

    def save(self, **kwargs):
        cart = self.context['cart']

        # Update the quantity directly instead of adding the value
        if self.instance is not None:
            self.update(self.instance, self.validated_data)
            return self.instance

        product_id = self.validated_data['product_id']
        quantity = self.validated_data['quantity']
        try:
            cart_item = models.CartItem.objects.get(cart=cart, product_id=product_id)
            cart_item.quantity += quantity
        except models.CartItem.DoesNotExist:
            cart_item = models.CartItem(cart=cart, **self.validated_data)

        if cart_item.quantity > cart_item.product.inventory:
            raise exceptions.QuantityError()

        cart_item.save()
        self.instance = cart_item
        return self.instance


class OrderSerializer(serializers.ModelSerializer):
    total_price = serializers.ReadOnlyField()

    class Meta:
        model = models.Order
        fields = ['id', 'items', 'customer','order_number','order_time', 'total_price', 'status']

    items = OrderItemSerializer(many=True)
    customer = CustomerSerializer(read_only=True)
    
