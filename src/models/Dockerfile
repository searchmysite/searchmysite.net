# 2 stage Dockerfile
# Stage 1 builds the model archive 
# Stage 2 copies the model archive in and serves it


# Builder image
FROM pytorch/torchserve AS builder

WORKDIR /usr/app

RUN pip install huggingface_hub

RUN huggingface-cli download TheBloke/Llama-2-7b-Chat-GGUF llama-2-7b-chat.Q3_K_S.gguf config.json --local-dir . --local-dir-use-symlinks False

ADD llama_cpp_handler.py .
ADD model-config.yaml .
#ADD config.properties .

RUN mkdir model_store
RUN torch-model-archiver --model-name llamacpp --version 1.0 --serialized-file llama-2-7b-chat.Q3_K_S.gguf --handler llama_cpp_handler.py --extra-files config.json --config-file model-config.yaml --export-path model_store


# Production image
FROM pytorch/torchserve

RUN pip install llama-cpp-python

COPY --from=builder /usr/app/model_store model_store
#COPY --from=builder /usr/app/config.properties config.properties

#CMD ["torchserve", "--start", "--model-store", "model_store", "--models", "llama2=llamacpp.mar", "--ncs", "--ts-config", "/config.properties"]
CMD ["torchserve", "--start", "--model-store", "model_store", "--models", "llama2=llamacpp.mar", "--ncs"]
