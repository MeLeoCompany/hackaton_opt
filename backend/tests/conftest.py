import os

# модули приложения читают настройки при импорте; этим тестам БД не нужна, но адрес должен быть задан
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
