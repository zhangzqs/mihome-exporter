from typing import Optional
import prometheus_client as pc
from config import load_config_from_args
from logger import LoggerConfig, init_logger
from pydantic import BaseModel
import logging
import mihome
import qweather


class Config(BaseModel):
    logger: LoggerConfig
    port: int = 8000
    mihome_config: Optional[mihome.MiHomeConfig] = None
    qweather_config: Optional[qweather.QWeatherConfig] = None


def main():
    cfg = load_config_from_args(Config)
    init_logger(cfg.logger, logging.getLogger())
    pc.start_http_server(port=cfg.port)
    logging.info(f"Starting MiHome Exporter on port {cfg.port}")

    threads = []
    if cfg.mihome_config:
        mihome.init(cfg.mihome_config)
        threads.append(mihome.start_collect())
    else:
        logging.warning(
            "MiHome configuration is not provided, skipping MiHome collector initialization.")
    if cfg.qweather_config:
        qweather.init(cfg.qweather_config)
        threads.append(qweather.start_collect())
    else:
        logging.warning(
            "QWeather configuration is not provided, skipping QWeather collector initialization.")
    if threads:
        for t in threads:
            t.join()
    else:
        logging.warning(
            "No collectors initialized, exiting. Please provide valid configurations.")


if __name__ == '__main__':
    main()
