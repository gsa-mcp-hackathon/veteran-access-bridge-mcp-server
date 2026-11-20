FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir .
ENV VAB_DEMO_HOST=0.0.0.0
ENV PORT=8080
EXPOSE 8080
CMD ["veteran-access-demo"]
