# backend/tasks.py
from celery import shared_task
from django.core.mail import EmailMultiAlternatives
from django.conf import settings
import yaml
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


@shared_task
def do_import(data, user_id):
    """
    Асинхронная задача для импорта товаров из файла YAML
    """
    try:
        user = User.objects.get(id=user_id)
        shop, _ = Shop.objects.get_or_create(name=data['shop'], user=user)

        for category in data['categories']:
            category_obj, _ = Category.objects.get_or_create(id=category['id'], defaults={'name': category['name']})
            if category_obj.name != category['name']:
                category_obj.name = category['name']
                category_obj.save()
            category_obj.shops.add(shop)
            category_obj.save()

        ProductInfo.objects.filter(shop=shop).delete()

        for item in data['goods']:
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
            for param_name, param_value in item['parameters'].items():
                parameter, _ = Parameter.objects.get_or_create(name=param_name)
                ProductParameter.objects.create(product_info=product_info, parameter=parameter, value=param_value)

        user = User.objects.get(id=user_id)
        subject = 'Загрузка данных завершена'
        message = 'Ваши данные успешно обновлены.'
        recipient_list = [user.email]
        send_email.delay(subject, message, recipient_list)

    except Exception as e:
        # Обработка ошибок: можно логировать ошибку или уведомить пользователя
        user = User.objects.get(id=user_id)
        subject = 'Ошибка при загрузке данных'
        message = f'Произошла ошибка при обновлении данных: {str(e)}'
        recipient_list = [user.email]
        send_email.delay(subject, message, recipient_list)
        # Дополнительно можно логировать ошибку
        raise e  # Повторно выбрасываем исключение для логирования в Celery
