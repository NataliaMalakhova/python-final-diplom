# Пример API-сервиса для магазина

[Исходная документация по запросам в PostMan](https://documenter.getpostman.com/view/5037826/SVfJUrSc) 

[Список запросов в PostMan с примерами ответов](https://documenter.getpostman.com/view/15814958/2sAYBRGuGi)


## **Инструкция по сборке docker-образа**
  
1. Клонирование репозитория:
   ```bash
   git clone https://github.com/NataliaMalakhova/python-final-diplom
   cd python-final-diplom/reference/netology_pd_diplom/
   ```
2. Далее необходимо создать `.env` файл, содержащий переменные: 
   ```bash
   EMAIL_HOST=smtp.mail.ru
   EMAIL_HOST_USER=логин почтового ящика
   EMAIL_HOST_PASSWORD=пароль для внешних приложений
   EMAIL_PORT=465
   EMAIL_USE_SSL=True
   ```
   Также в `.env` файл можно занести переменные `SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `CELERY_BROKER_URL` и `DATABASE_URL`.
4. Команда, собирающая Docker-образ согласно заданным настройкам:
   ```bash
   docker-compose build
   ```
   Команда, запускающая все сервисы, определенные в `docker-compose.yml` в фоновом режиме:
   ```bash
   docker-compose up -d
   ```
5. После запуска контейнеров необходимо выполнить миграции базы данных:
   ```bash
   docker-compose exec web python manage.py migrate
   ```
   Собрать статические файлы:
   ```bash
   docker-compose exec web python manage.py collectstatic --noinput
   ```
   И создать суперпользователя для доступа к админ-панели:
   ```bash
   docker-compose exec web python manage.py createsuperuser
   ```
    
## **Доступ к приложению**
   + После запуска приложение будет доступно по адресу: `http://localhost:8000`
   + Интерфейс Flower для мониторинга задач Celery доступен по адресу: `http://localhost:5555`

   Для отдельной сборки Docker-образа приложения необходимо выполнить команду:
   ```bash
   docker build -t your_image_name .
   ```,
   где `your_image_name` заменяется на желаемое название Docker-образа.
