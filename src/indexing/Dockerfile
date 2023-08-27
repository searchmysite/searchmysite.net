FROM python:3.11.2

WORKDIR /usr/src/app

COPY requirements.txt ./

# Install rust compiler, and make available in PATH, for safetensors (required by sentence-transformers) on aarch64
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH "$PATH:/root/.cargo/bin"

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

