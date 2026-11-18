import logging
import os
from pathlib import Path

if os.name == "nt":
    # WeasyPrint 在 Windows 上依赖 GTK3 运行时（libgobject/libpango 等 DLL），
    # 该运行时不是 pip 包，需另行安装（gtk3-runtime，装到默认或用户目录）。
    # 这里在 import weasyprint 之前，把 GTK DLL 目录加入进程搜索路径，
    # 避免依赖全局环境变量 WEASYPRINT_DLL_DIRECTORIES。
    _gtk_dll_dirs = [d for d in os.getenv("WEASYPRINT_DLL_DIRECTORIES", "").split(";") if d]
    _gtk_dll_dirs += [
        str(Path.home() / "gtk3-runtime" / "bin"),       # 无管理员权限时的用户目录安装
        r"C:\Program Files\GTK3-Runtime Win64\bin",      # 默认安装位置
        r"C:\msys64\ucrt64\bin",
        r"C:\msys64\mingw64\bin",
    ]
    for _d in dict.fromkeys(_gtk_dll_dirs):  # 去重且保持顺序
        if Path(_d).is_dir():
            os.add_dll_directory(_d)

import markdown
from weasyprint import HTML

logger = logging.getLogger("utils.pdf_converter")


def convert_md_to_pdf_via_weasyprint(md_abs_path: Path, pdf_abs_path: Path) -> str:
    """
    使用 WeasyPrint 将 Markdown 转换为 PDF（纯 Python，无需 MS Office）。

    流程：Markdown -> HTML（markdown 库，含 tables/fenced_code 扩展）-> PDF（WeasyPrint）。
    """
    try:
        # 1. MD -> HTML
        with open(md_abs_path, 'r', encoding='utf-8') as f:
            md_content = f.read()

        html_body = markdown.markdown(md_content, extensions=['tables', 'fenced_code'])
        html_content = f"""
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: "Microsoft YaHei", "SimSun", "Noto Sans CJK SC", sans-serif; }}
                table {{ border-collapse: collapse; width: 100%; }}
                th, td {{ border: 1px solid black; padding: 8px; }}
                pre {{ background-color: #f5f5f5; padding: 10px; border-radius: 4px; white-space: pre-wrap; }}
                code {{ font-family: "Consolas", "Courier New", monospace; }}
            </style>
        </head>
        <body>
            {html_body}
        </body>
        </html>
        """

        # 2. HTML -> PDF（base_url 指向 md 所在目录，便于解析 md 中的相对图片引用）
        HTML(string=html_content, base_url=str(md_abs_path.parent)).write_pdf(str(pdf_abs_path))

        if pdf_abs_path.exists():
            return f"成功转换: {pdf_abs_path} (WeasyPrint引擎)"
        return f"转换完成但未生成文件: {pdf_abs_path}"
    except Exception as e:
        logger.error("WeasyPrint转换PDF失败: %s", e, exc_info=True)
        return f"转换失败: {str(e)}"
