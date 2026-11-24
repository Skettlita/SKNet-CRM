FROM python:3.13-alpine
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN apk add --no-cache wireguard-tools iproute2 iputils iptables && mkdir /state
COPY agent.py rest.py ./
CMD ["python", "-m", "agent"]
