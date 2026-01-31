# API 描述文档

此目录存放 REST API 的使用文档，供 Agent 调用外部 API 时参考。

## 文件格式

每个 API 使用一个 Markdown 文件描述，包含：

- API 基础信息
- 认证方式
- 端点列表
- 请求/响应示例

## 示例

```markdown
# Weather API

## 基础信息
- Base URL: https://api.weather.com/v1
- 认证: API Key (Header: X-API-Key)

## 端点

### GET /current
获取当前天气

**参数:**
- city: 城市名称

**响应:**
```json
{
  "temp": 25,
  "humidity": 60
}
```
```
