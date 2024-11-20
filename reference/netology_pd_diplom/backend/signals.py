from typing import Type

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db.models.signals import post_save
from django.dispatch import receiver, Signal
from django_rest_passwordreset.signals import reset_password_token_created

from backend.models import ConfirmEmailToken, User
from .tasks import send_email

new_user_registered = Signal()

new_order = Signal()


@receiver(reset_password_token_created)
def password_reset_token_created(sender, instance, reset_password_token, **kwargs):
    """
    Отправляем письмо с токеном для сброса пароля
    When a token is created, an e-mail needs to be sent to the user
    :param sender: View Class that sent the signal
    :param instance: View Instance that sent the signal
    :param reset_password_token: Token Model Object
    :param kwargs:
    :return:
    """
    # send an e-mail to the user
    subject = f"Password Reset Token for {reset_password_token.user}"
    message = reset_password_token.key
    recipient_list = [reset_password_token.user.email]

    # Запускаем задачу отправки письма
    send_email.delay(subject, message, recipient_list)


@receiver(post_save, sender=User)
def new_user_registered_signal(sender: Type[User], instance: User, created: bool, **kwargs):
    """
    Отправляем письмо с подтверждением почты
    """
    if created and not instance.is_active:
        # send an e-mail to the user
        token, _ = ConfirmEmailToken.objects.get_or_create(user_id=instance.pk)

        subject = f"Password Reset Token for {instance.email}"
        message = token.key + 'Для подтверждения регистрации перейдите по ссылке'
        from_email = settings.EMAIL_HOST_USER
        recipient_list = [instance.email]

        # Запускаем задачу отправки письма
        send_email.delay(subject, message, recipient_list)


@receiver(new_order)
def new_order_signal(user_id, **kwargs):
    """
    Отправляем письмо при изменении статуса заказа
    """
    # send an e-mail to the user
    user = User.objects.get(id=user_id)
    subject = "Обновление статуса заказа"
    message = "Заказ сформирован"
    recipient_list = [user.email]

    # Запускаем задачу отправки письма
    send_email.delay(subject, message, recipient_list)
