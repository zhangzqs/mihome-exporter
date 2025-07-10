import logging
from threading import Thread
from typing import Optional, Type, TypeVar
import httpx
from pydantic import BaseModel
import time
import random
import hashlib
from prometheus_client import Gauge
from functools import lru_cache


def hashPassword(pwd: str, nonce: str) -> str:
    key = "a2ffa5c9be07488bbb04a3a47d3c5f6a"
    pwd_key = pwd + key
    pwdKeyHash = hashlib.sha1(pwd_key.encode()).hexdigest()

    nonce_pwd_key = nonce + pwdKeyHash
    noncePwdKeyHash = hashlib.sha1(nonce_pwd_key.encode()).hexdigest()
    return noncePwdKeyHash


def createNonce() -> str:
    typeVar = 0
    deviceID = ""
    timeVar = int(time.time())  # 获取当前Unix时间戳
    randomVar = random.randint(0, 9999)  # 生成0-9999的随机整数
    return f"{typeVar}_{deviceID}_{timeVar}_{randomVar}"


class MiRouterConfig(BaseModel):
    base_addr: str = "http://miwifi.com"
    "路由器地址"
    password: str
    "路由器密码"
    interval_seconds: int = 10
    "采集间隔，单位是秒"


cfg: Optional[MiRouterConfig] = None


def init(_cfg: MiRouterConfig):
    global cfg
    cfg = _cfg


class InitInfo(BaseModel):
    romversion: str
    countrycode: str
    id: str
    routername: str
    "路由器名称"

    routerId: str
    hardware: str
    "路由器型号"

    newEncryptMode: Optional[float] = None
    "如果不为None则使用新的加密模式"


T = TypeVar("T", bound=BaseModel)


def must_get_body(resp: httpx.Response, t: Type[T]) -> T:
    resp.raise_for_status()
    resp_body = resp.json()
    if resp_body.get('code') != 0:
        raise RuntimeError(f"请求失败：{resp_body}")
    return t(**resp_body)


def get_init_info() -> InitInfo:
    resp = httpx.get(
        url=f"{cfg.base_addr}/cgi-bin/luci/api/xqsystem/init_info",
    )
    return must_get_body(resp, InitInfo)


class LoginResponse(BaseModel):
    token: str


@lru_cache(maxsize=1)
def login() -> LoginResponse:
    init_into = get_init_info()
    nonce = createNonce()
    if init_into.newEncryptMode is None:
        hashed_password = hashPassword(cfg.password, nonce)
    else:
        raise NotImplementedError(
            "小米路由器新的加密模式尚未实现，不支持登录"
        )
    resp = httpx.post(
        url=f"{cfg.base_addr}/cgi-bin/luci/api/xqsystem/login",
        data={
            "username": "admin",
            "password": hashed_password,
            "logtype": "2",
            "nonce": nonce,
        },
    )
    return must_get_body(resp, LoginResponse)


NAMESPACE = "mirouter"

device_up_bytes = Gauge(
    namespace=NAMESPACE,
    name='device_up_bytes',
    documentation='设备上传字节数',
    labelnames=['device_name', 'mac'],
)

device_down_bytes = Gauge(
    namespace=NAMESPACE,
    name='device_down_bytes',
    documentation='设备下载字节数',
    labelnames=['device_name', 'mac'],
)

device_up_speed_bytes_per_second = Gauge(
    namespace=NAMESPACE,
    name='device_up_speed_bytes_per_second',
    documentation='设备上传速度（字节/秒）',
    labelnames=['device_name', 'mac'],
)

device_down_speed_bytes_per_second = Gauge(
    namespace=NAMESPACE,
    name='device_down_speed_bytes_per_second',
    documentation='设备下载速度（字节/秒）',
    labelnames=['device_name', 'mac'],
)

device_online_seconds = Gauge(
    namespace=NAMESPACE,
    name='device_online_seconds',
    documentation='设备在线时长（秒）',
    labelnames=['device_name', 'mac'],
)

device_max_up_speed_bytes_per_second = Gauge(
    namespace=NAMESPACE,
    name='device_max_up_speed_bytes_per_second',
    documentation='设备最大上传速度（字节/秒）',
    labelnames=['device_name', 'mac'],
)

device_max_down_speed_bytes_per_second = Gauge(
    namespace=NAMESPACE,
    name='device_max_down_speed_bytes_per_second',
    documentation='设备最大下载速度（字节/秒）',
    labelnames=['device_name', 'mac'],
)


class DeviceStatus(BaseModel):
    devname: str
    "设备名称"
    mac: str
    "mac地址"
    upspeed: str
    "实时上传速度"
    downspeed: str
    "实时下载速度"
    upload: str
    "当前已上传量"
    download: str
    "当前已下载量"
    online: str
    "在线了多久，单位是秒"
    maxdownloadspeed: str
    "最大下载速度"
    maxuploadspeed: str
    "最大上传速度"


def collect_device_status(s: DeviceStatus):
    device_up_bytes.labels(
        device_name=s.devname,
        mac=s.mac,
    ).set(int(s.upload))
    device_down_bytes.labels(
        device_name=s.devname,
        mac=s.mac,
    ).set(int(s.download))
    device_up_speed_bytes_per_second.labels(
        device_name=s.devname,
        mac=s.mac,
    ).set(int(s.upspeed))
    device_down_speed_bytes_per_second.labels(
        device_name=s.devname,
        mac=s.mac,
    ).set(int(s.downspeed))
    device_online_seconds.labels(
        device_name=s.devname,
        mac=s.mac,
    ).set(int(s.online))
    device_max_up_speed_bytes_per_second.labels(
        device_name=s.devname,
        mac=s.mac,
    ).set(int(s.maxuploadspeed))
    device_max_down_speed_bytes_per_second.labels(
        device_name=s.devname,
        mac=s.mac,
    ).set(int(s.maxdownloadspeed))


class MemoryStatus(BaseModel):
    usage: float
    "内存使用率"


memory_usage_percent = Gauge(
    namespace=NAMESPACE,
    name='memory_usage_percent',
    documentation='内存使用率',
)


def collect_memory_status(s: MemoryStatus):
    memory_usage_percent.set(s.usage)


class CountStatus(BaseModel):
    all: int
    "历史累计在线设备数"
    online: int
    "当前在线设备数"


history_device_count = Gauge(
    namespace=NAMESPACE,
    name='history_device_count',
    documentation='历史累计在线设备数',
)

current_online_device_count = Gauge(
    namespace=NAMESPACE,
    name='current_online_device_count',
    documentation='当前在线设备数',
)


def collect_count_status(s: CountStatus):
    history_device_count.set(s.all)
    current_online_device_count.set(s.online)


class CpuStatus(BaseModel):
    load: float
    "CPU使用率"


cpu_load_percent = Gauge(
    namespace=NAMESPACE,
    name='cpu_load_percent',
    documentation='CPU使用率',
)


def collect_cpu_status(s: CpuStatus):
    cpu_load_percent.set(s.load)


class WanStatus(BaseModel):
    devname: str
    "设备名称"
    upspeed: str
    "实时上传速度"
    downspeed: str
    "实时下载速度"
    upload: str
    "当前已上传量"
    download: str
    "当前已下载量"
    maxdownloadspeed: str
    "最大下载速度"
    maxuploadspeed: str
    "最大上传速度"


wan_up_bytes = Gauge(
    namespace=NAMESPACE,
    name='wan_up_bytes',
    documentation='WAN口上传字节数',
    labelnames=['device_name'],
)

wan_down_bytes = Gauge(
    namespace=NAMESPACE,
    name='wan_down_bytes',
    documentation='WAN口下载字节数',
    labelnames=['device_name'],
)

wan_up_speed_bytes_per_second = Gauge(
    namespace=NAMESPACE,
    name='wan_up_speed_bytes_per_second',
    documentation='WAN口上传速度（字节/秒）',
    labelnames=['device_name'],
)

wan_down_speed_bytes_per_second = Gauge(
    namespace=NAMESPACE,
    name='wan_down_speed_bytes_per_second',
    documentation='WAN口下载速度（字节/秒）',
    labelnames=['device_name'],
)

wan_max_up_speed_bytes_per_second = Gauge(
    namespace=NAMESPACE,
    name='wan_max_up_speed_bytes_per_second',
    documentation='WAN口最大上传速度（字节/秒）',
    labelnames=['device_name'],
)

wan_max_down_speed_bytes_per_second = Gauge(
    namespace=NAMESPACE,
    name='wan_max_down_speed_bytes_per_second',
    documentation='WAN口最大下载速度（字节/秒）',
    labelnames=['device_name'],
)


def collect_wan_status(s: WanStatus):
    wan_up_bytes.labels(
        device_name=s.devname
    ).set(int(s.upload))
    wan_down_bytes.labels(
        device_name=s.devname
    ).set(int(s.download))
    wan_up_speed_bytes_per_second.labels(
        device_name=s.devname
    ).set(int(s.upspeed))
    wan_down_speed_bytes_per_second.labels(
        device_name=s.devname
    ).set(int(s.downspeed))
    wan_max_up_speed_bytes_per_second.labels(
        device_name=s.devname
    ).set(int(s.maxuploadspeed))
    wan_max_down_speed_bytes_per_second.labels(
        device_name=s.devname
    ).set(int(s.maxdownloadspeed))


class StatusResponse(BaseModel):
    dev: list[DeviceStatus]
    "设备状态列表"
    mem: MemoryStatus
    "内存状态"
    count: CountStatus
    "设备统计信息"
    upTime: str
    "路由器运行时间，单位是秒"
    cpu: CpuStatus
    "CPU状态"
    wan: WanStatus
    "WAN口状态"


up_time_seconds = Gauge(
    namespace=NAMESPACE,
    name='up_time_seconds',
    documentation='路由器运行时间（秒）',
)


def collect_status(s: StatusResponse):
    for device_status in s.dev:
        collect_device_status(device_status)
    collect_memory_status(s.mem)
    collect_count_status(s.count)
    collect_cpu_status(s.cpu)
    collect_wan_status(s.wan)
    up_time_seconds.set(float(s.upTime))


def get_status() -> StatusResponse:
    token = login().token
    resp = httpx.get(
        url=f"{cfg.base_addr}/cgi-bin/luci/;stok={token}/api/misystem/status",
    )
    return must_get_body(resp, StatusResponse)


def collect_once():
    while True:
        try:
            status = get_status()
            logging.info("成功获取路由器状态: %s", status)
            collect_status(status)
            return
        except Exception as e:
            logging.error(f"获取状态时发生错误: {e}")
            logging.exception(e)
            login.cache_clear() # 清空缓存后重试


def start_collect() -> Thread:
    if cfg is None:
        raise ValueError('请先调用 init() 初始化配置')

    def run():
        while True:
            collect_once()
            time.sleep(cfg.interval_seconds)

    t = Thread(target=run, name='MiRouterCollectorThread', daemon=True)
    t.start()
    return t
