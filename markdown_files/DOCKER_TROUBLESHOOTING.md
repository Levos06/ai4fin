# Решение проблем с Docker

## Ошибка: "header key contains value with non-printable ASCII characters"

Эта ошибка возникает, если имя директории проекта содержит кириллицу или специальные символы.

### Решение 1: Переименовать директорию (рекомендуется)

```bash
# Переименуйте директорию в имя без кириллицы и специальных символов
cd /Users/levosadchi/Desktop
mv "knowledge_base — копия 4" knowledge_base_copy_4
cd knowledge_base_copy_4
docker-compose up -d
```

### Решение 2: Создать символическую ссылку

```bash
# Создайте символическую ссылку с простым именем
cd /Users/levosadchi/Desktop
ln -s "knowledge_base — копия 4" knowledge_base_docker
cd knowledge_base_docker
docker-compose up -d
```

### Решение 3: Использовать абсолютный путь в docker-compose.yml

Если переименование невозможно, можно указать абсолютный путь:

```yaml
services:
  backend:
    build:
      context: /Users/levosadchi/Desktop/knowledge_base\ —\ копия\ 4
      dockerfile: Dockerfile.backend
```

Но это может не решить проблему полностью, так как Docker все равно будет использовать путь с проблемными символами.

## Рекомендация

**Лучше всего переименовать директорию** в имя без кириллицы и специальных символов, например:
- `knowledge_base_copy_4`
- `financial_agent`
- `kb_docker`

Это решит проблему и предотвратит подобные ошибки в будущем.

