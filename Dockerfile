FROM python:3.11-slim

# Install OpenJDK for PySpark local execution
RUN apt-get update && apt-get install -y --no-install-recommends \
    default-jdk-headless \
    procps \
    curl \
    && rm -rf /var/lib/apt/lists/*

ENV JAVA_HOME=/usr/lib/jvm/default-java

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000 8501
