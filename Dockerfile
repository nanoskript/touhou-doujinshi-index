FROM python:3.10-slim-bookworm

RUN apt-get update && apt-get install -y g++

RUN pip install --no-cache-dir pdm
ADD ./pyproject.toml ./pdm.lock ./
RUN pdm sync && pdm cache clear

ADD ./start_server.sh ./
ADD ./start_update.sh ./

ADD ./static ./static
ADD ./scripts ./scripts
ADD ./templates ./templates
ADD ./app.py ./

CMD ["pdm", "run", "gunicorn", \
	"--bind", "0.0.0.0:$PORT", \
	"-k", "gevent", "app:app"]
