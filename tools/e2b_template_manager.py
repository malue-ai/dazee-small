"""
E2B Template Manager - 模板构建和管理

职责：
1. 加载模板配置（从 e2b_templates.yaml）
2. 按需构建自定义模板
3. 根据任务类型推荐模板
4. 缓存已构建的模板

参考文档：
- https://e2b.dev/docs/template/defining-template
- https://e2b.dev/docs/template/build
"""

import yaml
from typing import Dict, Any, List
from pathlib import Path

from e2b import Template, defaultBuildLogger

from logger import get_logger

logger = get_logger("e2b_template")


class E2BTemplateManager:
    """
    E2B 模板管理器
    
    设计原则：
    1. 按需构建 - 只在需要时构建模板
    2. 版本管理 - 模板有版本号，避免冲突
    3. 自动缓存 - 已构建的模板自动复用
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
        self._built_templates = {}  # 缓存已构建的模板
        
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
        获取或构建模板
        
        工作流：
        1. 检查是否已构建（缓存）
        2. 如果没有，构建模板
        3. 返回模板ID（用于创建沙箱）
        
        Args:
            template_name: 模板名称（如 "data-analysis"）
        
        Returns:
            模板ID（用于 Sandbox.create(template_id)）
        """
        # 检查缓存
        if template_name in self._built_templates:
            logger.debug(f"✅ 使用缓存模板: {template_name}")
            return self._built_templates[template_name]
        
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
            self._built_templates[template_name] = template_id
            return template_id
        
        elif build_method == "custom_build":
            # 自定义构建
            logger.info(f"🔨 构建自定义模板: {template_name}")
            template_id = await self._build_custom_template(template_name, template_config)
            self._built_templates[template_name] = template_id
            return template_id
        
        else:
            logger.warning(f"⚠️ 未知的构建方法: {build_method}，使用 base 模板")
            return "base"
    
    async def _build_custom_template(
        self, 
        template_name: str,
        config: Dict[str, Any]
    ) -> str:
        """
        构建自定义模板
        
        参考 E2B 文档：https://e2b.dev/docs/template/defining-template
        """
        try:
            # 创建模板定义
            base_template = config.get("base_template", "base")
            template = Template().fromTemplate(base_template)
            
            # 安装包
            pre_install_packages = config.get("pre_install_packages", [])
            if pre_install_packages:
                logger.info(f"📦 预安装包: {', '.join(pre_install_packages)}")
                template.pipInstall(pre_install_packages)
            
            # 设置环境变量
            env_vars = config.get("env_vars", {})
            if env_vars:
                template.setEnvs(env_vars)
            
            # 运行自定义命令
            setup_commands = config.get("setup_commands", [])
            if setup_commands:
                for cmd in setup_commands:
                    template.runCmd(cmd)
            
            # 构建模板
            template_alias = f"{template_name}-v1"  # 添加版本号
            
            # 获取构建配置
            build_config = self.templates_config.get("build_config", {})
            default_config = build_config.get("default", {})
            overrides = build_config.get("overrides", {}).get(template_name, {})
            
            # 合并配置
            cpu_count = overrides.get("cpu_count", default_config.get("cpu_count", 2))
            memory_mb = overrides.get("memory_mb", default_config.get("memory_mb", 2048))
            
            await Template.build(
                template,
                alias=template_alias,
                cpuCount=cpu_count,
                memoryMB=memory_mb,
                onBuildLogs=defaultBuildLogger()
            )
            
            logger.info(f"✅ 模板构建完成: {template_alias}")
            return template_alias
        
        except Exception as e:
            logger.error(f"❌ 模板构建失败: {e}", exc_info=True)
            # 降级：使用 base 模板
            logger.warning("⚠️ 降级到 base 模板")
            return "base"
    
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


# ==================== 便捷函数 ====================

def create_e2b_template_manager(config_path: str = None) -> E2BTemplateManager:
    """
    创建E2B模板管理器
    
    Args:
        config_path: 配置文件路径
    
    Returns:
        E2BTemplateManager实例
    """
    return E2BTemplateManager(config_path=config_path)

