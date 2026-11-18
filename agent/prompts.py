# 目标加载 yml 中的数据，供创建主和子智能体使用
import logging
from pathlib import Path

import yaml

logger = logging.getLogger("agent.prompts")


def load_yaml(file_path):
    """
    加载指定位置的 yaml 配置文件。
    safe_load 只会加载，不会执行内嵌代码，防止注入攻击。
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


project_root_path = Path(__file__).parents[1]
yaml_file_path = project_root_path / "prompt" / "prompts.yml"

prompt_yaml_content = load_yaml(yaml_file_path)

main_agent_content = prompt_yaml_content["main_agent"]
sub_agents_content = prompt_yaml_content["sub_agents"]

logger.debug("main_agent_content: %s", main_agent_content)
logger.debug("sub_agents_content: %s", sub_agents_content)
