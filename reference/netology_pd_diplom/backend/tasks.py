# backend/tasks.py
from celery import shared_task
from django.core.mail import EmailMultiAlternatives
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError
from django.conf import settings
import yaml
import requests
from .models import Shop, Category, Product, ProductInfo, Parameter, ProductParameter, User


@shared_task(bind=True, max_retries=3)
def send_email(self, subject, message, recipient_list):
    try:
        msg = EmailMultiAlternatives(
            subject=subject,
            body=message,
            from_email=settings.EMAIL_HOST_USER,
            to=recipient_list
        )
        msg.send()
    except Exception as e:
        self.retry(exc=e, countdown=60)  # Повторить через 60 секунд


def load_data_to_db(data, shop):
    """
    Загрузка данных из словаря в базу данных для указанного магазина.
    """
    from django.db import transaction

    with transaction.atomic():
        # Обновляем или создаем категории
        for category in data.get('categories', []):
            category_obj, _ = Category.objects.get_or_create(
                id=category['id'],
                defaults={'name': category['name']}
            )
            if category_obj.name != category['name']:
                category_obj.name = category['name']
                category_obj.save()
            category_obj.shops.add(shop)
            category_obj.save()

        # Удаляем старую информацию о товарах для этого магазина
        ProductInfo.objects.filter(shop=shop).delete()

        # Обрабатываем товары
        for item in data.get('goods', []):
            product, _ = Product.objects.get_or_create(
                name=item['name'],
                category_id=item['category'],
                defaults={'name': item['name']}
            )
            product_info = ProductInfo.objects.create(
                product=product,
                external_id=item['id'],
                model=item.get('model', ''),
                price=item['price'],
                price_rrc=item.get('price_rrc', 0),
                quantity=item['quantity'],
                shop=shop
            )
            for param_name, param_value in item.get('parameters', {}).items():
                parameter, _ = Parameter.objects.get_or_create(name=param_name)
                ProductParameter.objects.create(
                    product_info=product_info,
                    parameter=parameter,
                    value=param_value
                )


@shared_task
def do_import(shop_id):
    # Получаем магазин по ID
    try:
        shop = Shop.objects.get(id=shop_id)
    except Shop.DoesNotExist:
        # Логируем ошибку или уведомляем администратора
        print(f"Магазин с ID {shop_id} не найден.")
        return

    url = shop.url

    # Проверка наличия URL
    if not url:
        # Нет URL для импорта, логируем или уведомляем администратора
        print(f"У магазина '{shop.name}' не указан URL для импорта.")
        return

    # Проверяем, что URL валидный
    validate_url = URLValidator()
    try:
        validate_url(url)
    except ValidationError as e:
        # URL невалидный, логируем или уведомляем администратора
        print(f"Некорректный URL '{url}' для магазина '{shop.name}': {str(e)}")
        return

    try:
        # Получаем данные из URL
        response = requests.get(url)
        response.raise_for_status()
        data = yaml.safe_load(response.content)

        # Загружаем данные в базу данных
        load_data_to_db(data, shop)

        print(f"Данные успешно импортированы для магазина '{shop.name}'.")
    except requests.exceptions.RequestException as e:
        # Обработка ошибок запроса
        print(f"Ошибка при запросе к URL '{url}' для магазина '{shop.name}': {str(e)}")
    except yaml.YAMLError as e:
        # Ошибка при разборе YAML
        print(f"Ошибка при обработке YAML для магазина '{shop.name}': {str(e)}")
    except Exception as e:
        # Непредвиденная ошибка
        print(f"Непредвиденная ошибка при импорте данных для магазина '{shop.name}': {str(e)}")

