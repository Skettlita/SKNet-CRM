FROM python:3.13-alpine
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN apk add --no-cache wireguard-tools
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY provisioner.py rest.py ./
COPY providers ./providers
CMD ["python", "-m", "provisioner"]
