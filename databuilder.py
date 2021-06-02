# coding:utf-8
"""
Filename : databuilder.py
Role : TO-DO: Change role of databuilder.py

@author : Sunwaee
"""

import json
import logging
import os
from dataclasses import (
    dataclass,
    field
)
from typing import Optional

import sentencepiece
import pandas as pd
import torch
from nlp import Dataset
from transformers import (
    MT5Tokenizer,
    HfArgumentParser
)

from utils import dict_to_json

logger = logging.getLogger(__name__)

DEFAULT_ARGS = dict(
    source_max_length=512,  # Maximum length of source text
    target_max_length=30,  # Maximum length of target text
    highlight_token='<hl>',  # Highlight token
    separation_token='<sep>',  # Separation token
    tokenizer_name_or_path='google/mt5-small',  # Tokenizer path
    global_output_dir='model',  # Tokenizer save path
    train_csv_path='data/train.tsv',  # Training file path
    valid_csv_path='data/valid.tsv',  # Validation file path
    source_column='source_text',  # Source column
    target_column='target_text',  # Target column
    train_file_path='data/train.pt',  # Training data save path
    valid_file_path='data/valid.pt',  # Validation data save path
    config_path='model/params.json'  # Save path of databuilder config
)


@dataclass
class DatabuilderArguments:
    """
    Databuilder arguments used to build training and evaluation data.
    """

    highlight_token: Optional[str] = field(default=DEFAULT_ARGS['highlight_token'],
                                           metadata={"help": "Highlight token. "})

    separation_token: Optional[str] = field(default=DEFAULT_ARGS['separation_token'],
                                            metadata={"help": "Separation token. "})

    tokenizer_name_or_path: Optional[str] = field(default=DEFAULT_ARGS['tokenizer_name_or_path'],
                                                  metadata={"help": "Path or Hugging Face name of the tokenizer. "})

    global_output_dir: Optional[str] = field(default=DEFAULT_ARGS['global_output_dir'],
                                             metadata={"help": "Destination folder of the tokenizer. "})

    train_csv_path: Optional[str] = field(default=DEFAULT_ARGS['train_csv_path'],
                                          metadata={"help": "Path of the csv file containing training data. "})

    valid_csv_path: Optional[str] = field(default=DEFAULT_ARGS['valid_csv_path'],
                                          metadata={"help": "Path of the csv file containing validation data. "})

    train_file_path: Optional[str] = field(default=DEFAULT_ARGS['train_file_path'],
                                           metadata={"help": "Save path of the training data. "})

    valid_file_path: Optional[str] = field(default=DEFAULT_ARGS['valid_file_path'],
                                           metadata={"help": "Save path of the validation data. "})

    source_column: Optional[str] = field(default=DEFAULT_ARGS['source_column'],
                                         metadata={"help": "Source column. "})

    target_column: Optional[str] = field(default=DEFAULT_ARGS['target_column'],
                                         metadata={"help": "Target column. "})

    config_path: Optional[str] = field(default=DEFAULT_ARGS['config_path'],
                                       metadata={"help": "Save path of databuilder config. "})

    source_max_length: Optional[int] = field(default=DEFAULT_ARGS['source_max_length'],
                                             metadata={"help": "Maximum number of tokens in source. "})

    target_max_length: Optional[int] = field(default=DEFAULT_ARGS['target_max_length'],
                                             metadata={"help": "Maximum number of tokens in target. "})


class Databuilder:
    """
    Data preprocessing and conversion.
    """

    def __init__(self, tokenizer: MT5Tokenizer, args: DatabuilderArguments) -> None:
        """
        Initializes Preprocessor.

        :param tokenizer: MT5 Tokenizer
        :param args: databuilder arguments
        """

        self.tokenizer = tokenizer
        self.source_max_length = args.source_max_length
        self.target_max_length = args.target_max_length
        self.highlight_token = args.highlight_token
        self.separation_token = args.separation_token
        self.source_column = args.source_column
        self.target_column = args.target_column

    def preprocess(self, dataset: Dataset) -> Dataset:
        """
        Preprocess dataset and converts it to features.

        :param dataset: dataset to preprocess
        :return: preprocessed dataset
        """

        dataset = dataset.map(self._add_eos)
        dataset = dataset.map(self._replace_special_tokens)
        dataset = dataset.map(self._to_features, batched=True)

        return dataset

    def _add_eos(self, row: dict) -> dict:
        """
        Adds end of sentence tokens if necessary.

        :param row: a data example
        :return: modified data example
        """

        row[self.source_column] = [
            row[self.source_column] + " </s>",
            row[self.source_column]
        ][row[self.source_column][-4:] == '</s>']

        row[self.target_column] = [
            row[self.target_column] + " </s>",
            row[self.target_column]
        ][row[self.target_column][-4:] == '</s>']

        return row

    def _replace_special_tokens(self, row: dict) -> dict:
        """
        Replaces special tokens.

        :param row: a data example
        :return: modified data example
        """

        row[self.source_column] = row[self.source_column].replace("{hl_token}", self.highlight_token)
        row[self.target_column] = row[self.target_column].replace("{sep_token}", self.separation_token)

        return row

    def _to_features(self, batch: dict) -> dict:
        """
        Converts batches to features.

        :param batch: batch of examples
        :return:
        """

        encoded_source = self.tokenizer.batch_encode_plus(
            batch_text_or_text_pairs=batch[self.source_column],
            max_length=self.source_max_length,
            padding='max_length',
            pad_to_max_length=True,
            truncation=True,
        )

        encoded_target = self.tokenizer.batch_encode_plus(
            batch_text_or_text_pairs=batch[self.target_column],
            max_length=self.target_max_length,
            padding='max_length',
            pad_to_max_length=True,
            truncation=True,
        )

        encodings = {
            'source_ids': encoded_source['input_ids'],
            'target_ids': encoded_target['input_ids'],
            'attention_mask': encoded_source['attention_mask'],
        }

        return encodings


def main(from_json: bool = True, filename: str = DEFAULT_ARGS['config_path']) -> None:
    """
    Building training and validation data.

    :param from_json: whether to import config from a json or not
    :param filename: name of the json file
    :return: None
    """

    # Logging the session informations
    logging.basicConfig(
        format="%(asctime)s - %(levelname)s - %(name)s -   %(message)s",
        datefmt="%m/%d/%Y %H:%M:%S",
        level=logging.INFO
    )

    # Parsing arguments for line command and json file for script
    parser = HfArgumentParser((DatabuilderArguments,))
    db_args = parser.parse_json_file(json_file=filename)[0] if from_json else parser.parse_args_into_dataclasses()[0]

    # Showing config
    with open(db_args.config_path, "r") as config:
        config = json.load(config)

    logger.info("This config is being built: ")
    for key in config:
        logger.info("     " + key + "=" + str(config[key]))

    # Loading dataframes
    train_df = pd.read_csv(filepath_or_buffer=db_args.train_csv_path, sep='\t').astype(str)
    valid_df = pd.read_csv(filepath_or_buffer=db_args.valid_csv_path, sep='\t').astype(str)

    # Assertions to prevent wasted time and annoying bugs coming from sensitive arguments
    assert all([db_args.source_column in train_df.columns,
                db_args.target_column in train_df.columns]), \
        f"{db_args.source_column} or {db_args.target_column} column missing in {db_args.train_csv_path}."

    assert all([db_args.source_column in valid_df.columns,
                db_args.target_column in valid_df.columns]), \
        f"{db_args.source_column} or {db_args.target_column} column missing in {db_args.valid_csv_path}."

    assert all([db_args.train_file_path[-3:] == '.pt',
                db_args.valid_file_path[-3:] == '.pt']), \
        "train_file_path and valid_file_path must be .pt files."

    # Building Datasets from dataframes
    train_dataset = Dataset.from_pandas(train_df)
    valid_dataset = Dataset.from_pandas(train_df)

    # Loading tokenizer and adding special tokens
    tokenizer = MT5Tokenizer.from_pretrained(db_args.tokenizer_name_or_path)
    tokenizer.add_tokens([db_args.highlight_token, db_args.separation_token])

    # Initializing preprocessor
    preprocessor = Databuilder(
        tokenizer=tokenizer,
        args=db_args
    )

    # Preprocessing both datasets
    train_dataset = preprocessor.preprocess(
        dataset=train_dataset
    )
    valid_dataset = preprocessor.preprocess(
        dataset=valid_dataset
    )

    # Changing datasets format
    columns = ["source_ids", "target_ids", "attention_mask"]
    train_dataset.set_format(type='torch', columns=columns)
    valid_dataset.set_format(type='torch', columns=columns)

    # Saving datasets
    torch.save(train_dataset, db_args.train_file_path)
    logger.info(f"Train dataset saved at {db_args.train_file_path}. ")

    torch.save(valid_dataset, db_args.valid_file_path)
    logger.info(f"Validation dataset saved at {db_args.valid_file_path}. ")

    # Saving tokenizer
    if not os.path.exists(db_args.global_output_dir):
        os.mkdir(db_args.global_output_dir)
    tokenizer.save_pretrained(db_args.global_output_dir)
    logger.info(f"Tokenizer saved at {db_args.global_output_dir}. ")


def run(args_dict: dict = {}) -> None:
    args_dict = {**DEFAULT_ARGS, **args_dict}
    file = dict_to_json(args_dict=args_dict, filename=args_dict['config_path'])
    main(filename=file)


if __name__ == "__main__":
    main(from_json=False)
