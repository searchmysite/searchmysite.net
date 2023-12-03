import logging
import os
from abc import ABC

import torch
from llama_cpp import Llama

from ts.torch_handler.base_handler import BaseHandler

logger = logging.getLogger(__name__)


class LlamaCppHandler(BaseHandler, ABC):
    def __init__(self):
        super(LlamaCppHandler, self).__init__()
        self.initialized = False
        logger.info("Init done")

    def initialize(self, context):
        """In this initialize function, the HF large model is loaded and
        partitioned using DeepSpeed.
        Args:
            ctx (context): It is a JSON Object containing information
            pertaining to the model artifacts parameters.
        """
        logger.info("Start initialize")
        self.manifest = context.manifest
        logger.info('manifest: {}'.format(self.manifest))
        properties = context.system_properties
        logger.info('properties: {}'.format(properties))

        model_name = context.model_yaml_config["handler"]["model_name"]
        #model_path = context.model_yaml_config["handler"]["model_path"]
        model_dir = properties.get("model_dir")
        serialized_file = self.manifest['model']['serializedFile']
        model_path = os.path.join(model_dir, serialized_file)
        if not os.path.exists(model_path):
             raise RuntimeError("Missing model")
        #    model_path = os.environ["LLAMA2_Q4_MODEL"]

        seed = int(context.model_yaml_config["handler"]["manual_seed"])
        torch.manual_seed(seed)

        self.model = Llama(model_path=model_path)

    def preprocess(self, data):
        for row in data:
            item = row.get("body")
            return item

    def inference(self, data):
        result = self.model.create_completion(
            data["prompt"],
            max_tokens=data["max_tokens"],
            top_p=data["top_p"],
            temperature=data["temperature"],
            stop=["Q:", "\n"],
            echo=True,
        )
        tokens = self.model.tokenize(bytes(data["prompt"], "utf-8"))
        return result

    def postprocess(self, output):
        logger.info(output)
        result = []
        result.append(output["choices"][0]["text"])
        return result
