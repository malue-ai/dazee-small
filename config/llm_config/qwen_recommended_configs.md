# 通义千问 API 推荐配置列表

本文档基于通义千问 API 官方文档，为不同使用场景提供推荐参数配置。

## 目录

1. [文本输入](#文本输入)
2. [流式输出](#流式输出)
3. [图像输入](#图像输入)
4. [视频输入](#视频输入)
5. [音频输入](#音频输入)
6. [联网搜索](#联网搜索)
7. [工具调用](#工具调用)
8. [异步调用](#异步调用)
9. [文档理解](#文档理解)

---

## 文本输入

### 场景1：通用对话（推荐配置）

**适用场景**：日常对话、问答、内容生成

| 参数 | 推荐值 | 说明 |
|------|--------|------|
| `model` | `qwen-plus` 或 `qwen-max` | 根据需求选择 |
| `temperature` | `0.7-1.0` | 平衡创造性和准确性 |
| `top_p` | `0.8` | 核采样阈值 |
| `max_tokens` | `2000` | 根据输出长度需求调整 |
| `result_format` | `message` | 推荐格式，便于多轮对话 |
| `stream` | `false` | 非流式输出 |
| `incremental_output` | `true` | 流式时推荐开启 |

**Python 示例**：
```python
import os
import dashscope

messages = [
    {'role': 'system', 'content': 'You are a helpful assistant.'},
    {'role': 'user', 'content': '你是谁？'}
]

response = dashscope.Generation.call(
    api_key=os.getenv('DASHSCOPE_API_KEY'),
    model="qwen-plus",
    messages=messages,
    temperature=0.8,
    top_p=0.8,
    max_tokens=2000,
    result_format='message'
)
print(response)
```

**curl 示例**：
```bash
curl -X POST https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation \
  -H "Authorization: Bearer sk-xxx" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen-plus",
    "input": {
      "messages": [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "你是谁？"}
      ]
    },
    "parameters": {
      "temperature": 0.8,
      "top_p": 0.8,
      "max_tokens": 2000,
      "result_format": "message"
    }
  }'
```

### 场景2：确定性输出（技术文档、代码生成）

**适用场景**：代码生成、技术文档、结构化输出

| 参数 | 推荐值 | 说明 |
|------|--------|------|
| `model` | `qwen-plus` 或 `qwen-max` |  |
| `temperature` | `0.0-0.3` | 低温度保证确定性 |
| `top_p` | `0.9` |  |
| `max_tokens` | `4000-8000` | 代码生成需要更长输出 |
| `result_format` | `message` |  |
| `response_format` | `{"type": "json_object"}` | 需要JSON输出时使用 |
| `repetition_penalty` | `1.05` | 降低重复度 |

**Python 示例**：
```python
response = dashscope.Generation.call(
    api_key=os.getenv('DASHSCOPE_API_KEY'),
    model="qwen-plus",
    messages=messages,
    temperature=0.2,
    top_p=0.9,
    max_tokens=4000,
    repetition_penalty=1.05,
    result_format='message',
    response_format={"type": "json_object"}  # 可选
)
```

### 场景3：创意写作（高多样性）

**适用场景**：创意写作、头脑风暴、广告文案

| 参数 | 推荐值 | 说明 |
|------|--------|------|
| `model` | `qwen-plus` 或 `qwen-max` |  |
| `temperature` | `1.0-1.5` | 高温度增加多样性 |
| `top_p` | `0.95` |  |
| `presence_penalty` | `0.6-1.0` | 降低内容重复度 |
| `max_tokens` | `2000-4000` |  |
| `n` | `2-4` | 生成多个候选（仅支持部分模型） |

**Python 示例**：
```python
response = dashscope.Generation.call(
    api_key=os.getenv('DASHSCOPE_API_KEY'),
    model="qwen-plus",
    messages=messages,
    temperature=1.2,
    top_p=0.95,
    presence_penalty=0.8,
    max_tokens=3000,
    n=2,  # 生成2个候选
    result_format='message'
)
```

---

## 流式输出

### 场景1：实时对话（推荐配置）

**适用场景**：实时对话、长文本生成、提升用户体验

| 参数 | 推荐值 | 说明 |
|------|--------|------|
| `model` | `qwen-plus` 或 `qwen-max` |  |
| `stream` | `true` | 必须开启 |
| `incremental_output` | `true` | **强烈推荐**，增量输出 |
| `temperature` | `0.7-1.0` |  |
| `max_tokens` | `2000-8000` | 根据需求调整 |

**Python 示例**：
```python
import dashscope

messages = [
    {'role': 'user', 'content': '请写一篇关于AI的文章'}
]

responses = dashscope.Generation.call(
    api_key=os.getenv('DASHSCOPE_API_KEY'),
    model="qwen-plus",
    messages=messages,
    stream=True,
    incremental_output=True,  # 增量输出
    temperature=0.8,
    max_tokens=4000,
    result_format='message'
)

for response in responses:
    if response.status_code == 200:
        output = response.output
        choices = output.get('choices', [])
        if choices:
            message = choices[0].get('message', {})
            content = message.get('content', '')
            if content:
                print(content, end='', flush=True)
    else:
        print(f"Error: {response.message}")
```

**Node.js 示例**：
```javascript
const axios = require('axios');

async function streamChat() {
  const response = await axios.post(
    'https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation',
    {
      model: 'qwen-plus',
      input: {
        messages: [
          { role: 'user', content: '请写一篇关于AI的文章' }
        ]
      },
      parameters: {
        stream: true,
        incremental_output: true,
        temperature: 0.8,
        max_tokens: 4000,
        result_format: 'message'
      }
    },
    {
      headers: {
        'Authorization': `Bearer ${process.env.DASHSCOPE_API_KEY}`,
        'Content-Type': 'application/json',
        'X-DashScope-SSE': 'enable'  // HTTP流式必须设置
      },
      responseType: 'stream'
    }
  );

  response.data.on('data', (chunk) => {
    const lines = chunk.toString().split('\n');
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const data = JSON.parse(line.slice(6));
        if (data.output?.choices?.[0]?.message?.content) {
          process.stdout.write(data.output.choices[0].message.content);
        }
      }
    }
  });
}
```

**curl 示例（SSE流式）**：
```bash
curl -X POST https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation \
  -H "Authorization: Bearer sk-xxx" \
  -H "Content-Type: application/json" \
  -H "X-DashScope-SSE: enable" \
  -d '{
    "model": "qwen-plus",
    "input": {
      "messages": [
        {"role": "user", "content": "请写一篇关于AI的文章"}
      ]
    },
    "parameters": {
      "stream": true,
      "incremental_output": true,
      "temperature": 0.8,
      "max_tokens": 4000,
      "result_format": "message"
    }
  }'
```

### 场景2：思考模式流式输出（Qwen3系列）

**适用场景**：复杂推理任务，需要查看思考过程

| 参数 | 推荐值 | 说明 |
|------|--------|------|
| `model` | `qwen3-max-preview` | Qwen3系列 |
| `stream` | `true` | 必须开启 |
| `incremental_output` | `true` | Qwen3只支持true |
| `enable_thinking` | `true` | 开启思考模式 |
| `thinking_budget` | `10000` | 思考长度预算 |
| `result_format` | `message` | Qwen3必须为message |

**Python 示例**：
```python
responses = dashscope.Generation.call(
    api_key=os.getenv('DASHSCOPE_API_KEY'),
    model="qwen3-max-preview",
    messages=messages,
    stream=True,
    incremental_output=True,
    enable_thinking=True,
    thinking_budget=10000,
    result_format='message'
)

for response in responses:
    if response.status_code == 200:
        output = response.output
        # 思考内容
        if 'reasoning_content' in output:
            print(f"[思考] {output['reasoning_content']}")
        # 正常内容
        choices = output.get('choices', [])
        if choices:
            message = choices[0].get('message', {})
            content = message.get('content', '')
            if content:
                print(content, end='', flush=True)
```

---

## 图像输入

### 场景1：图像理解（Qwen-VL系列）

**适用场景**：图像描述、图像问答、OCR

| 参数 | 推荐值 | 说明 |
|------|--------|------|
| `model` | `qwen-vl-plus` 或 `qwen-vl-max` | VL模型 |
| `temperature` | `0.1-0.3` | 图像理解需要确定性 |
| `max_tokens` | `1000-2000` |  |
| `result_format` | `message` | VL模型必须为message |
| `vl_high_resolution_images` | `true` | 高分辨率图像时开启 |
| `vl_enable_image_hw_output` | `true` | 需要获取图像尺寸时开启 |

**Python 示例**：
```python
import dashscope
from dashscope import MultiModalConversation

messages = [
    {
        'role': 'user',
        'content': [
            {'image': 'https://example.com/image.jpg'},
            {'text': '请描述这张图片'}
        ]
    }
]

response = dashscope.MultiModalConversation.call(
    model='qwen-vl-plus',
    messages=messages,
    temperature=0.2,
    max_tokens=1500,
    result_format='message',
    vl_high_resolution_images=True,
    vl_enable_image_hw_output=True
)
```

**curl 示例**：
```bash
curl -X POST https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation \
  -H "Authorization: Bearer sk-xxx" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen-vl-plus",
    "input": {
      "messages": [
        {
          "role": "user",
          "content": [
            {"image": "https://example.com/image.jpg"},
            {"text": "请描述这张图片"}
          ]
        }
      ]
    },
    "parameters": {
      "temperature": 0.2,
      "max_tokens": 1500,
      "result_format": "message",
      "vl_high_resolution_images": true,
      "vl_enable_image_hw_output": true
    }
  }'
```

### 场景2：文字提取（OCR）

**适用场景**：文档OCR、图像文字提取

| 参数 | 推荐值 | 说明 |
|------|--------|------|
| `model` | `qwen-vl-plus_2025-01-25` | 特定版本 |
| `temperature` | `0.1` | 低温度保证准确性 |
| `repetition_penalty` | `1.0` | 文档建议值 |
| `presence_penalty` | `1.5` | 文档建议值 |
| `max_tokens` | `4000` | 长文档需要更多token |

**Python 示例**：
```python
response = dashscope.MultiModalConversation.call(
    model='qwen-vl-plus_2025-01-25',
    messages=messages,
    temperature=0.1,
    repetition_penalty=1.0,
    presence_penalty=1.5,
    max_tokens=4000,
    result_format='message'
)
```

---

## 视频输入

### 场景1：视频理解（Qwen-VL系列）

**适用场景**：视频内容理解、视频问答

| 参数 | 推荐值 | 说明 |
|------|--------|------|
| `model` | `qwen-vl-max` | 支持视频的模型 |
| `temperature` | `0.2-0.5` |  |
| `max_tokens` | `2000-4000` |  |
| `result_format` | `message` |  |

**Python 示例**：
```python
messages = [
    {
        'role': 'user',
        'content': [
            {'video': 'https://example.com/video.mp4'},
            {'text': '请描述这个视频的主要内容'}
        ]
    }
]

response = dashscope.MultiModalConversation.call(
    model='qwen-vl-max',
    messages=messages,
    temperature=0.3,
    max_tokens=3000,
    result_format='message'
)
```

---

## 音频输入

### 场景1：音频理解（Qwen-Audio系列）

**适用场景**：语音转文字、音频理解、多语言识别

| 参数 | 推荐值 | 说明 |
|------|--------|------|
| `model` | `qwen-audio-turbo` 或 `qwen-audio-plus` | Audio模型 |
| `temperature` | `0.0-0.3` | 音频转文字需要确定性 |
| `max_tokens` | `2000-4000` |  |
| `result_format` | `message` | Audio模型必须为message |

**Python 示例**：
```python
import dashscope

messages = [
    {
        'role': 'user',
        'content': [
            {'audio': 'https://example.com/audio.wav'},
            {'text': '请转写这段音频'}
        ]
    }
]

response = dashscope.MultiModalConversation.call(
    model='qwen-audio-turbo',
    messages=messages,
    temperature=0.1,
    max_tokens=3000,
    result_format='message'
)
```

---

## 联网搜索

### 场景1：启用联网搜索（推荐配置）

**适用场景**：需要实时信息的问答、新闻查询、最新数据

| 参数 | 推荐值 | 说明 |
|------|--------|------|
| `model` | `qwen-plus` 或 `qwen-max` | 支持联网搜索的模型 |
| `enable_search` | `true` | 必须开启 |
| `search_options` | `{"search_mode": "auto"}` | 自动搜索模式 |
| `temperature` | `0.7-1.0` |  |
| `max_tokens` | `2000-4000` |  |

**Python 示例**：
```python
response = dashscope.Generation.call(
    api_key=os.getenv('DASHSCOPE_API_KEY'),
    model="qwen-plus",
    messages=messages,
    enable_search=True,
    search_options={
        "search_mode": "auto",  # 自动模式
        # "forced_search": True,  # 强制搜索（可选）
    },
    temperature=0.8,
    max_tokens=3000,
    result_format='message'
)
```

**curl 示例**：
```bash
curl -X POST https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation \
  -H "Authorization: Bearer sk-xxx" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen-plus",
    "input": {
      "messages": [
        {"role": "user", "content": "今天北京的天气怎么样？"}
      ]
    },
    "parameters": {
      "enable_search": true,
      "search_options": {
        "search_mode": "auto"
      },
      "temperature": 0.8,
      "max_tokens": 3000,
      "result_format": "message"
    }
  }'
```

### 场景2：强制联网搜索

**适用场景**：必须使用最新信息，不允许使用模型知识

| 参数 | 推荐值 | 说明 |
|------|--------|------|
| `enable_search` | `true` |  |
| `search_options` | `{"search_mode": "auto", "forced_search": true}` | 强制搜索 |

**Python 示例**：
```python
response = dashscope.Generation.call(
    api_key=os.getenv('DASHSCOPE_API_KEY'),
    model="qwen-plus",
    messages=messages,
    enable_search=True,
    search_options={
        "search_mode": "auto",
        "forced_search": True  # 强制搜索
    },
    result_format='message'
)
```

---

## 工具调用

### 场景1：Function Calling（推荐配置）

**适用场景**：需要调用外部工具、API、函数

| 参数 | 推荐值 | 说明 |
|------|--------|------|
| `model` | `qwen-plus` 或 `qwen-max` |  |
| `tools` | `[...]` | 工具定义数组 |
| `tool_choice` | `"auto"` | 自动选择工具 |
| `result_format` | `"message"` | **必须为message** |
| `parallel_tool_calls` | `true` | 并行工具调用（推荐） |
| `temperature` | `0.3-0.7` | 工具调用需要一定确定性 |

**Python 示例**：
```python
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "获取指定城市的天气信息",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "城市名称"
                    }
                },
                "required": ["city"]
            }
        }
    }
]

response = dashscope.Generation.call(
    api_key=os.getenv('DASHSCOPE_API_KEY'),
    model="qwen-plus",
    messages=messages,
    tools=tools,
    tool_choice="auto",  # 或 "none" 禁用工具，或 {"type": "function", "function": {"name": "get_weather"}} 强制调用
    parallel_tool_calls=True,  # 并行工具调用
    result_format="message",  # 必须
    temperature=0.5
)
```

**Java 示例**：
```java
import com.alibaba.dashscope.aigc.generation.Generation;
import com.alibaba.dashscope.aigc.generation.GenerationParam;
import com.alibaba.dashscope.aigc.generation.models.QwenParam;
import com.alibaba.dashscope.common.Message;
import com.alibaba.dashscope.common.Role;
import com.alibaba.dashscope.exception.ApiException;
import com.alibaba.dashscope.exception.InputRequiredException;
import com.alibaba.dashscope.exception.NoApiKeyException;

public class ToolCallingExample {
    public static void main(String[] args) {
        Generation gen = new Generation();
        
        Message userMsg = Message.builder()
            .role(Role.USER.getValue())
            .content("北京今天天气怎么样？")
            .build();
        
        QwenParam param = QwenParam.builder()
            .apiKey(System.getenv("DASHSCOPE_API_KEY"))
            .model("qwen-plus")
            .messages(Arrays.asList(userMsg))
            .resultFormat("message")
            .toolChoice("auto")
            .parallelToolCalls(true)
            .temperature(0.5f)
            .build();
        
        // 添加工具定义
        // param.setTools(...);
        
        try {
            GenerationParam result = gen.call(param);
            System.out.println(result);
        } catch (ApiException | NoApiKeyException | InputRequiredException e) {
            e.printStackTrace();
        }
    }
}
```

**Node.js 示例**：
```javascript
const axios = require('axios');

async function toolCalling() {
  const tools = [
    {
      type: "function",
      function: {
        name: "get_weather",
        description: "获取指定城市的天气信息",
        parameters: {
          type: "object",
          properties: {
            city: {
              type: "string",
              description: "城市名称"
            }
          },
          required: ["city"]
        }
      }
    }
  ];

  const response = await axios.post(
    'https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation',
    {
      model: 'qwen-plus',
      input: {
        messages: [
          { role: 'user', content: '北京今天天气怎么样？' }
        ]
      },
      parameters: {
        tools: tools,
        tool_choice: 'auto',
        parallel_tool_calls: true,
        result_format: 'message',
        temperature: 0.5
      }
    },
    {
      headers: {
        'Authorization': `Bearer ${process.env.DASHSCOPE_API_KEY}`,
        'Content-Type': 'application/json'
      }
    }
  );

  console.log(response.data);
}
```

### 场景2：强制调用特定工具

**适用场景**：必须使用某个特定工具

| 参数 | 推荐值 | 说明 |
|------|--------|------|
| `tool_choice` | `{"type": "function", "function": {"name": "tool_name"}}` | 强制调用 |

**Python 示例**：
```python
response = dashscope.Generation.call(
    api_key=os.getenv('DASHSCOPE_API_KEY'),
    model="qwen-plus",
    messages=messages,
    tools=tools,
    tool_choice={
        "type": "function",
        "function": {"name": "get_weather"}  # 强制调用此工具
    },
    result_format="message"
)
```

---

## 异步调用

### 场景1：Python异步调用（推荐配置）

**适用场景**：高并发场景、批量处理

| 参数 | 推荐值 | 说明 |
|------|--------|------|
| `model` | `qwen-plus` 或 `qwen-max` |  |
| `temperature` | `0.7-1.0` |  |
| `max_tokens` | `2000` |  |

**Python 异步示例**：
```python
import asyncio
import dashscope
from dashscope import AsyncGeneration

async def async_chat():
    async_gen = AsyncGeneration()
    
    messages = [
        {'role': 'user', 'content': '你好'}
    ]
    
    response = await async_gen.call(
        model='qwen-plus',
        messages=messages,
        temperature=0.8,
        max_tokens=2000,
        result_format='message'
    )
    
    return response

# 并发调用
async def batch_chat():
    tasks = [async_chat() for _ in range(10)]
    results = await asyncio.gather(*tasks)
    return results

# 运行
results = asyncio.run(batch_chat())
```

### 场景2：HTTP异步调用（其他语言）

**适用场景**：Java、Go、Node.js等语言的异步HTTP调用

**Go 示例**：
```go
package main

import (
    "bytes"
    "encoding/json"
    "fmt"
    "io"
    "net/http"
    "os"
)

func main() {
    apiKey := os.Getenv("DASHSCOPE_API_KEY")
    url := "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"
    
    payload := map[string]interface{}{
        "model": "qwen-plus",
        "input": map[string]interface{}{
            "messages": []map[string]string{
                {"role": "user", "content": "你好"},
            },
        },
        "parameters": map[string]interface{}{
            "temperature": 0.8,
            "max_tokens": 2000,
            "result_format": "message",
        },
    }
    
    jsonData, _ := json.Marshal(payload)
    req, _ := http.NewRequest("POST", url, bytes.NewBuffer(jsonData))
    req.Header.Set("Authorization", "Bearer "+apiKey)
    req.Header.Set("Content-Type", "application/json")
    
    client := &http.Client{}
    resp, err := client.Do(req)
    if err != nil {
        panic(err)
    }
    defer resp.Body.Close()
    
    body, _ := io.ReadAll(resp.Body)
    fmt.Println(string(body))
}
```

**PHP 示例**：
```php
<?php
$apiKey = getenv('DASHSCOPE_API_KEY');
$url = 'https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation';

$data = [
    'model' => 'qwen-plus',
    'input' => [
        'messages' => [
            ['role' => 'user', 'content' => '你好']
        ]
    ],
    'parameters' => [
        'temperature' => 0.8,
        'max_tokens' => 2000,
        'result_format' => 'message'
    ]
];

$ch = curl_init($url);
curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
curl_setopt($ch, CURLOPT_POST, true);
curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($data));
curl_setopt($ch, CURLOPT_HTTPHEADER, [
    'Authorization: Bearer ' . $apiKey,
    'Content-Type: application/json'
]);

$response = curl_exec($ch);
curl_close($ch);

echo $response;
?>
```

**C# 示例**：
```csharp
using System;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;

class Program
{
    static async Task Main(string[] args)
    {
        var apiKey = Environment.GetEnvironmentVariable("DASHSCOPE_API_KEY");
        var url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation";
        
        var payload = new
        {
            model = "qwen-plus",
            input = new
            {
                messages = new[]
                {
                    new { role = "user", content = "你好" }
                }
            },
            parameters = new
            {
                temperature = 0.8,
                max_tokens = 2000,
                result_format = "message"
            }
        };
        
        using var client = new HttpClient();
        client.DefaultRequestHeaders.Add("Authorization", $"Bearer {apiKey}");
        
        var json = JsonSerializer.Serialize(payload);
        var content = new StringContent(json, Encoding.UTF8, "application/json");
        
        var response = await client.PostAsync(url, content);
        var result = await response.Content.ReadAsStringAsync();
        
        Console.WriteLine(result);
    }
}
```

---

## 文档理解

### 场景1：长文档理解（Qwen-Long系列）

**适用场景**：长文档分析、文档摘要、文档问答

| 参数 | 推荐值 | 说明 |
|------|--------|------|
| `model` | `qwen-long` | 长文本模型 |
| `temperature` | `0.1-0.3` | 文档理解需要确定性 |
| `max_tokens` | `8000-16000` | 长文档需要更多输出 |
| `result_format` | `message` |  |
| `repetition_penalty` | `1.05` | 降低重复 |

**Python 示例**：
```python
response = dashscope.Generation.call(
    api_key=os.getenv('DASHSCOPE_API_KEY'),
    model="qwen-long",
    messages=messages,
    temperature=0.2,
    max_tokens=12000,
    repetition_penalty=1.05,
    result_format='message'
)
```

### 场景2：文档结构化输出

**适用场景**：从文档中提取结构化信息

| 参数 | 推荐值 | 说明 |
|------|--------|------|
| `model` | `qwen-plus` 或 `qwen-max` |  |
| `temperature` | `0.0-0.2` | 高确定性 |
| `response_format` | `{"type": "json_object"}` | JSON输出 |
| `max_tokens` | `4000-8000` |  |

**Python 示例**：
```python
messages = [
    {'role': 'system', 'content': '你是一个文档分析助手。请按照JSON格式输出分析结果。'},
    {'role': 'user', 'content': '请分析以下文档并提取关键信息：...'}
]

response = dashscope.Generation.call(
    api_key=os.getenv('DASHSCOPE_API_KEY'),
    model="qwen-plus",
    messages=messages,
    temperature=0.1,
    max_tokens=6000,
    response_format={"type": "json_object"},
    result_format='message'
)
```

---

## 通用最佳实践

### 1. 参数选择原则

| 场景类型 | temperature | top_p | max_tokens |
|---------|------------|-------|------------|
| 确定性任务（代码、技术文档） | 0.0-0.3 | 0.9 | 4000-8000 |
| 平衡任务（通用对话） | 0.7-1.0 | 0.8 | 2000-4000 |
| 创意任务（写作、头脑风暴） | 1.0-1.5 | 0.95 | 2000-4000 |

### 2. 流式输出建议

- **始终使用 `incremental_output: true`**（除非使用Qwen3，它默认就是true）
- 流式输出时设置合理的 `max_tokens`，避免过早截断
- 使用 `result_format: "message"` 便于处理多轮对话

### 3. 工具调用注意事项

- **必须设置 `result_format: "message"`**
- 推荐开启 `parallel_tool_calls: true` 提升效率
- 使用 `tool_choice: "auto"` 让模型自主选择，或指定特定工具

### 4. 成本优化

- 合理设置 `max_tokens`，避免不必要的长输出
- 使用 Prompt Caching（如果支持）减少重复输入成本
- 对于简单任务，使用轻量模型如 `qwen-turbo`

### 5. 错误处理

- 设置合理的超时时间
- 实现重试机制（建议最多3次）
- 检查 `status_code` 和 `finish_reason`

### 6. 模型选择指南

| 模型 | 适用场景 | 特点 |
|------|---------|------|
| `qwen-turbo` | 快速响应、简单任务 | 速度快、成本低 |
| `qwen-plus` | 通用场景 | 平衡性能和成本 |
| `qwen-max` | 复杂推理、高质量输出 | 最强能力 |
| `qwen3-max-preview` | 复杂推理、思考模式 | 支持深度思考 |
| `qwen-vl-plus` | 图像理解 | 多模态 |
| `qwen-audio-turbo` | 音频处理 | 音频理解 |
| `qwen-long` | 长文档处理 | 超长上下文 |

---

## 扩展参数默认值建议（未设置时不透传）

**说明**：以下参数在本项目默认不透传，保持官方默认行为；仅在需要特定行为时才显式配置。
仍以系统提示词为中心驱动，参数仅用于“强制/约束”行为。

| 参数 | 推荐默认值 | 触发/说明 |
|------|-----------|----------|
| `top_k` | 不设置 | 需要更强随机性时再设，`>100` 等效关闭 |
| `seed` | 不设置 | 需要可复现输出时设置 |
| `stop` | 不设置 | 需要强制截断输出时设置 |
| `n` | `1` | 工具调用时必须为 `1` |
| `response_format` | 不设置 | 结构化输出时设置 `json_object/json_schema` |
| `logprobs` | `false` | 仅支持部分模型 |
| `top_logprobs` | `0` | 仅在 `logprobs=true` 时生效 |
| `enable_search` | `false` | 需要联网检索时开启 |
| `search_options` | 不设置 | `enable_search=true` 时可设 `{"search_mode":"auto"}` |
| `incremental_output` | `true`（流式） | 流式输出建议开启；非流式不需要 |
| `vl_high_resolution_images` | `false` | 仅高分辨率图像场景启用 |
| `vl_enable_image_hw_output` | `false` | 仅需返回缩放后尺寸时启用 |
| `enable_code_interpreter` | `false` | 仅 `qwen3-max-preview` 思考模式支持 |

**补充**：
- 若设置 `search_options`，建议同时启用 `enable_search=true`（本项目已自动处理）。
- 工具调用场景请固定 `result_format="message"` 并保持 `n=1`。

---

## 完整配置示例（YAML格式）

```yaml
# 通用对话配置
general_chat:
  model: "qwen-plus"
  temperature: 0.8
  top_p: 0.8
  max_tokens: 2000
  result_format: "message"
  stream: false

# 流式对话配置
streaming_chat:
  model: "qwen-plus"
  temperature: 0.8
  max_tokens: 4000
  result_format: "message"
  stream: true
  incremental_output: true

# 代码生成配置
code_generation:
  model: "qwen-plus"
  temperature: 0.2
  top_p: 0.9
  max_tokens: 4000
  repetition_penalty: 1.05
  result_format: "message"

# 工具调用配置
tool_calling:
  model: "qwen-plus"
  temperature: 0.5
  max_tokens: 2000
  result_format: "message"
  tool_choice: "auto"
  parallel_tool_calls: true

# 联网搜索配置
web_search:
  model: "qwen-plus"
  temperature: 0.8
  max_tokens: 3000
  result_format: "message"
  enable_search: true
  search_options:
    search_mode: "auto"

# 图像理解配置
vision:
  model: "qwen-vl-plus"
  temperature: 0.2
  max_tokens: 1500
  result_format: "message"
  vl_high_resolution_images: true

# 思考模式配置（Qwen3）
thinking_mode:
  model: "qwen3-max-preview"
  temperature: 0.7
  max_tokens: 4000
  result_format: "message"
  enable_thinking: true
  thinking_budget: 10000
  stream: true
  incremental_output: true
```

---

## 注意事项

1. **QVQ模型**：不建议修改 `temperature`、`top_p`、`top_k`、`repetition_penalty`、`presence_penalty` 的默认值
2. **Qwen3系列**：思考模式下 `incremental_output` 只能设置为 `true`，`result_format` 必须为 `message`
3. **工具调用**：使用 `tools` 时，`result_format` 必须为 `message`
4. **流式输出**：Qwen3商业版（思考模式）、Qwen3开源版、QwQ、QVQ 只支持流式输出
5. **联网搜索**：启用后可能增加 Token 消耗
6. **内容审核**：可通过 `X-DashScope-DataInspection` Header 启用增强内容审核

---

## 参考资源

- [通义千问官方文档](https://help.aliyun.com/zh/model-studio/)
- [模型列表](https://help.aliyun.com/zh/model-studio/getting-started/models)
- [DashScope Python SDK](https://help.aliyun.com/zh/model-studio/developer-reference/api-details-9)
- [Function Calling文档](https://help.aliyun.com/zh/model-studio/developer-reference/function-calling)
- [联网搜索文档](https://help.aliyun.com/zh/model-studio/developer-reference/online-search)
