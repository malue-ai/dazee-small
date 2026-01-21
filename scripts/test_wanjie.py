"""
测试万界方舟 API 连通性
"""
import httpx
import json

# 万界方舟配置
API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjE4MDA1MDc5NTc1MTMsImlhdCI6MTc2ODk3MTk1Nywia2V5IjoiNUs3NVo4VE5DOUY0SE0zN1A5WTcifQ.Sy2MvdYd-WkZXF3w7wOeVJxxySa2XPqyMToPwZ8XFHA"
BASE_URL = "https://maas-openapi.wanjiedata.com/api/anthropic"
MODEL = "claude-sonnet-4-20250514"


def test_basic():
    """测试基础调用"""
    print("=" * 50)
    print("测试 1: 基础 Messages API")
    print("=" * 50)
    
    url = f"{BASE_URL}/v1/messages"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json"
    }
    payload = {
        "model": MODEL,
        "max_tokens": 100,
        "messages": [
            {"role": "user", "content": "说你好"}
        ]
    }
    
    response = httpx.post(url, headers=headers, json=payload, timeout=30)
    print(f"状态码: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ 成功!")
        print(f"模型: {data.get('model')}")
        print(f"内容: {data.get('content', [{}])[0].get('text', '')[:100]}")
        print(f"Usage: {data.get('usage')}")
        return True
    else:
        print(f"❌ 失败: {response.text}")
        return False


def test_with_anthropic_sdk():
    """测试 anthropic SDK + auth_token"""
    print("\n" + "=" * 50)
    print("测试 2: anthropic SDK + auth_token")
    print("=" * 50)
    
    try:
        import anthropic
        
        client = anthropic.Anthropic(
            auth_token=API_KEY,
            base_url=BASE_URL
        )
        
        response = client.messages.create(
            model=MODEL,
            max_tokens=100,
            messages=[{"role": "user", "content": "说你好"}]
        )
        
        print(f"✅ 成功!")
        print(f"模型: {response.model}")
        print(f"内容: {response.content[0].text[:100]}")
        return True
        
    except Exception as e:
        print(f"❌ 失败: {e}")
        return False


def test_with_api_key():
    """测试 anthropic SDK + api_key（官方方式）"""
    print("\n" + "=" * 50)
    print("测试 3: anthropic SDK + api_key")
    print("=" * 50)
    
    try:
        import anthropic
        
        client = anthropic.Anthropic(
            api_key=API_KEY,
            base_url=BASE_URL
        )
        
        response = client.messages.create(
            model=MODEL,
            max_tokens=100,
            messages=[{"role": "user", "content": "说你好"}]
        )
        
        print(f"✅ 成功!")
        print(f"模型: {response.model}")
        print(f"内容: {response.content[0].text[:100]}")
        return True
        
    except Exception as e:
        print(f"❌ 失败: {e}")
        return False


if __name__ == "__main__":
    print("万界方舟 API 连通性测试\n")
    
    # 测试 1: httpx 直接调用
    r1 = test_basic()
    
    # 测试 2: anthropic SDK + auth_token
    r2 = test_with_anthropic_sdk()
    
    # 测试 3: anthropic SDK + api_key
    r3 = test_with_api_key()
    
    print("\n" + "=" * 50)
    print("测试结果汇总")
    print("=" * 50)
    print(f"httpx 直接调用:      {'✅' if r1 else '❌'}")
    print(f"SDK + auth_token:    {'✅' if r2 else '❌'}")
    print(f"SDK + api_key:       {'✅' if r3 else '❌'}")
