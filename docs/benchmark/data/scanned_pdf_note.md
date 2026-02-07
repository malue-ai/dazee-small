# 扫描 PDF 测试文件准备说明

## 测试用例

**A3: 文件格式转换出错恢复**

用户输入："把这个 PDF 转成 Word 文档"

## 文件要求

需要一份包含以下特征的 PDF 文件：

1. **混合页面类型**：
   - 前 2 页：正常文本（可被解析）
   - 第 3 页：扫描图片（纯图像，无可提取文本）
   - 第 4 页：正常文本

2. **触发条件**：
   - `nano-pdf` Skill 使用 pypdf 解析时，第 3 页无法提取文本
   - 首次解析会返回"部分页面无法提取"的错误或空白内容

3. **预期回溯**：
   - 小搭子 RVR-B `ErrorClassifier` 分类为"业务逻辑错误"（非网络/权限问题）
   - `BacktrackManager` 尝试 `PARAM_ADJUST` 或 `TOOL_REPLACE` 回溯
   - 替代方案：跳过图片页 / 标注"此页为扫描件" / 尝试 OCR

## 准备方式

### 方式 1：手动制作（推荐）

1. 用 Word 写 4 页内容（任意主题）
2. 将第 3 页替换为一张截图/照片（使其成为纯图像页）
3. 导出为 PDF
4. 保存为 `docs/benchmark/data/scanned_contract.pdf`

### 方式 2：使用现有文件

任何包含"扫描页 + 文字页"混合的 PDF 都可以。常见来源：
- 扫描的合同/发票
- 包含手写签名页的文档
- 老旧文档的扫描件

### 方式 3：用 Python 生成

```python
# 需要安装 reportlab 和 Pillow
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from PIL import Image

c = canvas.Canvas("scanned_contract.pdf", pagesize=A4)

# 页面1：正常文本
c.drawString(72, 750, "合同协议书")
c.drawString(72, 720, "甲方：XX公司  乙方：YY公司")
c.drawString(72, 690, "本合同约定以下事项...")
c.showPage()

# 页面2：正常文本
c.drawString(72, 750, "第一条 服务内容")
c.drawString(72, 720, "甲方委托乙方提供技术开发服务...")
c.showPage()

# 页面3：纯图片（模拟扫描页）
# 先生成一张纯色图片模拟扫描件
img = Image.new('RGB', (595, 842), color=(245, 245, 240))
img.save("/tmp/scan_page.png")
c.drawImage("/tmp/scan_page.png", 0, 0, width=595, height=842)
c.showPage()

# 页面4：正常文本
c.drawString(72, 750, "第三条 费用与支付")
c.drawString(72, 720, "总费用为人民币壹拾万元整（¥100,000.00）")
c.showPage()

c.save()
```

## 验证清单

- [ ] PDF 文件至少 4 页
- [ ] 至少 1 页是纯图像（不可提取文本）
- [ ] 其他页面有可提取的中文文本
- [ ] 文件大小合理（<5MB）
