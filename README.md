Пожалуйста, сначала откройте [папку](https://drive.google.com/drive/folders/1EVEj87VGWpaiysrNPw6xC-hlSFIQoUvt?usp=drive_link) и прочитайте файл [Запуск](https://docs.google.com/document/d/1ad3xyH887CwfajvucLzJnH02Dbz85wLMOzS3M6HPsz0/edit?usp=drive_link)

# Быстрый запуск Docker

Запишите в .env ключи для tavily (https://www.tavily.com/) и для openrouter.
Скачайте папку [vector_db](https://drive.google.com/file/d/1K545rsCKLqnZiQFdraH04CZ6W1Nn9Pa5/view?usp=drive_link), если запускаете через клонирование репозитория.

Запустите проект из корневой директории:

```bash
docker compose up -d
```

Когда контейнеры будут готовы, откройте `http://localhost` в браузере.

Чтобы остановить и очистить:

```bash
docker compose down
```

Подробности ищите в документации внутри `markdown_files/`.

Важно:
Если Вы клонировали репозиторий, для полной функциональности Вам надо скачать векторную базу данных (по ссылке)[https://drive.google.com/file/d/1WZaA2oz3ornM2zdnjcSAkLMUXexHQBrz/view?usp=drive_link]
