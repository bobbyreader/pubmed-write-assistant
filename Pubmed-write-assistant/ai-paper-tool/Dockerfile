FROM python:3.9-slim

WORKDIR /app

# Install system dependencies for reportlab chinese fonts
RUN apt-get update && apt-get install -y \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose Streamlit port
EXPOSE 8501

# Run Streamlit
CMD ["streamlit", "run", "app.py", "--server.headless", "true", "--server.port", "8501", "--server.address", "127.0.0.1"]