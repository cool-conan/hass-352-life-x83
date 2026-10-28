# 352-life for Home Assistant

`352-life` 是面向 352 X83 空气净化器的 Home Assistant custom integration，通过 352Life 旧云端协议读取设备状态并控制电源、显示灯、运行模式和风速。

这是非官方社区项目，与 352 品牌方无隶属或背书关系。

源码仓库：<https://github.com/cool-conan/hass-352-life-x83>

## 功能

- UI 配置与重新认证，无需编辑 YAML；
- 电源与显示灯开关；
- 自动、强力、睡眠、手动四种运行模式；
- 1–6 档风速控制；
- 在线状态、PM2.5 和当前风速档位；
- 断线后有限重连，认证失效时进入 reauth；
- 所有控制等待设备状态回读，不做 optimistic update。

支持型号：`X83`。集成显示名称为 `352-life`，domain 为 `life352_x83`。

## 使用前准备

请创建或使用一个已获得 X83 分享权限的备用成员账号，不要使用 owner 主账号。配置时的密码登录会使该账号在 352Life App 中的原登录态失效；Home Assistant 后续只复用会话 token，不会在后台自动重试密码登录。

旧设备列表签名还需要从已审计 APK 生成部署私有凭据：

```bash
gh repo clone cool-conan/hass-352-life-x83
cd hass-352-life-x83
python3 scripts/create_private_credentials.py
```

如果 APK 不在默认的 `~/Downloads` 或文件名不同，请显式指定：

```bash
python3 scripts/create_private_credentials.py --apk /path/to/352Life.apk
```

脚本生成 Git ignored 文件：

```text
private/life352_x83_private.json
```

部署时将其复制到：

```text
/config/.storage/life352_x83_private.json
```

文件必须是普通文件、权限为 `0600`，并且 Home Assistant 进程可读。不要把文件内容提交到 Git 或粘贴到日志中。

## 全新安装

1. 确认 Home Assistant 的真实 `/config` 挂载路径。
2. 将 `custom_components/life352_x83/` 复制到 `/config/custom_components/life352_x83/`。
3. 将私有凭据复制到 `/config/.storage/life352_x83_private.json` 并设为 `0600`。
4. 确认 `/config/custom_components/` 下只有一个 `life352_x83` 目录，并且没有 `._life352_x83` 等 AppleDouble 文件。
5. 由 Home Assistant 管理员手动重启实例以加载新组件。
6. 打开“设置 → 设备与服务 → 添加集成”，搜索 `352-life`，输入备用成员账号的手机号码和密码。

从 macOS 复制组件时，应禁用扩展属性并排除缓存文件：

```bash
COPYFILE_DISABLE=1 tar --no-xattrs --exclude='._*' --exclude='__pycache__' \
  -cf - -C custom_components life352_x83
```

## 实体

| 类型 | 实体 | 行为 |
|---|---|---|
| Switch | 电源 | 开机、关机；刷新失败后仍保留恢复入口 |
| Switch | 显示灯 | 开启或关闭设备显示灯 |
| Select | 运行模式 | 自动、强力、睡眠、手动 |
| Number | 风速控制 | 1–6 档整数 |
| Binary sensor | 连接状态 | 展示云端返回的设备在线状态 |
| Sensor | PM2.5 | 当前 PM2.5 |
| Sensor | 风速档位 | 当前设备上报档位 |

控制会按设备协议执行三轮发送，并且只在收到匹配的 device-data 状态后更新实体。超时、断线或回读不匹配时，操作会报错并保留上一次可信状态。

## 故障排查

- 无法加载 integration：确认 `/config/custom_components/life352_x83/manifest.json` 存在，并移除 `custom_components` 下的重复目录或 AppleDouble 文件。
- `private credential ... missing/0600/digest`：检查私有凭据路径、文件类型、权限和摘要；不要打印文件内容。
- `authentication failed/refused`：从集成页面发起“重新认证”，重新输入备用成员账号；集成不会自动密码重登。
- `state refresh failed`：检查 Home Assistant 到 `wifi.352air.com:11591` 的 DNS、TLS 和 TCP 连通性，等待下一次有界重连；不要关闭证书校验。
- `did not confirm the requested ... state`：设备没有返回匹配状态，实体会保留上一次可信值；不要手工篡改实体 state。
- reload/setup 长时间卡在连接关闭：检查 HA 到 352 云端的网络连接；integration 的 TLS close handshake 最多等待 1 秒。

diagnostics 不应包含账号、密码、token、MAC、authCode、设备名、工作服务器 endpoint、原始 frame 或私钥。如发现这些内容，请不要分享 diagnostics。

## 卸载

先在“设置 → 设备与服务”中删除 `352-life` config entry，确认实体已移除后，再删除 `/config/custom_components/life352_x83`。私有凭据需要单独删除；删除前请确认没有其他部署仍在使用。

## 本地验证

在已安装 Home Assistant 2026.10.2 的 Python 环境中运行：

```bash
PYTHONPYCACHEPREFIX=/tmp/x83-ha-pycache \
  python -m unittest discover -s tests -v
```

## 安全边界

- TLS 使用系统 CA 与 hostname verification；
- 不发送异常登录 opcode `0x89`；
- 每个 Home Assistant 进程最多尝试一次密码登录；
- 不在日志或 diagnostics 中暴露凭据和设备标识；
- 状态只能由真实设备回读更新。

## License

[MIT](LICENSE)
