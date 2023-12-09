# 2 stage Dockerfile
# Stage 1 is the builder image, which builds the model archive, and is not persisted
# Stage 2 is the production image, which copies the model archive in and serves it, and is persisted


# Builder image
#FROM pytorch/torchserve AS builder
# Start arm64 workaround 1
# pytorch/torchserve doesn't currently support arm64 as per https://github.com/pytorch/serve/issues/2555
# Until arm64 is available for pytorch/torchserve, use the lines below instead of the one above
# Note that the builder image is lighterweight than the production image because it just runs the huggingface CLI and the model archiver 
FROM alpine:3.18 AS builder
RUN apk add --no-cache python3 py3-pip python3-dev gcc build-base linux-headers
RUN pip install torchserve torch-model-archiver
# End arm64 workaround 1

WORKDIR /usr/app

RUN pip install huggingface_hub

#RUN huggingface-cli download TheBloke/Llama-2-7b-Chat-GGUF llama-2-7b-chat.Q3_K_S.gguf config.json --local-dir . --local-dir-use-symlinks False
RUN huggingface-cli download TheBloke/rocket-3B-GGUF rocket-3b.Q4_K_M.gguf config.json --local-dir . --local-dir-use-symlinks False

ADD llama_cpp_handler.py .
ADD model-config.yaml .

RUN mkdir model_store
#RUN torch-model-archiver --model-name llamacpp --version 1.0 --serialized-file llama-2-7b-chat.Q3_K_S.gguf --handler llama_cpp_handler.py --extra-files config.json --config-file model-config.yaml --export-path model_store
RUN torch-model-archiver --model-name rocket-3b --version 1.0 --serialized-file rocket-3b.Q4_K_M.gguf --handler llama_cpp_handler.py --extra-files config.json --config-file model-config.yaml --export-path model_store


# Production image
#FROM pytorch/torchserve
# Start arm64 workaround 2
# As per above, temporarily using the lines below in place of the one above
# Note that this requires the full torchserve rather than just the huggingface CLI and model archiver 
FROM ubuntu:22.04
RUN apt-get update && apt-get install -y python3 python3-pip openjdk-17-jdk git
RUN git clone https://github.com/pytorch/serve.git && cd /serve ; python3 ./ts_scripts/install_dependencies.py ; cd /
RUN pip install torchserve torch-model-archiver torch-workflow-archiver
ADD config.properties config.properties
RUN ln -s /usr/bin/python3 /usr/bin/python
# End arm64 workaround 2

RUN pip install llama-cpp-python

COPY --from=builder /usr/app/model_store model_store

#CMD ["torchserve", "--start", "--model-store", "model_store", "--models", "llama2=llamacpp.mar", "--ncs"]
# Start arm64 workaround 3
# As per above, temporarily using the lines below in place of the one above
# The self-built torchserve container needs the config.properties to specify inference_address 
# and the sleep infinity to stop the container exiting before torchserve starts
#CMD torchserve --start --model-store model_store --models llama2=llamacpp.mar --ncs --ts-config /config.properties && sleep infinity
CMD torchserve --start --model-store model_store --models rocket-3b=rocket-3b.mar --ncs --ts-config /config.properties && sleep infinity
# End arm64 workaround 3
