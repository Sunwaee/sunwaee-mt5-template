# coding:utf-8
"""
Filename : train.py
Role : model training

@author : Sunwaee
"""

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Optional

import torch
from transformers import (
    AutoModelForSeq2SeqLM,
    MT5Tokenizer,
    HfArgumentParser,
    TrainingArguments,
    set_seed,
)

from data_collector import DataCollector
from databuilder import DatabuilderArguments
from trainer import Trainer
from utils import (
    dict_to_json,
)

# Initializing logger
logger = logging.getLogger(__name__)

# Generating default train config
DEFAULT_ARGS = dict(
    model_name_or_path="",
    label_smoothing_rate=0.0,
    train_config_path="model/params.json",
    wandb_project_name='mt5-project',
    overwrite_output_dir=True
)


@dataclass
class ModelArguments:
    """
    Model arguments.
    """

    # Model name from hugging face or path
    model_name_or_path: Optional[str] = field(default=DEFAULT_ARGS['model_name_or_path'],
                                              metadata={"help": "Path to pretrained model or Hugging Face model. "})

    # Label smoothing rate
    label_smoothing_rate: Optional[float] = field(default=DEFAULT_ARGS['label_smoothing_rate'],
                                                  metadata={"help": "Label smoothing rate. "})

    # Wandb project name for training
    wandb_project_name: Optional[str] = field(default=DEFAULT_ARGS['wandb_project_name'],
                                              metadata={"help": "Name of the wandb project. "})

    # Path to databuilder params
    train_config_path: Optional[str] = field(default=DEFAULT_ARGS['train_config_path'],
                                             metadata={"help": "Model configuration output path "})


def main(from_json: bool = True, filename: str = DEFAULT_ARGS['train_config_path']) -> None:
    """
    Start training.

    :param from_json: whether to import config from a json or not
    :param filename: name of the json file
    """

    # Parsing arguments
    parser = HfArgumentParser((ModelArguments, DatabuilderArguments, TrainingArguments))
    model_args, databuilder_args, training_args = parser.parse_json_file(
        json_file=filename) if from_json else parser.parse_args_into_dataclasses()

    # Checking if output folder is empty
    if (os.path.exists(training_args.output_dir)
            and os.listdir(training_args.output_dir)
            and training_args.do_train
            and not training_args.overwrite_output_dir):
        raise ValueError(f"Output directory ({training_args.output_dir}) already exists and is not empty. "
                         f"Use --overwrite_output_dir to overcome. ")

    # Logging the session informations
    logging.basicConfig(
        format="%(asctime)s - %(levelname)s - %(name)s -   %(message)s",
        datefmt="%m/%d/%Y %H:%M:%S",
        level=logging.INFO if training_args.local_rank in [-1, 0] else logging.WARN,
    )
    logger.warning(
        "Process rank: %s, device: %s, n_gpu: %s, distributed training: %s, 16-bits training: %s",
        training_args.local_rank,
        training_args.device,
        training_args.n_gpu,
        bool(training_args.local_rank != -1),
        training_args.fp16,
    )
    logger.info("Training/evaluation parameters %s", training_args)

    # Setting seed
    set_seed(training_args.seed)

    # Setting wandb project name
    os.environ["WANDB_PROJECT"] = model_args.wandb_project_name

    # Getting model name
    model_name = [
        lambda: databuilder_args.tokenizer_name_or_path,
        lambda: model_args.model_name_or_path
    ][model_args.model_name_or_path != ""]()

    # Loading pretrained model and tokenizer
    tokenizer = MT5Tokenizer.from_pretrained(databuilder_args.global_output_dir)
    model = AutoModelForSeq2SeqLM.from_pretrained(model_name)

    # Resizing embedding
    model.resize_token_embeddings(len(tokenizer))

    # Loading datasets
    logger.info('Loading datasets...')

    train_dataset = torch.load(databuilder_args.train_file_path) if training_args.do_train else None
    logger.info(f'{databuilder_args.train_file_path} has been loaded. ')
    valid_dataset = torch.load(databuilder_args.valid_file_path) if training_args.do_eval else None
    logger.info(f'{databuilder_args.valid_file_path} has been loaded. ')

    # Initialize DataCollector
    data_collector = DataCollector(
        tokenizer=tokenizer,
        mode="training",
        using_tpu=training_args.tpu_num_cores is not None)

    # Initialize our Trainer
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=valid_dataset,
        data_collator=data_collector,
        label_smoothing=model_args.label_smoothing_rate
    )

    # Disabling wandb logs that are not WARNINGS
    logging.getLogger('wandb.run_manager').setLevel(logging.WARNING)

    # Training
    if training_args.do_train:
        trainer.train()

        # Saving model
        trainer.save_model(training_args.output_dir)

        # Saving tokenizer
        tokenizer.save_pretrained(training_args.output_dir)

    # Evaluation
    results = {}
    if training_args.do_eval and training_args.local_rank in [-1, 0]:
        logger.info("*** Evaluate ***")

        # Evaluating
        eval_output = trainer.evaluate()

        # Saving evaluation result
        output_eval_file = os.path.join(training_args.output_dir, "eval_results.txt")
        with open(output_eval_file, "w") as writer:
            logger.info("***** Eval results *****")
            for key in sorted(eval_output.keys()):
                logger.info("  %s = %s", key, str(eval_output[key]))
                writer.write("%s = %s\n" % (key, str(eval_output[key])))

        results.update(eval_output)


def run(args_dict: dict = {}, databuilder_config_path: str = db_config['databuilder_config_path']) -> None:
    """
    Runs training.

    :param args_dict: training arguments dictionary
    :param databuilder_config_path: path to databuilder config
    """

    # Asserting databuilder config path exists
    assert os.path.isfile(databuilder_config_path), \
        f"Invalid filename for {databuilder_config_path}, file doesn't exist. "

    # Opening databuilder config path and merging it with train dict
    with open(databuilder_config_path, "r") as dbcfg:
        args_dict = {**json.load(fp=dbcfg), **DEFAULT_ARGS, **args_dict}

    # Sending train dict to .json
    file = dict_to_json(args_dict=args_dict, filename=args_dict['train_config_path'])

    # Starting training
    main(filename=file)


if __name__ == "__main__":
    main(from_json=False)
