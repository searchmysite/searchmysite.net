FROM python:3.9.0-buster

WORKDIR /usr/src/app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# docker-compose.yml (env=dev) and docker-compose.test.yml (env=test) have the following:
#    volumes:
#      - "./indexer:/usr/src/app/:ro"
# For prod we need to copy the source files in to that location
COPY ./ /tmp/indexer/
ARG env
RUN if [ "$env" = "prod" ] ; then cp -r /tmp/indexer/* /usr/src/app/ ; fi

ENV ENVIRONMENT $env
CMD [ "sh", "-c", "/usr/src/app/indexer/run.sh ${ENVIRONMENT}" ]

