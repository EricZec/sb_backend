from django.db import models
from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.core.validators import MinValueValidator
from django.core.cache import cache
from django.utils.text import slugify
from django_fsm import FSMField, transition
from django.utils import timezone


import uuid
# Create your models here.

class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **kwargs):
        if not email:
            raise ValueError("Users must have an email address")
        email = self.normalize_email(email)
        user = self.model(email=email, **kwargs)
        user.set_password(password)
        user.save()
        return user

    def create_superuser(self, email, password=None, **kwargs):
        kwargs.setdefault('is_active', True)
        kwargs.setdefault('is_staff', True)
        kwargs.setdefault('is_superuser', True)
        if kwargs.get('is_active') is not True:
            raise ValueError('Superuser must be active')
        if kwargs.get('is_staff') is not True:
            raise ValueError('Superuser must be staff')
        if kwargs.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True')
        return self.create_user(email, password, **kwargs)


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(max_length=255, unique=True)
    first_name = models.CharField(max_length=255)
    last_name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=False)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']

    def get_full_name(self):
        return f"{self.first_name}{self.last_name}"

    def get_short_name(self):
        return self.first_name

    def __str__(self):
        return self.email



class Customer(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    phone = models.CharField(max_length=255)
    address = models.TextField()

    # noinspection PyUnresolvedReferences
    def __str__(self):
        return self.user.email
    

class Category(models.Model):
    name = models.CharField(max_length=255)
    

    def __str__(self):
        return self.name


class Product(models.Model):
    title = models.CharField(max_length=255)
    sku = models.CharField(max_length=255,null=True)
    slug = models.SlugField()
    category = models.ForeignKey(Category, on_delete=models.CASCADE, default=1)
    description = models.TextField(null=True, blank=True)
    unit_price = models.PositiveIntegerField(blank=True, default=0)
    inventory = models.PositiveIntegerField(blank=True, default=0)
    limit = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    create_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title
    
    def save(self, *args, **kwargs):
        if not self.slug:
            # Generate the slug from the title using Django's slugify function
            self.slug = slugify(self.title)

        super(Product, self).save(*args, **kwargs)

    @property
    def image(self):
        images = self.images.all()
        if images.count() == 0:
            return None
        return images.first()

    @property
    def average_rating(self):
        reviews = Review.objects.filter(order_item__product=self)

        if len(reviews) == 0:
            return None

        total = 0
        for review in reviews:
            total += review.rating

        return total / len(reviews)

    @property
    def reviews(self):
        return Review.objects.filter(order_item__product=self)

    @property
    def few_reviews(self):
        qs = self.reviews
        if qs.count() > 10:
            return qs[:10]
        return qs

    @property
    def review_count(self):
        return self.reviews.count()
    
class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='store/images/')


class FeaturedProduct(models.Model):
    product = models.OneToOneField(Product, on_delete=models.CASCADE)


class Cart(models.Model):
    customer = models.OneToOneField(Customer, on_delete=models.CASCADE)


class CartItem(models.Model):
    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['cart', 'product'], name='unique_product_in_cart')
        ]

    cart = models.ForeignKey(Cart, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])

    @property
    def total_price(self):
        return self.quantity * self.product.unit_price


class Order(models.Model):
    STATUS_AWAITING_PAYMENT = 'a'
    STATUS_PROCESSED = 'b'
    STATUS_SHIPPED = 'c'
    STATUS_COMPLETED = 'd'
    STATUS_CANCELLED = 'e'
    STATUS_CHOICES = [
        (STATUS_AWAITING_PAYMENT, 'Awaiting payment'),
        (STATUS_PROCESSED, 'Processed'),
        (STATUS_SHIPPED, 'Shipped'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]
    order_number = models.CharField(max_length=20, unique=True, null=True)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    order_time = models.DateTimeField(auto_now=True)
    status = FSMField(max_length=1, choices=STATUS_CHOICES, default=STATUS_AWAITING_PAYMENT)
    shipping_reference = models.CharField(max_length=50, blank=True, null=True)
    

    def save(self, *args, **kwargs):
        if not self.order_number:
            # Get the current date in the format YYYYMMDD
            date_str = timezone.now().strftime('%Y%m%d')

            # Find the latest order number in the database
            last_order = Order.objects.filter(order_number__startswith=f"ord{date_str}-").order_by('-order_number').first()

            # Increment the last order number or start from 1 if no orders exist
            if last_order:
                last_order_number = int(last_order.order_number[-3:])
                new_order_number = str(last_order_number + 1).zfill(3)
            else:
                new_order_number = "001"

            self.order_number = f"ORD{date_str}-{new_order_number}"
        super(Order, self).save(*args, **kwargs)


    @property
    def total_price(self):
        items = OrderItem.objects.filter(order=self)
        total = 0
        for item in items:
            total += item.total_price
        return total

    @property
    def is_pending(self):
        return self.status == self.STATUS_AWAITING_PAYMENT

    @transition(field=status, source=STATUS_AWAITING_PAYMENT, target=STATUS_PROCESSED)
    def complete_payment(self):
        self.status = self.STATUS_PROCESSED
        self.save()

    @transition(field=status, source=STATUS_PROCESSED, target=STATUS_SHIPPED)
    def ship(self, shipping_reference=''):
        self.shipping_reference = shipping_reference
        self.status = self.STATUS_SHIPPED
        self.save()

    @transition(field=status, source=STATUS_SHIPPED, target=STATUS_COMPLETED)
    def complete(self):
        self.status = self.STATUS_COMPLETED
        self.save()

    @transition(field=status, source=[STATUS_AWAITING_PAYMENT, STATUS_PROCESSED], target=STATUS_CANCELLED)
    def cancel(self):
        self.status = self.STATUS_CANCELLED
        self.save()




class OrderItem(models.Model):
    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['order', 'product'], name='unique_product_in_order')
        ]

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.IntegerField(validators=[MinValueValidator(1)])
    unit_price = models.IntegerField(validators=[MinValueValidator(1)])

    @property
    def total_price(self):
        return self.quantity * self.unit_price

    @property
    def review(self):
        return self.review_set.first()


class Review(models.Model):
    RATING_CHOICES = (
        (1, '1 star'),
        (2, '2 stars'),
        (3, '3 stars'),
        (4, '4 stars'),
        (5, '5 stars'),
    )
    order_item = models.ForeignKey(OrderItem, null=True, on_delete=models.SET_NULL)
    rating = models.IntegerField(choices=RATING_CHOICES)
    comment = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
