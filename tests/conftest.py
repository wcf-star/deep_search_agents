import sys
from pathlib import Path

# 让 pytest 能 import 项目顶层命名空间包（agent / tools / api / utils / rawflow）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
