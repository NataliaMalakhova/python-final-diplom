from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.db import IntegrityError
from django.contrib import messages
from backend.models import User, Shop, Category, Product, ProductInfo, Parameter, ProductParameter, Order, OrderItem, \
    Contact, ConfirmEmailToken
from .tasks import do_import, process_avatar, process_product_image


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    """
    Панель управления пользователями
    """
    model = User

    fieldsets = (
        (None, {'fields': ('email', 'password', 'type')}),
        ('Personal info', {'fields': ('first_name', 'last_name', 'company', 'position')}),
        ('Permissions', {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )
    list_display = ('email', 'first_name', 'last_name', 'is_staff', 'type')
    search_fields = ('email', 'first_name', 'last_name')
    list_filter = ('type', 'is_staff', 'is_superuser', 'is_active')

    def save_model(self, request, obj, form, change):
        """
        Переопределяем метод сохранения объекта
        """
        try:
            super().save_model(request, obj, form, change)
            if obj.avatar:
                # Запускаем задачу Celery для обработки аватара
                process_avatar.delay(obj.id)
        except IntegrityError:
            self.message_user(request, "Пользователь с таким email уже существует.", level=messages.ERROR)


@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
    list_display = ('name', 'url', 'user', 'state')
    search_fields = ('name', 'url', 'user__email')
    list_filter = ('state',)

    actions = ['import_products']

    def import_products(self, request, queryset):
        for shop in queryset:
            # Запускаем задачу импорта для каждого выбранного магазина
            do_import.delay(shop.id)
        self.message_user(request, "Задача импорта запущена для выбранных магазинов.")

    import_products.short_description = "Импортировать товары для выбранных магазинов"


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'category',)
    search_fields = ('name', 'category')
    list_filter = ('category',)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if obj.image:
            # Запускаем задачу Celery для обработки изображения товара
            process_product_image.delay(obj.id)


@admin.register(ProductInfo)
class ProductInfoAdmin(admin.ModelAdmin):
    list_display = ('product', 'shop', 'quantity', 'price', 'price_rrc')
    search_fields = ('product__name', 'shop__name')
    list_filter = ('shop',)


@admin.register(Parameter)
class ParameterAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(ProductParameter)
class ProductParameterAdmin(admin.ModelAdmin):
    list_display = ('product_info', 'parameter', 'value')
    search_fields = ('product_info__product__name', 'parameter__name', 'value')
    list_filter = ('parameter',)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'dt', 'state')
    search_fields = ('user__email', 'id')
    list_filter = ('state', 'dt')


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('order', 'product_info', 'quantity')
    search_fields = ('order__id', 'product_info__product__name')
    list_filter = ('order',)


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ('user', 'city', 'street', 'phone')
    search_fields = ('user__email', 'city', 'street', 'phone')


@admin.register(ConfirmEmailToken)
class ConfirmEmailTokenAdmin(admin.ModelAdmin):
    list_display = ('user', 'key', 'created_at',)
