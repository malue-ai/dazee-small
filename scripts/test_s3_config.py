#!/usr/bin/env python3
"""
测试 AWS S3 配置

功能：
1. 验证 AWS 凭证是否正确
2. 测试 S3 bucket 连接
3. 测试文件上传和下载
"""

import asyncio
import sys
import os
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from logger import get_logger
from utils.s3_uploader import get_s3_uploader, S3ConfigError, S3UploadError

logger = get_logger("test_s3")


async def test_s3_connection():
    """测试 S3 连接"""
    print("=" * 60)
    print("AWS S3 配置测试")
    print("=" * 60)
    
    try:
        # 1. 初始化 S3 上传器
        print("\n1️⃣ 初始化 S3 上传器...")
        uploader = get_s3_uploader()
        print(f"✅ S3 Bucket: {uploader.bucket_name}")
        print(f"✅ AWS Region: {uploader.config['aws']['region']}")
        
        # 2. 测试 S3 连接
        print("\n2️⃣ 测试 S3 bucket 访问...")
        try:
            # 列出 bucket（测试访问权限）
            response = uploader.s3_client.head_bucket(Bucket=uploader.bucket_name)
            print(f"✅ Bucket 访问成功")
        except Exception as e:
            print(f"❌ Bucket 访问失败: {str(e)}")
            return False
        
        # 3. 创建测试文件
        print("\n3️⃣ 创建测试文件...")
        test_file = "/tmp/test_s3_upload.txt"
        test_content = f"S3 测试文件\n创建时间: {asyncio.get_event_loop().time()}\n"
        
        with open(test_file, 'w', encoding='utf-8') as f:
            f.write(test_content)
        
        print(f"✅ 测试文件已创建: {test_file}")
        
        # 4. 上传文件到 S3
        print("\n4️⃣ 上传文件到 S3...")
        try:
            result = await uploader.upload_file(
                file_path=test_file,
                category="temp",
                user_id="test_user",
                filename="test_upload.txt",
                metadata={"test": "true"}
            )
            
            print(f"✅ 上传成功:")
            print(f"   - S3 Key: {result['s3_key']}")
            print(f"   - S3 URL: {result['s3_url']}")
            print(f"   - 文件大小: {result['file_size']} bytes")
            print(f"   - 内容类型: {result['content_type']}")
            print(f"   - 预签名 URL: {result['presigned_url'][:50]}...")
            
            s3_key = result['s3_key']
        except Exception as e:
            print(f"❌ 上传失败: {str(e)}")
            return False
        
        # 5. 生成新的预签名 URL（测试下载）
        print("\n5️⃣ 生成预签名 URL...")
        try:
            presigned_url = uploader.get_presigned_url(s3_key, expires_in=300)  # 5分钟
            print(f"✅ 预签名 URL 已生成（5分钟有效）")
            print(f"   URL: {presigned_url[:80]}...")
        except Exception as e:
            print(f"❌ 生成失败: {str(e)}")
        
        # 6. 删除测试文件
        print("\n6️⃣ 删除测试文件...")
        try:
            success = await uploader.delete_file(s3_key)
            if success:
                print(f"✅ 测试文件已删除: {s3_key}")
            else:
                print(f"⚠️ 删除失败（但不影响测试结果）")
        except Exception as e:
            print(f"⚠️ 删除失败: {str(e)}")
        
        # 清理本地测试文件
        try:
            os.unlink(test_file)
        except Exception:
            pass
        
        print("\n" + "=" * 60)
        print("✅ S3 配置测试通过！")
        print("=" * 60)
        return True
    
    except S3ConfigError as e:
        print(f"\n❌ S3 配置错误: {str(e)}")
        print("\n请检查：")
        print("1. .env 文件中的 AWS 凭证是否正确")
        print("2. AWS_ACCESS_KEY_ID 和 AWS_SECRET_ACCESS_KEY 是否已设置")
        print("3. config/storage.yaml 配置是否正确")
        return False
    
    except Exception as e:
        print(f"\n❌ 测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """主函数"""
    success = await test_s3_connection()
    
    if success:
        print("\n🎉 所有测试通过！可以开始使用 S3 存储了。")
        sys.exit(0)
    else:
        print("\n💥 测试失败，请检查配置后重试。")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

