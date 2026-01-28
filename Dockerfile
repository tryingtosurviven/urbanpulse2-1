FROM python:3.11-slim

WORKDIR /app

# Install deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY . .

# Code Engine listens on 8080
ENV PORT=8080

EXPOSE 8080

# Run with gunicorn (production)
CMD ["gunicorn", "-b", "0.0.0.0:8080", "app:app"]
