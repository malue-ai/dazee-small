# 小搭子日志收集器

从小搭子桌面应用的日志文件中提取指定日期的内容，上传到腾讯云 COS。通过系统计划任务每天自动执行。

## 前提条件

- Python 3.10+（公司机器上已有）
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
pip install cos-python-sdk-v5 pyyaml
```

### 3. 配置 COS 凭证

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
  --config PATH       COS 配置文件路径（默认：脚本同目录 cos_config.yaml）
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
