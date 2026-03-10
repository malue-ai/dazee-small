# 小搭子日志收集器（可选）

从小搭子桌面应用的日志文件中提取指定日期的内容，上传到腾讯云 COS。通过系统计划任务每天自动执行。

> **这是一个完全可选的运维工具**，不会自动启用。需要用户主动执行 `--install` 才会注册定时任务。

## 安全说明

本脚本是开源透明的，不包含任何后门或硬编码的服务器地址。以下是安全设计要点：

- **零内置凭证**：源码和模板文件中不包含任何密钥、Token 或服务器地址。所有 COS 凭证由使用者自行配置，数据上传到使用者自己的 COS Bucket，开发者无法访问。
- **默认关闭**：脚本不会自动运行或采集任何数据，必须由使用者主动执行 `--install` 注册定时任务后才会生效。
- **完全可卸载**：随时通过 `--uninstall` 注销定时任务，彻底停止数据采集。
- **可预览**：上传前可使用 `--dry-run` 查看将要上传的内容和目标路径，确认无误后再正式执行。
- **仅读取应用日志**：脚本只读取小搭子自身生成的 `app.log` 和 `error.log`，不访问系统日志、浏览器数据、文件系统或任何其他应用数据。
- **采集信息范围**：除日志内容外，仅采集基础设备信息（操作系统、主机名、随机生成的设备 ID）用于日志归类，不采集 IP 地址、MAC 地址、硬件序列号等可追踪标识。
- **代码可审计**：整个脚本为单文件 Python 脚本（约 1000 行），逻辑简单清晰，欢迎审查。

## 前提条件

- Python 3.10+
- 小搭子已在本机运行过（日志目录已生成）
- 腾讯云 COS Bucket 已创建，有可用的 SecretId/SecretKey

## 部署步骤

### 1. 拷贝文件

将 `tools/log_collector/` 目录拷贝到目标机器的任意位置，例如：

```
Windows: C:\tools\log_collector\
macOS:   ~/tools/log_collector/
```

### 2. 安装依赖

```bash
python -m pip install cos-python-sdk-v5 pyyaml
```

### 3. 配置 COS 凭证

首次运行 `--install` 时会自动引导配置。也可手动配置：

```bash
cp cos_config.yaml.example cos_config.yaml
```

编辑 `cos_config.yaml`，填写：
- `secret_id` / `secret_key`：腾讯云 API 密钥
- `bucket`：COS Bucket 名称（格式 `bucket-appid`）
- `region`：Bucket 所在地域（如 `ap-shanghai`）
- `user`：当前机器使用者姓名（可选，不填则用系统用户名）

### 4. 测试运行

```bash
# 预览今天的日志（不上传）
python log_collector.py --dry-run

# 实际上传
python log_collector.py
```

### 5. 注册计划任务

```bash
# 自动注册每天 23:30 执行（Windows 和 macOS 均支持）
python log_collector.py --install
```

## 命令行参数

```
python log_collector.py [选项]

选项:
  --config PATH       COS 配置文件路径（默认：用户数据目录/config/cos_config.yaml）
  --user NAME         用户标识（覆盖配置文件中的 user）
  --log-dir PATH      日志目录（默认：自动探测）
  --date YYYY-MM-DD   目标日期（默认：今天）
  --dry-run           仅提取，不上传
  --install           注册系统计划任务
  --uninstall         注销系统计划任务
  --verbose           详细输出
```

## 常用场景

```bash
# 补传昨天的日志
python log_collector.py --date 2026-03-08

# 指定用户名上传
python log_collector.py --user zhangsan

# 开发模式（日志在项目根目录）
python log_collector.py --log-dir /path/to/dazee-small/logs

# 注销计划任务
python log_collector.py --uninstall
```

## COS 上传路径结构

```
{bucket}/
  logs/
    {user}/
      {device_id}/
        meta.json            # 设备信息 + 版本信息
        2026-03-09/
          app.log             # 当天应用日志（<= 2MB）
          app_part001.log     # 当天应用日志分片（> 2MB 时）
          app_part002.log
          error.log           # 当天错误日志
```

## 日志路径（自动探测）

| 系统 | 路径 |
|------|------|
| Windows | `%APPDATA%\com.zenflux.agent\logs\` |
| macOS | `~/Library/Application Support/com.zenflux.agent/logs/` |
| Linux | `~/.local/share/com.zenflux.agent/logs/` |

## 注意事项

- `cos_config.yaml` 包含 COS 凭证，**不要提交到任何代码仓库**
- 同一天多次执行会覆盖已上传的文件（幂等），不会产生重复数据
- 当天日志超过 2MB 时自动切片上传
- 设备 ID 首次运行自动生成，保存在小搭子数据目录下的 `device_id` 文件中
