import json
import os
import sys
from mijiaAPI import mijiaLogin, mijiaAPI
from typing import Any, Callable, Optional
import prometheus_client as pc
import time
from config import load_config_from_args
from logger import LoggerConfig, init_logger
from pydantic import BaseModel
import logging

collectors: dict[str, Callable[[str], None]] = {}


def register_collector(**metadata):
    def decorator(func):
        for key, value in metadata.items():
            if not hasattr(func, key):
                collectors[value] = func
            else:
                logging.warning(
                    f'函数 {func.__name__} 已经有属性 {key}，将覆盖原有值')
            setattr(func, key, value)
        return func
    return decorator


class DeviceConfig(BaseModel):
    name: str


class Config(BaseModel):
    logger: LoggerConfig
    port: int = 8000
    auth_file: str = 'auth.json'
    devices_file: str = 'devices.json'
    devices: list[DeviceConfig] = []
    interval_seconds: float = 5.0


cfg = load_config_from_args(Config)

init_logger(cfg.logger, logging.getLogger())


def login_and_get_api():
    auther = mijiaLogin()
    try:
        with open(cfg.auth_file, 'r') as f:
            auth = json.load(f)
        auther.auth_data = auth
        logging.info('已成功加载认证信息: %s', cfg.auth_file)
    except FileNotFoundError:
        logging.info('未找到认证信息，尝试登录')
        auth = auther.QRlogin()
        with open(cfg.auth_file, 'w') as f:
            json.dump(auth, f, indent=4)
    except json.JSONDecodeError:
        logging.info('认证信息格式错误，尝试重新登录')
        os.remove(cfg.auth_file)
        return login_and_get_api()

    api = mijiaAPI(auth)
    if not api.available:
        logging.info('API 不可用，认证已过期，需要重新登录')
        os.remove(cfg.auth_file)
        return login_and_get_api()
    logging.info('登录成功')
    return api


api = login_and_get_api()
# 获取设备列表
devices = api.get_devices_list()

# 保存设备列表到文件
with open(cfg.devices_file, 'w') as f:
    json.dump(devices, f, indent=4)
logging.info(f'设备列表已保存到 {cfg.devices_file}')


def get_device_by_name(name: str):
    for device in devices:
        if device['name'] == name:
            return device
    raise ValueError(f'未找到名称为 {name} 的设备')


def get_device_props(
    name: str,
    assert_model: str | None = None,
    sp_id_pairs: dict[str, (int, int)] = {},
) -> dict[str, dict[str, Any]]:
    device: dict = get_device_by_name(name)
    if assert_model:
        # 支持通配符匹配
        if '*' in assert_model:
            import fnmatch
            assert fnmatch.fnmatch(device['model'], assert_model), \
                f'设备 {device["name"]} 的型号 {device["model"]} 不符合通配模式 {assert_model}'
        else:
            assert device['model'] == assert_model, \
                f'设备 {device["name"]} 不是 {assert_model} 类型'

    query_list = []
    for _, (siid, piid) in sp_id_pairs.items():
        query_list.append({
            'did': device['did'],
            'siid': siid,
            'piid': piid,
        })
    props = api.get_devices_prop(query_list)
    result = {}
    for prop in props:
        siid = prop['siid']
        piid = prop['piid']
        value = prop['value']
        # 寻找sp_id_pairs中对应的键
        for key, (expected_siid, expected_piid) in sp_id_pairs.items():
            if siid == expected_siid and piid == expected_piid:
                result[key] = {'value': value}
                break
    if 'localip' in device:
        result['device_ip'] = device['localip']
    return result


NAMESPACE = 'mihome_exporter'
pc.start_http_server(cfg.port)
plug_power_on_status = pc.Gauge(
    namespace=NAMESPACE,
    name='plug_power_on_status',
    documentation='插座电源状态',
    labelnames=['device_ip', 'device_name'],
)

plug_temperature = pc.Gauge(
    namespace=NAMESPACE,
    name='plug_temperature',
    documentation='设备温度',
    labelnames=['device_ip', 'device_name'],
)

plug_electric_power = pc.Gauge(
    namespace=NAMESPACE,
    name='plug_electric_power',
    documentation='功率',
    labelnames=['device_ip', 'device_name'],
)


@register_collector(model='cuco.plug.v3')
def collect_cuco_plug_v3_metrics(device_name: str):
    props = get_device_props(
        name=device_name,
        assert_model=collect_cuco_plug_v3_metrics.model,
        sp_id_pairs={
            'power_on_status': (2, 1),  # 电源状态
            'electric_power': (11, 2),  # 功率
            'temperature': (12, 2),  # 设备温度
        }
    )
    logging.info(f'采集 {device_name} 的数据: {props}')
    device_ip = props.get('device_ip', 'unknown')
    plug_power_on_status.labels(
        device_ip=device_ip,
        device_name=device_name,
    ).set(
        value=props['power_on_status']['value'],
    )
    plug_electric_power.labels(
        device_ip=device_ip,
        device_name=device_name,
    ).set(
        value=props['electric_power']['value'],
    )
    plug_temperature.labels(
        device_ip=device_ip,
        device_name=device_name,
    ).set(
        value=props['temperature']['value'],
    )


@register_collector(model='chuangmi.plug.m3')
def collect_chuangmi_plug_m3_metrics(device_name: str):
    props = get_device_props(
        name=device_name,
        assert_model=collect_chuangmi_plug_m3_metrics.model,
        sp_id_pairs={
            'power_on_status': (2, 1),  # 电源状态
            'temperature': (2, 2),  # 设备温度
        }
    )
    logging.info(f'采集 {device_name} 的数据: {props}')
    device_ip = props.get('device_ip', 'unknown')
    plug_power_on_status.labels(
        device_ip=device_ip,
        device_name=device_name,
    ).set(
        value=props['power_on_status']['value'],
    )
    plug_temperature.labels(
        device_ip=device_ip,
        device_name=device_name,
    ).set(
        value=props['temperature']['value'],
    )


sensor_ht_temperature = pc.Gauge(
    namespace=NAMESPACE,
    name='sensor_ht_temperature',
    documentation='温度',
    labelnames=['device_name'],
)

sensor_ht_relative_humidity = pc.Gauge(
    namespace=NAMESPACE,
    name='sensor_ht_relative_humidity',
    documentation='相对湿度',
    labelnames=['device_name'],
)

sensor_ht_battery_level = pc.Gauge(
    namespace=NAMESPACE,
    name='sensor_ht_battery_level',
    documentation='电池电量',
    labelnames=['device_name'],
)


@register_collector(model='miaomiaoce.sensor_ht.t2')
def collect_miaomiaoce_sensor_ht_t2(device_name: str):
    props = get_device_props(
        name=device_name,
        assert_model=collect_miaomiaoce_sensor_ht_t2.model,
        sp_id_pairs={
            'temperature': (2, 1),  # 温度
            'relative_humidity': (2, 2),  # 相对湿度
            'battery_level': (3, 1),  # 电池电量
        }
    )
    logging.info(f'采集 {device_name} 的数据: {props}')
    sensor_ht_temperature.labels(
        device_name=device_name,
    ).set(
        value=props['temperature']['value'],
    )
    sensor_ht_relative_humidity.labels(
        device_name=device_name,
    ).set(
        value=props['relative_humidity']['value'],
    )
    sensor_ht_battery_level.labels(
        device_name=device_name,
    ).set(
        value=props['battery_level']['value'],
    )


router_download_speed = pc.Gauge(
    namespace=NAMESPACE,
    name='router_download_speed',
    documentation='路由器下载速度',
    labelnames=['device_name'],
)

router_connected_device_number = pc.Gauge(
    namespace=NAMESPACE,
    name='router_connected_device_number',
    documentation='路由器连接的设备数量',
    labelnames=['device_name'],
)


@register_collector(model='xiaomi.router.*')
def collect_router_metrics(device_name: str):
    props = get_device_props(
        name=device_name,
        assert_model=collect_router_metrics.model,
        sp_id_pairs={
            'download_speed': (2, 1),  # 下载速度
            'connected_device_number': (2, 2),  # 连接的设备数量
        }
    )
    logging.info(f'采集 {device_name} 的数据: {props}')
    router_download_speed.labels(
        device_name=device_name,
    ).set(
        value=props['download_speed']['value'],
    )
    router_connected_device_number.labels(
        device_name=device_name,
    ).set(
        value=props['connected_device_number']['value'],
    )


cooker_status = pc.Gauge(
    namespace=NAMESPACE,
    name='cooker_status',
    documentation='电饭煲烹饪状态',
    labelnames=['device_name'],
)


@register_collector(model='chunmi.cooker.normal2')
def collect_cooker_metrics(device_name: str):
    props = get_device_props(
        name=device_name,
        assert_model=collect_cooker_metrics.model,
        sp_id_pairs={
            'cooker_status': (2, 1),  # 烹饪状态
        }
    )
    logging.info(f'采集 {device_name} 的数据: {props}')
    cooker_status.labels(
        device_name=device_name,
    ).set(
        value=props['cooker_status']['value'],
    )


def collector_by_name(device_name: str):
    device = get_device_by_name(device_name)
    matcherd_collector: Optional[Callable[[str], None]] = None
    for (model_matcher, collector) in collectors.items():
        if '*' in model_matcher:
            import fnmatch
            if fnmatch.fnmatch(device['model'], model_matcher):
                if matcherd_collector is None:
                    matcherd_collector = collector
                else:
                    logging.warning(
                        f'设备 {device_name} 匹配到多个收集器: {matcherd_collector.__name__} 和 {collector.__name__}')
        else:
            if device['model'] == model_matcher:
                matcherd_collector = collector
    if matcherd_collector is None:
        logging.warning(
            f'未找到设备 {device_name} 的收集器，请检查设备型号和注册的收集器')
        return
    logging.info(f'使用收集器 {matcherd_collector.__name__} 采集设备 {device_name} 的数据')
    matcherd_collector(device_name)


def main():
    while True:
        for device in cfg.devices:
            collector_by_name(device.name)
        time.sleep(cfg.interval_seconds)


if __name__ == '__main__':
    main()
