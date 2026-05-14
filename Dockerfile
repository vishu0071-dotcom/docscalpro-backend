FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (LibreOffice for DOCX/XLSX→PDF)
RUN apt-get update && apt-get install -y \
    libreoffice \
    libgl1-mesa-glx \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create temp directories
RUN mkdir -p /tmp/docscalpro/uploads /tmp/docscalpro/outputs

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
