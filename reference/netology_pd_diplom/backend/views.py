from distutils.util import strtobool
from rest_framework.request import Request
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import IntegrityError
from django.db.models import Q, Sum, F
from django.http import JsonResponse

from django.core.files.storage import default_storage
from django.conf import settings
from .tasks import do_import
import yaml
import logging
import sentry_sdk
import requests

from requests import get
from rest_framework.authtoken.models import Token
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework.throttling import SimpleRateThrottle

from drf_spectacular.utils import extend_schema, OpenApiExample, OpenApiResponse, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from ujson import loads as load_json

from backend.models import Shop, Category, Product, ProductInfo, Parameter, ProductParameter, Order, OrderItem, \
    Contact, ConfirmEmailToken
from backend.serializers import UserSerializer, CategorySerializer, ShopSerializer, ProductInfoSerializer, \
    OrderItemSerializer, OrderSerializer, ContactSerializer
from backend.signals import new_user_registered, new_order


class RegisterAccount(APIView):
    """
    Для регистрации покупателей
    """

    @extend_schema(
        request=UserSerializer,
        responses={
            200: OpenApiResponse(
                description='Успешная регистрация',
                examples=[
                    OpenApiExample(
                        name="Успех",
                        value={"Status": True}
                    )
                ]
            ),
            400: OpenApiResponse(
                description='Ошибка валидации',
                examples=[
                    OpenApiExample(
                        name="Ошибка валидации пароля",
                        value={"Status": False, "Errors": {"password": ["This password is too short."]}}
                    ),
                    OpenApiExample(
                        name="Недостаточно данных",
                        value={"Status": False, "Errors": "Не указаны все необходимые аргументы"}
                    )
                ]
            )
        },
        examples=[
            OpenApiExample(
                name="Успешная регистрация",
                value={
                    "first_name": "Иван",
                    "last_name": "Иванов",
                    "email": "ivanov@example.com",
                    "password": "securepassword123",
                    "company": "ООО Ромашка",
                    "position": "Директор"
                }
            ),
            OpenApiExample(
                name="Ошибка валидации",
                value={"Status": False, "Errors": {"email": "Уже существует"}},
                response_only=True
            )
        ]
    )

    # Регистрация методом POST
    def post(self, request, *args, **kwargs):
        """
            Process a POST request and create a new user.

            Args:
                request (Request): The Django request object.

            Returns:
                JsonResponse: The response indicating the status of the operation and any errors.
            """
        # проверяем обязательные аргументы
        if {'first_name', 'last_name', 'email', 'password', 'company', 'position'}.issubset(request.data):

            # проверяем пароль на сложность
            sad = 'asd'
            try:
                validate_password(request.data['password'])
            except Exception as password_error:
                # Логируем ошибку в Sentry
                sentry_sdk.capture_exception(password_error)
                error_array = []
                # noinspection PyTypeChecker
                for item in password_error:
                    error_array.append(item)
                return JsonResponse({'Status': False, 'Errors': {'password': error_array}})
            else:
                # проверяем данные для уникальности имени пользователя

                user_serializer = UserSerializer(data=request.data)
                if user_serializer.is_valid():
                    # сохраняем пользователя
                    user = user_serializer.save()
                    user.set_password(request.data['password'])
                    user.save()
                    return JsonResponse({'Status': True})
                else:
                    return JsonResponse({'Status': False, 'Errors': user_serializer.errors})

        return JsonResponse({'Status': False, 'Errors': 'Не указаны все необходимые аргументы'})


class ConfirmAccount(APIView):
    """
    Класс для подтверждения почтового адреса
    """

    @extend_schema(
        description="Подтверждение почтового адреса пользователя по email и токену, высланному на почту.",
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "email": {"type": "string", "example": "john@example.com"},
                    "token": {"type": "string", "example": "abcd1234token"}
                },
                "required": ["email", "token"]
            }
        },
        responses={
            200: OpenApiResponse(
                description='Успешное подтверждение email',
                examples=[
                    OpenApiExample(
                        name="Успех",
                        value={"Status": True}
                    )
                ]
            ),
            400: OpenApiResponse(
                description='Ошибка валидации',
                examples=[
                    OpenApiExample(
                        name="Неверный токен или email",
                        value={"Status": False, "Errors": "Неправильно указан токен или email"}
                    ),
                    OpenApiExample(
                        name="Недостаточно данных",
                        value={"Status": False, "Errors": "Не указаны все необходимые аргументы"}
                    )
                ]
            )
        },
        examples=[
            OpenApiExample(
                name='Пример запроса',
                request_only=True,
                value={
                    "email": "john@example.com",
                    "token": "abcd1234token"
                }
            )
        ]
    )

    # Регистрация методом POST
    def post(self, request, *args, **kwargs):
        """
                Подтверждает почтовый адрес пользователя.

                Args:
                - request (Request): The Django request object.

                Returns:
                - JsonResponse: The response indicating the status of the operation and any errors.
                """
        # проверяем обязательные аргументы
        if {'email', 'token'}.issubset(request.data):

            token = ConfirmEmailToken.objects.filter(user__email=request.data['email'],
                                                     key=request.data['token']).first()
            if token:
                token.user.is_active = True
                token.user.save()
                token.delete()
                return JsonResponse({'Status': True})
            else:
                return JsonResponse({'Status': False, 'Errors': 'Неправильно указан токен или email'})

        return JsonResponse({'Status': False, 'Errors': 'Не указаны все необходимые аргументы'})


class AccountDetails(APIView):
    """
    A class for managing user account details.

    Methods:
    - get: Retrieve the details of the authenticated user.
    - post: Update the account details of the authenticated user.

    Attributes:
    - None
    """

    @extend_schema(
        description="Retrieve the details of the authenticated user.",
        responses={
            200: OpenApiResponse(
                response=UserSerializer,
                description="Success",
                examples=[
                    OpenApiExample(
                        name="Успех",
                        value={
                            "id": 1,
                            "first_name": "John",
                            "last_name": "Doe",
                            "email": "john@example.com",
                            "company": "Acme Inc",
                            "position": "Manager"
                        }
                    )
                ]
            ),
            403: OpenApiResponse(
                description="Unauthorized: user not authenticated",
                examples=[
                    OpenApiExample(
                        name="Пользователь не аутентифицирован",
                        value={"Status": False, "Error": "Log in required"}
                    )
                ]
            )
        }
    )
    # получить данные
    def get(self, request: Request, *args, **kwargs):
        """
               Retrieve the details of the authenticated user.

               Args:
               - request (Request): The Django request object.

               Returns:
               - Response: The response containing the details of the authenticated user.
        """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)

        serializer = UserSerializer(request.user)
        return Response(serializer.data)

    @extend_schema(
        description="Update the account details of the authenticated user.",
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "first_name": {"type": "string", "example": "John"},
                    "last_name": {"type": "string", "example": "Doe"},
                    "email": {"type": "string", "example": "john@example.com"},
                    "password": {"type": "string", "example": "NewStr0ngPass!"},
                    "company": {"type": "string", "example": "Acme Inc"},
                    "position": {"type": "string", "example": "CTO"}
                }
            }
        },
        responses={
            200: OpenApiResponse(
                description="Profile updated successfully",
                examples=[
                    OpenApiExample(
                        name="Успех",
                        value={"Status": True}
                    )
                ]
            ),
            400: OpenApiResponse(
                description="Validation error",
                examples=[
                    OpenApiExample(
                        name="Ошибка валидации пароля",
                        value={"Status": False, "Errors": {"password": ["This password is too short."]}}
                    ),
                    OpenApiExample(
                        name="Ошибка валидации других полей",
                        value={"Status": False, "Errors": {"email": ["Enter a valid email address."]}}
                    )
                ]
            ),
            403: OpenApiResponse(
                description="Unauthorized: user not authenticated",
                examples=[
                    OpenApiExample(
                        name="Пользователь не аутентифицирован",
                        value={"Status": False, "Error": "Log in required"}
                    )
                ]
            )
        },
        examples=[
            OpenApiExample(
                name="Пример запроса на обновление",
                request_only=True,
                value={
                    "email": "john_new@example.com",
                    "password": "NewStr0ngPass!",
                    "company": "Acme Corp",
                    "position": "Head of Engineering"
                }
            )
        ]
    )
    # Редактирование методом POST
    def post(self, request, *args, **kwargs):
        """
                Update the account details of the authenticated user.

                Args:
                - request (Request): The Django request object.

                Returns:
                - JsonResponse: The response indicating the status of the operation and any errors.
                """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)
        # проверяем обязательные аргументы

        if 'password' in request.data:
            errors = {}
            # проверяем пароль на сложность
            try:
                validate_password(request.data['password'])
            except Exception as password_error:
                # Логируем ошибку в Sentry
                sentry_sdk.capture_exception(password_error)
                error_array = []
                # noinspection PyTypeChecker
                for item in password_error:
                    error_array.append(item)
                return JsonResponse({'Status': False, 'Errors': {'password': error_array}})
            else:
                request.user.set_password(request.data['password'])

        # проверяем остальные данные
        user_serializer = UserSerializer(request.user, data=request.data, partial=True)
        if user_serializer.is_valid():
            user_serializer.save()
            return JsonResponse({'Status': True})
        else:
            return JsonResponse({'Status': False, 'Errors': user_serializer.errors})


class LoginAttemptThrottle(SimpleRateThrottle):
    scope = 'login'

    def get_cache_key(self, request, view):
        # IP-адрес клиента используется как ключ
        if not request.user.is_authenticated:
            return self.get_ident(request)
        return None


class LoginAccount(APIView):
    """
    Класс для авторизации пользователей
    """

    permission_classes = [AllowAny]
    throttle_classes = [LoginAttemptThrottle]

    @extend_schema(
        request={"type": "object", "properties": {"email": {"type": "string"}, "password": {"type": "string"}}},
        responses={200: {"type": "object", "properties": {"Status": {"type": "boolean"}, "Token": {"type": "string"}}}},
        examples=[
            OpenApiExample(
                name="Успешная авторизация",
                value={"email": "ivanov@example.com", "password": "securepassword123"}
            ),
            OpenApiExample(
                name="Ошибка авторизации",
                value={"Status": False, "Errors": "Не удалось авторизовать"},
                response_only=True
            )
        ]
    )
    # Авторизация методом POST
    def post(self, request, *args, **kwargs):
        """
                Authenticate a user.

                Args:
                    request (Request): The Django request object.

                Returns:
                    JsonResponse: The response indicating the status of the operation and any errors.
                """
        if {'email', 'password'}.issubset(request.data):
            user = authenticate(request, username=request.data['email'], password=request.data['password'])

            if user is not None:
                if user.is_active:
                    token, _ = Token.objects.get_or_create(user=user)

                    return JsonResponse({'Status': True, 'Token': token.key})

            return JsonResponse({'Status': False, 'Errors': 'Не удалось авторизовать'})

        return JsonResponse({'Status': False, 'Errors': 'Не указаны все необходимые аргументы'})


class CategoryView(ListAPIView):
    """
    Класс для просмотра категорий
    """
    queryset = Category.objects.all()
    serializer_class = CategorySerializer


class ShopView(ListAPIView):
    """
    Класс для просмотра списка магазинов
    """
    queryset = Shop.objects.filter(state=True)
    serializer_class = ShopSerializer


class ProductInfoView(APIView):
    """
        A class for searching products.

        Methods:
        - get: Retrieve the product information based on the specified filters.

        Attributes:
        - None
        """

    @extend_schema(
        description="Retrieve the product information based on optional filters: 'shop_id' and 'category_id'.",
        parameters=[
            OpenApiParameter(
                name='shop_id',
                description='ID of the shop to filter the products by',
                required=False,
                type=OpenApiTypes.INT
            ),
            OpenApiParameter(
                name='category_id',
                description='ID of the category to filter the products by',
                required=False,
                type=OpenApiTypes.INT
            )
        ],
        responses={
            200: OpenApiResponse(
                response=ProductInfoSerializer(many=True),
                description="List of product information based on the provided filters.",
                examples=[
                    OpenApiExample(
                        name="Ответ без фильтров",
                        value=[
                            {
                                "product": {
                                    "name": "Product A",
                                    "category": {
                                        "id": 1,
                                        "name": "Electronics"
                                    }
                                },
                                "shop": {
                                    "id": 2,
                                    "name": "Best Shop"
                                },
                                "quantity": 10,
                                "price": 1000,
                                "product_parameters": [
                                    {
                                        "parameter": {"name": "Color"},
                                        "value": "Black"
                                    },
                                    {
                                        "parameter": {"name": "Size"},
                                        "value": "M"
                                    }
                                ]
                            }
                        ]
                    ),
                    OpenApiExample(
                        name="Ответ с фильтрацией по магазину",
                        value=[]
                    )
                ]
            )
        }
    )
    def get(self, request: Request, *args, **kwargs):
        """
               Retrieve the product information based on the specified filters.

               Args:
               - request (Request): The Django request object.

               Returns:
               - Response: The response containing the product information.
               """
        query = Q(shop__state=True)
        shop_id = request.query_params.get('shop_id')
        category_id = request.query_params.get('category_id')

        if shop_id:
            query = query & Q(shop_id=shop_id)

        if category_id:
            query = query & Q(product__category_id=category_id)

        # фильтруем и отбрасываем дубликаты
        queryset = ProductInfo.objects.filter(
            query).select_related(
            'shop', 'product__category').prefetch_related(
            'product_parameters__parameter').distinct()

        serializer = ProductInfoSerializer(queryset, many=True)

        return Response(serializer.data)


class BasketView(APIView):
    """
    A class for managing the user's shopping basket.

    Methods:
    - get: Retrieve the items in the user's basket.
    - post: Add an item to the user's basket.
    - put: Update the quantity of an item in the user's basket.
    - delete: Remove an item from the user's basket.

    Attributes:
    - None
    """
    @extend_schema(
        responses=OrderSerializer(many=True),
        examples=[
            OpenApiExample(
                name="Содержимое корзины",
                value=[
                    {
                        "id": 1,
                        "ordered_items": [
                            {
                                "id": 1,
                                "product_info": {
                                    "id": 1,
                                    "model": "Galaxy S21",
                                    "product": {"name": "Смартфон", "category": "Электроника"},
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
                        "state": "basket",
                        "total_sum": 140000,
                        "contact": None
                    }
                ],
                response_only=True
            )
        ]
    )
    # получить корзину
    def get(self, request, *args, **kwargs):
        """
                Retrieve the items in the user's basket.

                Args:
                - request (Request): The Django request object.

                Returns:
                - Response: The response containing the items in the user's basket.
                """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)
        basket = Order.objects.filter(
            user_id=request.user.id, state='basket').prefetch_related(
            'ordered_items__product_info__product__category',
            'ordered_items__product_info__product_parameters__parameter').annotate(
            total_sum=Sum(F('ordered_items__quantity') * F('ordered_items__product_info__price'))).distinct()

        serializer = OrderSerializer(basket, many=True)
        return Response(serializer.data)

    # редактировать корзину
    def post(self, request, *args, **kwargs):
        """
               Add an items to the user's basket.

               Args:
               - request (Request): The Django request object.

               Returns:
               - JsonResponse: The response indicating the status of the operation and any errors.
               """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)

        items_sting = request.data.get('items')
        if items_sting:
            try:
                items_dict = load_json(items_sting)
            except ValueError as e:
                # Логируем ошибку в Sentry
                sentry_sdk.capture_exception(e)
                return JsonResponse({'Status': False, 'Errors': 'Неверный формат запроса'})
            else:
                basket, _ = Order.objects.get_or_create(user_id=request.user.id, state='basket')
                objects_created = 0
                for order_item in items_dict:
                    order_item.update({'order': basket.id})
                    serializer = OrderItemSerializer(data=order_item)
                    if serializer.is_valid():
                        try:
                            serializer.save()
                        except IntegrityError as error:
                            # Логируем ошибку в Sentry
                            sentry_sdk.capture_exception(error)
                            return JsonResponse({'Status': False, 'Errors': str(error)})
                        else:
                            objects_created += 1

                    else:

                        return JsonResponse({'Status': False, 'Errors': serializer.errors})

                return JsonResponse({'Status': True, 'Создано объектов': objects_created})
        return JsonResponse({'Status': False, 'Errors': 'Не указаны все необходимые аргументы'})

    # удалить товары из корзины
    def delete(self, request, *args, **kwargs):
        """
                Remove  items from the user's basket.

                Args:
                - request (Request): The Django request object.

                Returns:
                - JsonResponse: The response indicating the status of the operation and any errors.
                """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)

        items_sting = request.data.get('items')
        if items_sting:
            items_list = items_sting.split(',')
            basket, _ = Order.objects.get_or_create(user_id=request.user.id, state='basket')
            query = Q()
            objects_deleted = False
            for order_item_id in items_list:
                if order_item_id.isdigit():
                    query = query | Q(order_id=basket.id, id=order_item_id)
                    objects_deleted = True

            if objects_deleted:
                deleted_count = OrderItem.objects.filter(query).delete()[0]
                return JsonResponse({'Status': True, 'Удалено объектов': deleted_count})
        return JsonResponse({'Status': False, 'Errors': 'Не указаны все необходимые аргументы'})

    # добавить позиции в корзину
    def put(self, request, *args, **kwargs):
        """
               Update the items in the user's basket.

               Args:
               - request (Request): The Django request object.

               Returns:
               - JsonResponse: The response indicating the status of the operation and any errors.
               """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)

        items_sting = request.data.get('items')
        if items_sting:
            try:
                items_dict = load_json(items_sting)
            except ValueError as e:
                # Логируем ошибку в Sentry
                sentry_sdk.capture_exception(e)
                return JsonResponse({'Status': False, 'Errors': 'Неверный формат запроса'})
            else:
                basket, _ = Order.objects.get_or_create(user_id=request.user.id, state='basket')
                objects_updated = 0
                for order_item in items_dict:
                    if type(order_item['id']) == int and type(order_item['quantity']) == int:
                        objects_updated += OrderItem.objects.filter(order_id=basket.id, id=order_item['id']).update(
                            quantity=order_item['quantity'])

                return JsonResponse({'Status': True, 'Обновлено объектов': objects_updated})
        return JsonResponse({'Status': False, 'Errors': 'Не указаны все необходимые аргументы'})


class PartnerUpdate(APIView):
    """
    A class for updating partner information.

    Methods:
    - post: Update the partner information.

    Attributes:
    - None
    """

    @extend_schema(
        description="Update the partner (shop) information by providing either a 'url' to a YAML file or uploading a local 'file' with product data.",
        request={
            "multipart/form-data": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "format": "uri", "description": "URL to a YAML file with product data"},
                    "file": {"type": "string", "format": "binary", "description": "Local YAML file with product data"}
                }
            }
        },
        responses={
            202: OpenApiResponse(
                description="Data import started successfully",
                examples=[
                    OpenApiExample(
                        name="Успех (URL)",
                        value={"Status": True, "Message": "Данные загружаются"}
                    ),
                    OpenApiExample(
                        name="Успех (File)",
                        value={"Status": True, "Message": "Данные загружаются"}
                    )
                ]
            ),
            400: OpenApiResponse(
                description="Validation error or bad request",
                examples=[
                    OpenApiExample(
                        name="Отсутствуют аргументы",
                        value={"Status": False, "Error": "Не указаны все необходимые аргументы"}
                    ),
                    OpenApiExample(
                        name="Неверный формат URL",
                        value={"Status": False, "Error": "Enter a valid URL."}
                    ),
                    OpenApiExample(
                        name="Ошибка при запросе URL",
                        value={"Status": False, "Error": "Ошибка при запросе URL: <details>"}
                    ),
                    OpenApiExample(
                        name="Ошибка YAML",
                        value={"Status": False, "Error": "Ошибка при обработке YAML: <details>"}
                    )
                ]
            ),
            403: OpenApiResponse(
                description="Unauthorized or forbidden",
                examples=[
                    OpenApiExample(
                        name="Не аутентифицирован",
                        value={"Status": False, "Error": "Требуется аутентификация"}
                    ),
                    OpenApiExample(
                        name="Не магазин",
                        value={"Status": False, "Error": "Только для магазинов"}
                    )
                ]
            ),
            500: OpenApiResponse(
                description="Internal server error",
                examples=[
                    OpenApiExample(
                        name="Непредвиденная ошибка",
                        value={"Status": False, "Error": "Непредвиденная ошибка: <details>"}
                    )
                ]
            )
        },
        examples=[
            OpenApiExample(
                name="Пример с URL",
                request_only=True,
                value={
                    "url": "https://raw.githubusercontent.com/netology-code/python-final-diplom/master/data/shop1.yaml"
                }
            ),
            OpenApiExample(
                name="Пример с файлом",
                request_only=True,
                value={
                    # Это пример multipart-запроса
                    # В реальном запросе вместо value здесь будет загружен файл
                    "file": "(binary data)"
                }
            )
        ]
    )
    def post(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Требуется аутентификация'}, status=403)

        if request.user.type != 'shop':
            return JsonResponse({'Status': False, 'Error': 'Только для магазинов'}, status=403)

        # Проверка наличия URL
        url = request.data.get('url')
        if url:
            return self._process_url(url, request.user)

        # Проверка загрузки файла
        file = request.FILES.get('file')
        if file:
            return self._process_file(file, request.user)

        return JsonResponse({'Status': False, 'Error': 'Не указаны все необходимые аргументы'}, status=400)

    def _process_url(self, url, user):
        """
        Обработка данных из URL
        """
        validate_url = URLValidator()
        try:
            validate_url(url)
        except ValidationError as e:
            # Логируем ошибку в Sentry
            sentry_sdk.capture_exception(e)
            return JsonResponse({'Status': False, 'Error': str(e)}, status=400)

        try:
            response = requests.get(url)
            response.raise_for_status()
            data = yaml.safe_load(response.content)

            # Запуск задачи Celery для загрузки данных
            do_import.delay(data, user.id)

            return JsonResponse({'Status': True, 'Message': 'Данные загружаются'}, status=202)
        except requests.exceptions.RequestException as e:
            # Логируем ошибку в Sentry
            sentry_sdk.capture_exception(e)
            return JsonResponse({'Status': False, 'Error': f'Ошибка при запросе URL: {str(e)}'}, status=400)
        except yaml.YAMLError as e:
            # Логируем ошибку в Sentry
            sentry_sdk.capture_exception(e)
            return JsonResponse({'Status': False, 'Error': f'Ошибка при обработке YAML: {str(e)}'}, status=400)
        except Exception as e:
            # Логируем ошибку в Sentry
            sentry_sdk.capture_exception(e)
            return JsonResponse({'Status': False, 'Error': f'Непредвиденная ошибка: {str(e)}'}, status=500)

    def _process_file(self, file, user):
        """
        Обработка данных из локального файла
        """
        try:
            # Чтение содержимого файла
            data = yaml.safe_load(file.read())

            # Запуск задачи Celery для загрузки данных
            do_import.delay(data, user.id)

            return JsonResponse({'Status': True, 'Message': 'Данные загружаются'}, status=202)
        except yaml.YAMLError as e:
            # Логируем ошибку в Sentry
            sentry_sdk.capture_exception(e)
            return JsonResponse({'Status': False, 'Error': f'Ошибка при обработке YAML: {str(e)}'}, status=400)
        except Exception as e:
            # Логируем ошибку в Sentry
            sentry_sdk.capture_exception(e)
            return JsonResponse({'Status': False, 'Error': f'Непредвиденная ошибка: {str(e)}'}, status=500)


class PartnerState(APIView):
    """
       A class for managing partner state.

       Methods:
       - get: Retrieve the state of the partner.

       Attributes:
       - None
       """

    @extend_schema(
        description="Retrieve the state of the authenticated partner (shop).",
        responses={
            200: OpenApiResponse(
                response=ShopSerializer,
                description="Current state of the shop.",
                examples=[
                    OpenApiExample(
                        name="Успех",
                        value={
                            "id": 1,
                            "name": "My Shop",
                            "state": True
                        }
                    )
                ]
            ),
            403: OpenApiResponse(
                description="User not authenticated or not a shop",
                examples=[
                    OpenApiExample(
                        name="Не аутентифицирован",
                        value={"Status": False, "Error": "Log in required"}
                    ),
                    OpenApiExample(
                        name="Не магазин",
                        value={"Status": False, "Error": "Только для магазинов"}
                    )
                ]
            )
        }
    )
    # получить текущий статус
    def get(self, request, *args, **kwargs):
        """
               Retrieve the state of the partner.

               Args:
               - request (Request): The Django request object.

               Returns:
               - Response: The response containing the state of the partner.
               """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)

        if request.user.type != 'shop':
            return JsonResponse({'Status': False, 'Error': 'Только для магазинов'}, status=403)

        shop = request.user.shop
        serializer = ShopSerializer(shop)
        return Response(serializer.data)

    @extend_schema(
        description="Update the partner state to True (active) or False (inactive).",
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "state": {"type": "string", "example": "true"}
                },
                "required": ["state"]
            }
        },
        responses={
            200: OpenApiResponse(
                description="State updated successfully",
                examples=[
                    OpenApiExample(
                        name="Успех",
                        value={"Status": True}
                    )
                ]
            ),
            400: OpenApiResponse(
                description="Invalid arguments",
                examples=[
                    OpenApiExample(
                        name="Не указаны аргументы",
                        value={"Status": False, "Errors": "Не указаны все необходимые аргументы"}
                    )
                ]
            ),
            403: OpenApiResponse(
                description="User not authenticated or not a shop",
                examples=[
                    OpenApiExample(
                        name="Не аутентифицирован",
                        value={"Status": False, "Error": "Log in required"}
                    ),
                    OpenApiExample(
                        name="Не магазин",
                        value={"Status": False, "Error": "Только для магазинов"}
                    )
                ]
            ),
            500: OpenApiResponse(
                description="ValueError or other server error",
                examples=[
                    OpenApiExample(
                        name="Ошибка преобразования",
                        value={"Status": False, "Errors": "invalid literal for int() with base 10: 'foo'"}
                    )
                ]
            )
        },
        examples=[
            OpenApiExample(
                name="Пример запроса",
                request_only=True,
                value={"state": "false"}
            )
        ]
    )
    # изменить текущий статус
    def post(self, request, *args, **kwargs):
        """
               Update the state of a partner.

               Args:
               - request (Request): The Django request object.

               Returns:
               - JsonResponse: The response indicating the status of the operation and any errors.
               """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)

        if request.user.type != 'shop':
            return JsonResponse({'Status': False, 'Error': 'Только для магазинов'}, status=403)
        state = request.data.get('state')
        if state:
            try:
                Shop.objects.filter(user_id=request.user.id).update(state=strtobool(state))
                return JsonResponse({'Status': True})
            except ValueError as error:
                # Логируем ошибку в Sentry
                sentry_sdk.capture_exception(error)
                return JsonResponse({'Status': False, 'Errors': str(error)})

        return JsonResponse({'Status': False, 'Errors': 'Не указаны все необходимые аргументы'})


class PartnerOrders(APIView):
    """
    Класс для получения заказов поставщиками
     Methods:
    - get: Retrieve the orders associated with the authenticated partner.

    Attributes:
    - None
    """

    @extend_schema(
        description="Retrieve all non-basket orders related to the authenticated partner (shop).",
        responses={
            200: OpenApiResponse(
                response=OrderSerializer(many=True),
                description="List of orders for the partner.",
                examples=[
                    OpenApiExample(
                        name="Успех",
                        value=[
                            {
                                "id": 10,
                                "state": "new",
                                "contact": {
                                    "id": 5,
                                    "city": "Moscow",
                                    "street": "Tverskaya",
                                    "phone": "+7 123 456-78-90"
                                },
                                "total_sum": 3000,
                                "ordered_items": [
                                    {
                                        "product_info": {
                                            "product": {
                                                "name": "Laptop",
                                                "category": {
                                                    "id": 2,
                                                    "name": "Electronics"
                                                }
                                            },
                                            "shop": {
                                                "id": 3,
                                                "name": "Best Shop"
                                            },
                                            "quantity": 1,
                                            "price": 3000
                                        },
                                        "quantity": 1
                                    }
                                ]
                            }
                        ]
                    )
                ]
            ),
            403: OpenApiResponse(
                description="User not authenticated or not a shop",
                examples=[
                    OpenApiExample(
                        name="Не аутентифицирован",
                        value={"Status": False, "Error": "Log in required"}
                    ),
                    OpenApiExample(
                        name="Не магазин",
                        value={"Status": False, "Error": "Только для магазинов"}
                    )
                ]
            )
        }
    )
    def get(self, request, *args, **kwargs):
        """
               Retrieve the orders associated with the authenticated partner.

               Args:
               - request (Request): The Django request object.

               Returns:
               - Response: The response containing the orders associated with the partner.
               """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)

        if request.user.type != 'shop':
            return JsonResponse({'Status': False, 'Error': 'Только для магазинов'}, status=403)

        order = Order.objects.filter(
            ordered_items__product_info__shop__user_id=request.user.id).exclude(state='basket').prefetch_related(
            'ordered_items__product_info__product__category',
            'ordered_items__product_info__product_parameters__parameter').select_related('contact').annotate(
            total_sum=Sum(F('ordered_items__quantity') * F('ordered_items__product_info__price'))).distinct()

        serializer = OrderSerializer(order, many=True)
        return Response(serializer.data)


class ContactView(APIView):
    """
       A class for managing contact information.

       Methods:
       - get: Retrieve the contact information of the authenticated user.
       - post: Create a new contact for the authenticated user.
       - put: Update the contact information of the authenticated user.
       - delete: Delete the contact of the authenticated user.

       Attributes:
       - None
       """

    @extend_schema(
        description="Retrieve all contacts associated with the authenticated user.",
        responses={
            200: OpenApiResponse(
                response=ContactSerializer(many=True),
                description="List of user's contacts.",
                examples=[
                    OpenApiExample(
                        name="Успех",
                        value=[
                            {
                                "id": 1,
                                "city": "Moscow",
                                "street": "Arbat",
                                "phone": "+7 999 111-22-33"
                            },
                            {
                                "id": 2,
                                "city": "Saint Petersburg",
                                "street": "Nevsky Prospect",
                                "phone": "+7 999 444-55-66"
                            }
                        ]
                    )
                ]
            ),
            403: OpenApiResponse(
                description="User not authenticated",
                examples=[
                    OpenApiExample(
                        name="Не аутентифицирован",
                        value={"Status": False, "Error": "Log in required"}
                    )
                ]
            )
        }
    )
    # получить мои контакты
    def get(self, request, *args, **kwargs):
        """
               Retrieve the contact information of the authenticated user.

               Args:
               - request (Request): The Django request object.

               Returns:
               - Response: The response containing the contact information.
               """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)
        contact = Contact.objects.filter(
            user_id=request.user.id)
        serializer = ContactSerializer(contact, many=True)
        return Response(serializer.data)

    @extend_schema(
        description="Create a new contact for the authenticated user.",
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "example": "Moscow"},
                    "street": {"type": "string", "example": "Arbat"},
                    "phone": {"type": "string", "example": "+7 999 111-22-33"}
                },
                "required": ["city", "street", "phone"]
            }
        },
        responses={
            200: OpenApiResponse(
                description="Contact created successfully",
                examples=[
                    OpenApiExample(
                        name="Успех",
                        value={"Status": True}
                    )
                ]
            ),
            400: OpenApiResponse(
                description="Validation error",
                examples=[
                    OpenApiExample(
                        name="Недостаточно данных",
                        value={"Status": False, "Errors": "Не указаны все необходимые аргументы"}
                    )
                ]
            ),
            403: OpenApiResponse(
                description="User not authenticated",
                examples=[
                    OpenApiExample(
                        name="Не аутентифицирован",
                        value={"Status": False, "Error": "Log in required"}
                    )
                ]
            )
        },
        examples=[
            OpenApiExample(
                name="Пример запроса",
                request_only=True,
                value={
                    "city": "Moscow",
                    "street": "Arbat",
                    "phone": "+7 999 111-22-33"
                }
            )
        ]
    )
    # добавить новый контакт
    def post(self, request, *args, **kwargs):
        """
               Create a new contact for the authenticated user.

               Args:
               - request (Request): The Django request object.

               Returns:
               - JsonResponse: The response indicating the status of the operation and any errors.
               """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)

        if {'city', 'street', 'phone'}.issubset(request.data):
            request.data._mutable = True
            request.data.update({'user': request.user.id})
            serializer = ContactSerializer(data=request.data)

            if serializer.is_valid():
                serializer.save()
                return JsonResponse({'Status': True})
            else:
                return JsonResponse({'Status': False, 'Errors': serializer.errors})

        return JsonResponse({'Status': False, 'Errors': 'Не указаны все необходимые аргументы'})

    @extend_schema(
        description="Delete contacts by their IDs (comma-separated).",
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "string",
                        "description": "Comma-separated list of contact IDs to delete",
                        "example": "1,2"
                    }
                },
                "required": ["items"]
            }
        },
        responses={
            200: OpenApiResponse(
                description="Contacts deleted successfully",
                examples=[
                    OpenApiExample(
                        name="Успех",
                        value={"Status": True, "Удалено объектов": 2}
                    )
                ]
            ),
            400: OpenApiResponse(
                description="Missing arguments",
                examples=[
                    OpenApiExample(
                        name="Недостаточно данных",
                        value={"Status": False, "Errors": "Не указаны все необходимые аргументы"}
                    )
                ]
            ),
            403: OpenApiResponse(
                description="User not authenticated",
                examples=[
                    OpenApiExample(
                        name="Не аутентифицирован",
                        value={"Status": False, "Error": "Log in required"}
                    )
                ]
            )
        },
        examples=[
            OpenApiExample(
                name="Пример запроса",
                request_only=True,
                value={"items": "1,2"}
            )
        ]
    )
    # удалить контакт
    def delete(self, request, *args, **kwargs):
        """
               Delete the contact of the authenticated user.

               Args:
               - request (Request): The Django request object.

               Returns:
               - JsonResponse: The response indicating the status of the operation and any errors.
               """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)

        items_sting = request.data.get('items')
        if items_sting:
            items_list = items_sting.split(',')
            query = Q()
            objects_deleted = False
            for contact_id in items_list:
                if contact_id.isdigit():
                    query = query | Q(user_id=request.user.id, id=contact_id)
                    objects_deleted = True

            if objects_deleted:
                deleted_count = Contact.objects.filter(query).delete()[0]
                return JsonResponse({'Status': True, 'Удалено объектов': deleted_count})
        return JsonResponse({'Status': False, 'Errors': 'Не указаны все необходимые аргументы'})

    @extend_schema(
        description="Update a contact by its ID.",
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "example": "1"},
                    "city": {"type": "string", "example": "Moscow"},
                    "street": {"type": "string", "example": "Arbat 10"},
                    "phone": {"type": "string", "example": "+7 999 222-33-44"}
                },
                "required": ["id"]
            }
        },
        responses={
            200: OpenApiResponse(
                description="Contact updated successfully",
                examples=[
                    OpenApiExample(
                        name="Успех",
                        value={"Status": True}
                    )
                ]
            ),
            400: OpenApiResponse(
                description="Missing arguments or validation error",
                examples=[
                    OpenApiExample(
                        name="Недостаточно данных",
                        value={"Status": False, "Errors": "Не указаны все необходимые аргументы"}
                    )
                ]
            ),
            403: OpenApiResponse(
                description="User not authenticated",
                examples=[
                    OpenApiExample(
                        name="Не аутентифицирован",
                        value={"Status": False, "Error": "Log in required"}
                    )
                ]
            )
        },
        examples=[
            OpenApiExample(
                name="Пример запроса",
                request_only=True,
                value={
                    "id": "1",
                    "phone": "+7 999 222-33-44"
                }
            )
        ]
    )
    # редактировать контакт
    def put(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            """
                   Update the contact information of the authenticated user.

                   Args:
                   - request (Request): The Django request object.

                   Returns:
                   - JsonResponse: The response indicating the status of the operation and any errors.
                   """
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)

        if 'id' in request.data:
            if request.data['id'].isdigit():
                contact = Contact.objects.filter(id=request.data['id'], user_id=request.user.id).first()
                print(contact)
                if contact:
                    serializer = ContactSerializer(contact, data=request.data, partial=True)
                    if serializer.is_valid():
                        serializer.save()
                        return JsonResponse({'Status': True})
                    else:
                        return JsonResponse({'Status': False, 'Errors': serializer.errors})

        return JsonResponse({'Status': False, 'Errors': 'Не указаны все необходимые аргументы'})


class OrderView(APIView):
    """
    Класс для получения и размешения заказов пользователями
    Methods:
    - get: Retrieve the details of a specific order.
    - post: Create a new order.
    - put: Update the details of a specific order.
    - delete: Delete a specific order.

    Attributes:
    - None
    """

    @extend_schema(
        description="Retrieve all orders (except 'basket') of the authenticated user.",
        responses={
            200: OpenApiResponse(
                response=OrderSerializer(many=True),
                description="List of user orders.",
                examples=[
                    OpenApiExample(
                        name="Успех",
                        value=[
                            {
                                "id": 5,
                                "state": "new",
                                "contact": {
                                    "id": 3,
                                    "city": "Moscow",
                                    "street": "Tverskaya",
                                    "phone": "+7 123 456-78-90"
                                },
                                "total_sum": 2000,
                                "ordered_items": [
                                    {
                                        "product_info": {
                                            "product": {
                                                "name": "Smartphone",
                                                "category": {
                                                    "id": 1,
                                                    "name": "Electronics"
                                                }
                                            },
                                            "shop": {
                                                "id": 2,
                                                "name": "Gadget Store"
                                            },
                                            "quantity": 1,
                                            "price": 2000
                                        },
                                        "quantity": 1
                                    }
                                ]
                            }
                        ]
                    )
                ]
            ),
            403: OpenApiResponse(
                description="User not authenticated",
                examples=[
                    OpenApiExample(
                        name="Не аутентифицирован",
                        value={"Status": False, "Error": "Log in required"}
                    )
                ]
            )
        }
    )
    # получить мои заказы
    def get(self, request, *args, **kwargs):
        """
               Retrieve the details of user orders.

               Args:
               - request (Request): The Django request object.

               Returns:
               - Response: The response containing the details of the order.
               """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)
        order = Order.objects.filter(
            user_id=request.user.id).exclude(state='basket').prefetch_related(
            'ordered_items__product_info__product__category',
            'ordered_items__product_info__product_parameters__parameter').select_related('contact').annotate(
            total_sum=Sum(F('ordered_items__quantity') * F('ordered_items__product_info__price'))).distinct()

        serializer = OrderSerializer(order, many=True)
        return Response(serializer.data)

    @extend_schema(
        description="Place an order from the user's basket by providing the order ID and a contact ID.",
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "example": "5"},
                    "contact": {"type": "string", "example": "3"}
                },
                "required": ["id", "contact"]
            }
        },
        responses={
            200: OpenApiResponse(
                description="Order placed successfully",
                examples=[
                    OpenApiExample(
                        name="Успех",
                        value={"Status": True}
                    )
                ]
            ),
            400: OpenApiResponse(
                description="Validation error",
                examples=[
                    OpenApiExample(
                        name="Неправильно указаны аргументы",
                        value={"Status": False, "Errors": "Неправильно указаны аргументы"}
                    )
                ]
            ),
            403: OpenApiResponse(
                description="User not authenticated",
                examples=[
                    OpenApiExample(
                        name="Не аутентифицирован",
                        value={"Status": False, "Error": "Log in required"}
                    )
                ]
            ),
            400: OpenApiResponse(
                description="Missing arguments",
                examples=[
                    OpenApiExample(
                        name="Недостаточно данных",
                        value={"Status": False, "Errors": "Не указаны все необходимые аргументы"}
                    )
                ]
            )
        },
        examples=[
            OpenApiExample(
                name="Пример запроса",
                request_only=True,
                value={
                    "id": "5",
                    "contact": "3"
                }
            )
        ]
    )
    # разместить заказ из корзины
    def post(self, request, *args, **kwargs):
        """
               Put an order and send a notification.

               Args:
               - request (Request): The Django request object.

               Returns:
               - JsonResponse: The response indicating the status of the operation and any errors.
               """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)

        if {'id', 'contact'}.issubset(request.data):
            if request.data['id'].isdigit():
                try:
                    is_updated = Order.objects.filter(
                        user_id=request.user.id, id=request.data['id']).update(
                        contact_id=request.data['contact'],
                        state='new')
                except IntegrityError as error:
                    # print(error)
                    # Логируем ошибку в Sentry
                    sentry_sdk.capture_exception(error)
                    return JsonResponse({'Status': False, 'Errors': 'Неправильно указаны аргументы'})
                else:
                    if is_updated:
                        new_order.send(sender=self.__class__, user_id=request.user.id)
                        return JsonResponse({'Status': True})

        return JsonResponse({'Status': False, 'Errors': 'Не указаны все необходимые аргументы'})


class ImportProductsView(APIView):
    """
    View для запуска задачи импорта товаров
    """

    def post(self, request, *args, **kwargs):
        file = request.FILES.get('file')
        if file:
            file_path = default_storage.save(file.name, file)
            with open(file_path, 'r') as f:
                yaml_data = f.read()

            # Запускаем асинхронную задачу
            do_import.delay(yaml_data)
            return Response({"status": "Импорт начат"}, status=status.HTTP_200_OK)

        return Response({"error": "Файл не найден"}, status=status.HTTP_400_BAD_REQUEST)


class ErrorAPIView(APIView):
    """
    Этот APIView генерирует исключение для проверки работы Sentry
    """

    def get(self, request, *args, **kwargs):
        # Вызов исключения, чтобы проверить работу Sentry
        try:
            1 / 0  # Делим на ноль, чтобы вызвать ZeroDivisionError
        except ZeroDivisionError as e:
            # Это исключение будет поймано и отправлено в Sentry
            logging.error("Ошибка: деление на ноль")
            # Логируем ошибку в Sentry
            sentry_sdk.capture_exception(e)
            raise e  # Повторно выбрасываем ошибку, чтобы она попала в Sentry
        return Response({"message": "This will not be reached!"}, status=status.HTTP_200_OK)
