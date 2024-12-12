from rest_framework.views import exception_handler


def custom_throttle_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is not None and response.status_code == 429:
        response.data = {
            'error': 'Вы превысили лимит запросов. Попробуйте позже.',
            'detail': response.data['detail']
        }

    return response
