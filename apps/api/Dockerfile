FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
COPY pyproject.toml ./
COPY eztracker ./eztracker
# Chromium + its system libraries for the headless scraper
RUN pip install --no-cache-dir . && playwright install --with-deps chromium \
    && useradd -m app && chown -R app /ms-playwright
USER app
EXPOSE 8000
CMD ["sh", "-c", "uvicorn eztracker.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers"]
