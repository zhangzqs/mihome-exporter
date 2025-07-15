# my-exporter

个人自用的 Prometheus Metrics Exporter，包含以下模块：

## MiHome

米家相关智能家居的 Metrics Exporter

目前支持收集以下设备：

- 小米米家智能插座 WiFi 版
- 米家蓝牙温湿度计 2
- 米家智能插座 3
- 小米路由器 4A
- 米家 IH 电饭煲
- 小米路由器
- 米家空调伴侣 2

### 米家设备的协议参考文档

https://home.miot-spec.com/

- [小米米家蓝牙温湿度计 2](https://home.miot-spec.com/spec/miaomiaoce.sensor_ht.t2)
- [米家智能插座 3](https://home.miot-spec.com/spec/cuco.plug.v3)
- [小米路由器 4A](https://home.miot-spec.com/spec/xiaomi.router.r4a)

## QWeather

和风天气实时天气 API 数据抓取，支持以下数据的采集：

- 当前温度
- 当前湿度
- 体感温度
- 风向
- 风力等级
- 风速
- 气压

## 小米路由器

基于小米路由器的 API，采集路由器及各个设备的相关网络信息。
