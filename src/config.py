from typing import Optional, Type, TypeVar
import yaml
from pydantic import BaseModel
import argparse

from logger import LoggerConfig

# 定义一个泛型类型 T，限制为 BaseModel 或其子类
T = TypeVar("T", bound=BaseModel)


def load_config_from_args(model: Type[T]) -> T:
    parser = argparse.ArgumentParser(
        description="Load configuration from a YAML file.")
    parser.add_argument(
        "--config", type=str, required=True, help="Path to the YAML configuration file"
    )
    args = parser.parse_args()

    # 加载配置文件
    with open(args.config, "r", encoding="utf-8") as f:
        config_data = yaml.safe_load(f)
    return model(**config_data)
