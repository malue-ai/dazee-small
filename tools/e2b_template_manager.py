"""
E2B Template Manager - 模板配置和管理

职责：
1. 加载模板配置（从 e2b_templates.yaml）
2. 根据任务类型推荐模板
3. 返回预构建的模板 ID

注意：E2B SDK v2+ 中，自定义模板需要通过 CLI 工具预先构建：
  e2b template build --name <template-name>

参考文档：
- https://e2b.dev/docs/sandbox-template
- https://e2b.dev/docs/cli/template-build
"""

import yaml
from typing import Dict, Any, List, Optional
from pathlib import Path

from logger import get_logger

logger = get_logger("e2b_template")


class E2BTemplateManager:
    """
    E2B 模板管理器（v2+ 兼容版本）
    
    设计原则：
    1. 配置驱动 - 模板配置与代码分离
    2. 预构建模板 - 自定义模板需提前通过 CLI 构建
    3. 运行时包安装 - 未预装的包在运行时安装
    
    E2B SDK v2+ 变更说明：
    - Template Python API 已移除，改用 CLI 构建
    - 自定义模板需要使用 `e2b template build` 命令预构建
    - 运行时可通过 sandbox.commands.run("pip install ...") 安装包
    """
    
    def __init__(self, config_path: str = None):
        """
        初始化模板管理器
        
        Args:
            config_path: 配置文件路径（默认 config/e2b_templates.yaml）
        """
        
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config" / "e2b_templates.yaml"
        
        self.config_path = Path(config_path)
        self.templates_config = self._load_config()
        self._template_cache: Dict[str, str] = {}  # 模板名称 -> 模板 ID 缓存
        
        logger.info(f"✅ E2B模板管理器已初始化 ({len(self.templates_config.get('templates', {}))} 个模板配置)")
    
    def _load_config(self) -> Dict:
        """加载模板配置"""
        if not self.config_path.exists():
            logger.warning(f"⚠️ 模板配置文件不存在: {self.config_path}")
            return {"templates": {}, "routing_rules": []}
        
        try:
            with open(self.config_path) as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"❌ 加载模板配置失败: {e}")
            return {"templates": {}, "routing_rules": []}
    
    async def get_or_build_template(self, template_name: str) -> str:
        """
        获取模板 ID
        
        E2B SDK v2+ 说明：
        - 对于内置模板（build_method: use_builtin），直接返回 template_id
        - 对于自定义模板（build_method: custom_build），返回预构建的模板 ID 或降级到 base
        
        如果需要自定义模板，请先使用 CLI 构建：
            e2b template build --name <template-name>
        
        Args:
            template_name: 模板名称（如 "data-analysis"）
        
        Returns:
            模板 ID（用于创建沙箱）
        """
        # 检查缓存
        if template_name in self._template_cache:
            logger.debug(f"✅ 使用缓存模板: {template_name}")
            return self._template_cache[template_name]
        
        # 获取配置
        templates = self.templates_config.get("templates", {})
        template_config = templates.get(template_name)
        
        if not template_config:
            logger.warning(f"⚠️ 模板配置不存在: {template_name}，使用 base 模板")
            return "base"
        
        build_method = template_config.get("build_method", "use_builtin")
        
        if build_method == "use_builtin":
            # 使用 E2B 内置模板（无需构建）
            template_id = template_config.get("template_id", "base")
            logger.info(f"✅ 使用内置模板: {template_id}")
            self._template_cache[template_name] = template_id
            return template_id
        
        elif build_method == "custom_build":
            # 自定义模板：检查是否有预构建的 template_id
            template_id = template_config.get("template_id")
            
            if template_id:
                # 已有预构建模板
                logger.info(f"✅ 使用预构建模板: {template_id}")
                self._template_cache[template_name] = template_id
                return template_id
            else:
                # 无预构建模板，降级到 base 并记录所需包
                pre_install_packages = template_config.get("pre_install_packages", [])
                logger.warning(
                    f"⚠️ 模板 {template_name} 未预构建，降级到 base 模板。"
                    f"所需包将在运行时安装: {', '.join(pre_install_packages[:5])}..."
                )
                logger.info(
                    f"💡 提示：如需更快启动，请使用 CLI 预构建模板：\n"
                    f"   e2b template build --name {template_name}"
                )
                self._template_cache[template_name] = "base"
                return "base"
        
        else:
            logger.warning(f"⚠️ 未知的构建方法: {build_method}，使用 base 模板")
            return "base"
    
    def get_runtime_packages(self, template_name: str) -> List[str]:
        """
        获取模板所需的运行时包列表
        
        当模板未预构建时，这些包需要在运行时安装。
        
        Args:
            template_name: 模板名称
            
        Returns:
            需要安装的包列表
        """
        templates = self.templates_config.get("templates", {})
        template_config = templates.get(template_name, {})
        return template_config.get("pre_install_packages", [])
    
    def get_recommended_template(self, task_type: str) -> str:
        """
        根据任务类型推荐模板
        
        Args:
            task_type: 任务类型（来自 Intent Analysis）
        
        Returns:
            推荐的模板名称
        """
        routing_rules = self.templates_config.get("routing_rules", [])
        
        for rule in routing_rules:
            if rule.get("task_type") == task_type:
                template_name = rule.get("preferred_template")
                reason = rule.get("reason", "")
                logger.info(f"🎯 推荐模板: {template_name} - {reason}")
                return template_name
        
        # 默认使用 base 模板
        logger.debug("🎯 使用默认模板: base")
        return "base"
    
    def get_template_info(self, template_name: str) -> Dict[str, Any]:
        """获取模板信息"""
        templates = self.templates_config.get("templates", {})
        return templates.get(template_name, {})
    
    def list_templates(self) -> List[str]:
        """列出所有可用模板"""
        templates = self.templates_config.get("templates", {})
        return list(templates.keys())
    
    def get_package_mapping(self) -> Dict[str, str]:
        """
        获取包名映射（import 名 → pip 包名）
        
        例如：cv2 -> opencv-python, PIL -> Pillow
        
        Returns:
            包名映射字典
        """
        pkg_mgmt = self.templates_config.get("package_management", {})
        return pkg_mgmt.get("package_mapping", {})
    
    def is_template_prebuilt(self, template_name: str) -> bool:
        """
        检查模板是否已预构建
        
        Args:
            template_name: 模板名称
            
        Returns:
            是否已预构建
        """
        templates = self.templates_config.get("templates", {})
        template_config = templates.get(template_name, {})
        
        build_method = template_config.get("build_method", "use_builtin")
        
        if build_method == "use_builtin":
            return True  # 内置模板始终可用
        
        # 自定义模板需要检查是否有 template_id
        return bool(template_config.get("template_id"))


# ==================== 便捷函数 ====================

def create_e2b_template_manager(config_path: str = None) -> E2BTemplateManager:
    """
    创建 E2B 模板管理器
    
    Args:
        config_path: 配置文件路径
    
    Returns:
        E2BTemplateManager 实例
    """
    return E2BTemplateManager(config_path=config_path)

