from django.test import TestCase
from django.urls import reverse
from django.core import mail
from django.core.cache import cache
from django.contrib.auth import get_user_model
from django.dispatch import Signal
# Импортируем сигналы и ресиверы
from django_rest_passwordreset.signals import reset_password_token_created

from backend.models import Order
from backend.signals import new_order

User = get_user_model()


class UserRegistrationTestCase(TestCase):
    def setUp(self):
        # Явный сброс mail.outbox
        mail.outbox = []

        self.registration_url = reverse('user-register')
        self.confirm_email_url = reverse('confirm-email', args=['{token}'])
        self.user_data = {
            "email": "testuser@example.com",
            "first_name": "Иван",
            "last_name": "Иванов",
            "password": "testpassword123",
            "password_confirm": "testpassword123"
        }

    def test_user_registration_sends_email(self):
        """
        Тестирует, что при регистрации пользователя отправляется письмо с подтверждением.
        """
        response = self.client.post(self.registration_url, data=self.user_data)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(mail.outbox), 1)  # Проверяем, что отправлено одно письмо

        # Проверяем содержание письма
        email = mail.outbox[0]
        self.assertEqual('Password Reset Token for', email.subject)
        self.assertIn('Для подтверждения регистрации перейдите по ссылке', email.body)
        self.assertIn(self.user_data['email'], email.to)

        # Проверяем, что пользователь создан, но не активен
        user = User.objects.get(email=self.user_data['email'])
        self.assertFalse(user.is_active)

    def test_invalid_token(self):
        """
        Тестирует поведение при неверном токене подтверждения.
        """
        invalid_token = '12345678-1234-5678-1234-567812345678'
        confirm_url = reverse('confirm-email', args=[invalid_token])
        response = self.client.get(confirm_url)
        self.assertEqual(response.status_code, 400)
        # self.assertIn('Неверный или просроченный токен.', response.data['error'])


class PasswordResetTokenCreatedTestCase(TestCase):
    def setUp(self):
        mail.outbox = []

        self.user = User.objects.create_user(
            email='testuser@example.com',
            password='testpassword123'
        )
        self.reset_password_url = reverse('password_reset')

    def test_password_reset_token_created_sends_email(self):
        """
        Тестирует, что при создании токена для сброса пароля отправляется письмо.
        """
        # Отправляем запрос на сброс пароля
        response = self.client.post(self.reset_password_url, data={'email': self.user.email})
        self.assertEqual(response.status_code, 200)

        # Проверяем, что отправлено одно письмо
        self.assertEqual(len(mail.outbox), 1)

        email = mail.outbox[0]
        self.assertIn('Password Reset Token for', email.subject)
        self.assertIn(self.user.email, email.to)


class NewOrderSignalTestCase(TestCase):
    def setUp(self):
        mail.outbox = []

        self.user = User.objects.create_user(
            email='customer@example.com',
            password='password123'
        )
        # Создаем заказ для пользователя
        self.order = Order.objects.create(
            user=self.user,
            state='new'  # или другой статус, соответствующий вашей модели
        )

    def test_new_order_signal_sends_email(self):
        """
        Тестирует, что при срабатывании сигнала new_order отправляется письмо пользователю.
        """
        # Отправляем сигнал new_order
        new_order.send(sender=self.__class__, user_id=self.user.id)

        # Проверяем, что отправлено одно письмо
        self.assertEqual(len(mail.outbox), 1)

        email = mail.outbox[0]
        self.assertEqual(email.subject, 'Обновление статуса заказа')
        self.assertIn('Заказ сформирован', email.body)
        self.assertIn(self.user.email, email.to)


class ThrottlingTestCase(TestCase):
    def setUp(self):
        # Очистка кеша перед каждым тестом
        cache.clear()

    def test_request_limit(self):
        response = self.client.get('/user/login/')
        self.assertEqual(response.status_code, 200)

        # Превышение лимита
        for _ in range(10):
            response = self.client.get('/user/login/')
        self.assertEqual(response.status_code, 429)

    def tearDown(self):
        # Очистка кеша после каждого теста
        cache.clear()
