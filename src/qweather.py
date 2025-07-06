from typing import Optional
import httpx
from pydantic import BaseModel
import time
from threading import Thread
import prometheus_client as pc
from datetime import datetime, timezone
import logging


class LocationConfig(BaseModel):
    name: str
    lon: float
    lat: float


class QWeatherConfig(BaseModel):
    api_key: str
    api_host: str
    interval_seconds: int = 1200
    locations: list[LocationConfig] = []


cfg: Optional[QWeatherConfig] = None

NAMESPACE = 'qweather'

obs_time_deplay_seconds = pc.Gauge(
    namespace=NAMESPACE,
    name='obs_time_deplay_seconds',
    documentation='观测延时',
    labelnames=['location'],
)

temperature = pc.Gauge(
    namespace=NAMESPACE,
    name='temperature',
    documentation='当前温度',
    labelnames=['location'],
)

humidity = pc.Gauge(
    namespace=NAMESPACE,
    name='humidity',
    documentation='当前湿度',
    labelnames=['location'],
)

feels_like = pc.Gauge(
    namespace=NAMESPACE,
    name='feels_like',
    documentation='体感温度',
    labelnames=['location'],
)

wind_360 = pc.Gauge(
    namespace=NAMESPACE,
    name='wind_360',
    documentation='风向（360度）',
    labelnames=['location'],
)

wind_scale = pc.Gauge(
    namespace=NAMESPACE,
    name='wind_scale',
    documentation='风力等级',
    labelnames=['location'],
)

wind_speed = pc.Gauge(
    namespace=NAMESPACE,
    name='wind_speed',
    documentation='风速',
    labelnames=['location'],
)

pressure = pc.Gauge(
    namespace=NAMESPACE,
    name='pressure',
    documentation='气压',
    labelnames=['location'],
)


def init(_cfg: QWeatherConfig):
    global cfg
    cfg = _cfg
    print(f'初始化配置: {cfg}')
    if not cfg.api_key or not cfg.api_host:
        raise ValueError('请提供有效的 QWeather API Key 和 Host')
    print('QWeather 配置初始化完成')


def collect_qweather(location_cfg: LocationConfig):
    url = httpx.URL(f'{cfg.api_host}/v7/grid-weather/now')
    resp = httpx.get(
        url=url,
        params={
            "location": f"{format(location_cfg.lon, '.2f')},{format(location_cfg.lat, '.2f')}",
        },
        headers={
            'X-QW-Api-Key': cfg.api_key,
        })
    if resp.status_code != 200:
        raise httpx.HTTPStatusError(
            f'请求失败: {resp.status_code} - {resp.text}', request=resp.request, response=resp)
    resp_body = resp.json()
    logging.info(f'获取 {location_cfg.name} 的天气数据: {resp_body}')
    now_weather = resp_body['now']
    obs_time = datetime.fromisoformat(
        now_weather['obsTime']).astimezone(tz=timezone.utc)
    now_time = datetime.now(tz=timezone.utc)
    logging.info(f'观测时间: {obs_time}, 当前时间: {now_time}')
    obs_time_deplay_seconds.labels(location=location_cfg.name).set(
        value=(now_time - obs_time).total_seconds(),
    )
    temperature.labels(location=location_cfg.name).set(
        value=float(now_weather['temp']),
    )
    humidity.labels(location=location_cfg.name).set(
        value=float(now_weather['humidity']),
    )
    feels_like.labels(location=location_cfg.name).set(
        value=float(now_weather['feelsLike']),
    )
    wind_360.labels(location=location_cfg.name).set(
        value=float(now_weather['wind360']),
    )
    wind_scale.labels(location=location_cfg.name).set(
        value=float(now_weather['windScale']),
    )
    wind_speed.labels(location=location_cfg.name).set(
        value=float(now_weather['windSpeed']),
    )
    pressure.labels(location=location_cfg.name).set(
        value=float(now_weather['pressure']),
    )


def start_collect():
    if cfg is None:
        raise ValueError('请先调用 init() 初始化配置')

    def run():
        while True:
            for location in cfg.locations:
                collect_qweather(location)
            time.sleep(cfg.interval_seconds)

    t = Thread(target=run, name='QWeatherCollectorThread', daemon=True)
    t.start()
    return t
