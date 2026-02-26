---
name: home-assistant
description: Control smart home devices via Home Assistant. Lights, climate, locks, sensors, scenes, automations — all through natural language.
metadata:
  xiaodazi:
    dependency_level: external
    os: [common]
    backend_type: mcp
    user_facing: true
---

# Home Assistant — 智能家居控制

通过 Home Assistant 控制家中所有智能设备：灯光、空调、窗帘、门锁、传感器、场景、自动化等。支持 2600+ 品牌，一句话操控全屋。

## 使用场景

- 用户说「把客厅灯调暗一点」「关掉所有灯」
- 用户说「空调调到 24 度」「打开制冷模式」
- 用户说「现在家里温度多少？」「湿度多少？」
- 用户说「我要睡觉了」→ 触发 "晚安" 场景（关灯、锁门、降温）
- 用户说「帮我设个自动化：每天早上 7 点开窗帘」
- 结合 `pomodoro`：番茄钟结束时调亮灯光提醒休息
- 结合 `daily-briefing`：早间简报时自动调节室内环境

## 前置条件

1. 运行 Home Assistant 实例（https://www.home-assistant.io/）
2. 在 Home Assistant 中生成长期访问令牌（Long-Lived Access Token）
3. 设置环境变量：`export HOMEASSISTANT_TOKEN="your-token"`
4. 设置环境变量：`export HOMEASSISTANT_URL="http://homeassistant.local:8123"`

Home Assistant 2025.4.4+ 内置 MCP Server 支持，可直接通过 MCP 协议通信。

## 执行方式

### 通过 MCP 工具调用（推荐）

Home Assistant 提供 MCP Server 集成，通过 MCP 协议直接操作：

#### 控制设备

```
工具: call_service
参数:
  domain: "light"
  service: "turn_on"
  target:
    entity_id: "light.living_room"
  data:
    brightness_pct: 50
    color_temp_kelvin: 3000
```

#### 查询状态

```
工具: get_state
参数:
  entity_id: "sensor.living_room_temperature"
```

#### 触发场景

```
工具: call_service
参数:
  domain: "scene"
  service: "turn_on"
  target:
    entity_id: "scene.good_night"
```

### 通过 REST API 调用（备选）

```bash
# 获取所有设备状态
curl -s "$HOMEASSISTANT_URL/api/states" \
  -H "Authorization: Bearer $HOMEASSISTANT_TOKEN"

# 控制灯光
curl -s -X POST "$HOMEASSISTANT_URL/api/services/light/turn_on" \
  -H "Authorization: Bearer $HOMEASSISTANT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"entity_id": "light.living_room", "brightness_pct": 80}'

# 设置空调温度
curl -s -X POST "$HOMEASSISTANT_URL/api/services/climate/set_temperature" \
  -H "Authorization: Bearer $HOMEASSISTANT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"entity_id": "climate.bedroom", "temperature": 24}'

# 查询传感器
curl -s "$HOMEASSISTANT_URL/api/states/sensor.outdoor_temperature" \
  -H "Authorization: Bearer $HOMEASSISTANT_TOKEN"
```

### 常用设备控制模板

**灯光**：
```
开灯/关灯: light.turn_on / light.turn_off
调亮度: brightness_pct (0-100)
调色温: color_temp_kelvin (2700暖光-6500冷光)
调颜色: rgb_color [R, G, B]
```

**空调/暖通**：
```
设温度: climate.set_temperature → temperature
设模式: climate.set_hvac_mode → hvac_mode (heat/cool/auto/off)
设风速: climate.set_fan_mode → fan_mode (low/medium/high/auto)
```

**窗帘**：
```
开/关: cover.open_cover / cover.close_cover
设位置: cover.set_cover_position → position (0关-100全开)
```

**门锁**：
```
锁门: lock.lock
开锁: lock.unlock (需确认！调用 hitl 工具确认)
```

**场景**：
```
触发: scene.turn_on → entity_id: scene.xxx
```

## 安全规范

- **门锁操作**：开锁前必须通过 `hitl` 工具获得用户确认
- **安防相关**：关闭安防系统前必须确认
- **批量操作**：一次性控制 5 个以上设备时先告知用户具体操作清单
- 不主动推荐用户未拥有的设备或功能

## 与其他 Skills 的协作

| 组合 | 效果 |
|------|------|
| home-assistant + pomodoro | 番茄钟开始→调暗灯光营造专注环境；结束→调亮提醒休息 |
| home-assistant + daily-briefing | 早间简报时自动开灯、调温、播报天气 |
| home-assistant + reminder | 提醒事项触发时闪烁灯光辅助提醒 |
| home-assistant + scheduled-tasks | 定时自动化：每晚 11 点关灯锁门 |

## 输出规范

- 执行设备操作后简洁确认：「✅ 客厅灯已调至 50% 亮度」
- 查询状态时使用表格呈现多个传感器数据
- 批量操作给出操作清单摘要
- 设备不可达时给出故障排查建议（检查网络、重启设备）
