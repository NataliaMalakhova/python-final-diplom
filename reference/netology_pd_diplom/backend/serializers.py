from drf_spectacular.utils import extend_schema_serializer, OpenApiExample
from rest_framework import serializers

from backend.models import User, Category, Shop, ProductInfo, Product, ProductParameter, OrderItem, Order, Contact


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            name="Пример контактной информации",
            value={
                "city": "Москва",
                "street": "Тверская",
                "house": "1",
                "structure": "2",
                "building": "3",
                "apartment": "45",
                "phone": "+79161234567",
                "user": 1
            }
        )
    ]
)
class ContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = Contact
        fields = ('id', 'city', 'street', 'house', 'structure', 'building', 'apartment', 'user', 'phone')
        read_only_fields = ('id',)
        extra_kwargs = {
            'user': {'write_only': True}
        }


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            name="Пример пользователя",
            value={
                "id": 1,
                "first_name": "Иван",
                "last_name": "Иванов",
                "email": "ivanov@example.com",
                "company": "ООО Ромашка",
                "position": "Директор",
                "contacts": []
            }
        )
    ]
)
class UserSerializer(serializers.ModelSerializer):
    contacts = ContactSerializer(read_only=True, many=True)

    class Meta:
        model = User
        fields = ('id', 'first_name', 'last_name', 'email', 'company', 'position', 'contacts')
        read_only_fields = ('id',)


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            name="Пример категории",
            value={
                "id": 1,
                "name": "Электроника"
            }
        )
    ]
)
class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ('id', 'name',)
        read_only_fields = ('id',)


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            name="Пример магазина",
            value={
                "id": 1,
                "name": "Магазин Электроники",
                "state": True
            }
        )
    ]
)
class ShopSerializer(serializers.ModelSerializer):
    class Meta:
        model = Shop
        fields = ('id', 'name', 'state',)
        read_only_fields = ('id',)


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            name="Пример продукта",
            value={
                "name": "Смартфон",
                "category": "Электроника"
            }
        )
    ]
)
class ProductSerializer(serializers.ModelSerializer):
    category = serializers.StringRelatedField()

    class Meta:
        model = Product
        fields = ('name', 'category',)


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            name="Пример параметра продукта",
            value={
                "parameter": "Цвет",
                "value": "Черный"
            }
        )
    ]
)
class ProductParameterSerializer(serializers.ModelSerializer):
    parameter = serializers.StringRelatedField()

    class Meta:
        model = ProductParameter
        fields = ('parameter', 'value',)


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            name="Пример информации о продукте",
            value={
                "id": 1,
                "model": "Galaxy S21",
                "product": {
                    "name": "Смартфон",
                    "category": "Электроника"
                },
                "shop": 1,
                "quantity": 10,
                "price": 70000,
                "price_rrc": 75000,
                "product_parameters": [
                    {"parameter": "Цвет", "value": "Черный"}
                ]
            }
        )
    ]
)
class ProductInfoSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)
    product_parameters = ProductParameterSerializer(read_only=True, many=True)

    class Meta:
        model = ProductInfo
        fields = ('id', 'model', 'product', 'shop', 'quantity', 'price', 'price_rrc', 'product_parameters',)
        read_only_fields = ('id',)


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            name="Пример элемента заказа",
            value={
                "id": 1,
                "product_info": 1,
                "quantity": 2,
                "order": 1
            }
        )
    ]
)
class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = ('id', 'product_info', 'quantity', 'order',)
        read_only_fields = ('id',)
        extra_kwargs = {
            'order': {'write_only': True}
        }


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            name="Пример заказа",
            value={
                "id": 1,
                "ordered_items": [
                    {
                        "id": 1,
                        "product_info": {
                            "id": 1,
                            "model": "Galaxy S21",
                            "product": {
                                "name": "Смартфон",
                                "category": "Электроника"
                            },
                            "shop": 1,
                            "quantity": 10,
                            "price": 70000,
                            "price_rrc": 75000,
                            "product_parameters": [
                                {"parameter": "Цвет", "value": "Черный"}
                            ]
                        },
                        "quantity": 2
                    }
                ],
                "state": "Создан",
                "dt": "2024-01-01T12:00:00Z",
                "total_sum": 140000,
                "contact": {
                    "city": "Москва",
                    "street": "Тверская",
                    "house": "1",
                    "structure": "2",
                    "building": "3",
                    "apartment": "45",
                    "phone": "+79161234567"
                }
            }
        )
    ]
)
class OrderSerializer(serializers.ModelSerializer):
    ordered_items = OrderItemSerializer(read_only=True, many=True)
    total_sum = serializers.IntegerField()
    contact = ContactSerializer(read_only=True)

    class Meta:
        model = Order
        fields = ('id', 'ordered_items', 'state', 'dt', 'total_sum', 'contact',)
        read_only_fields = ('id',)
