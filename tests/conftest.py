import os


os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("DATABASE_URL", "postgresql://localhost/presek_test")
os.environ.setdefault("GOOGLE_API_KEY", "test-google-api-key")
