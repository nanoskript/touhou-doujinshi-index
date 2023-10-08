pdm run \
  gunicorn -k gevent \
  --certfile cert.pem \
  --keyfile key.pem \
  --bind 0.0.0.0:443 \
  app:app
